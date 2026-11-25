import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import App from './App';

const DATE = '2026-11-25';
const TOKEN = 'secret-token';
const SLOTS = ['PG', 'SG', 'SF', 'PF', 'C', '6TH'];
const game = { id: 'g1', status: 1, statusText: '7:00 pm ET', startTimeUTC: '2026-11-26T00:00:00Z', home: true, opponent: 'NYK' };
const emptySlot = (slot) => ({ slot, player: null, game: null, stats: null, points: 0, locked: false, hidden: false });

const CAP = 148465000;
const emptyLineup = {
  date: DATE,
  player: 'Amy',
  total: 0,
  final: false,
  slots: SLOTS.map(emptySlot),
  salary: { used: 0, cap: CAP, left: CAP },
};

const pool = {
  date: DATE,
  games: 1,
  injuryReport: { official: { published: '2026-11-25T17:30:00', url: 'https://example.com/report.pdf' }, espn: true },
  players: [
    {
      id: 1, name: 'Jayson Tatum', team: 'BOS', position: 'F-G', slots: ['PG', 'SG', 'SF', 'PF', '6TH'],
      salary: 58456566, salaryListed: true,
      injury: { status: 'QUESTIONABLE', label: 'Questionable', reason: 'Right Knee Inflammation', source: 'NBA' },
      gp: 15, avg: { pts: 26, reb: 7, ast: 6, stl: 1, blk: 1, tov: 3 }, avgPoints: 109, game, locked: false,
    },
    {
      id: 2, name: 'Started Guy', team: 'LAL', position: 'G', slots: ['PG', 'SG', '6TH'],
      salary: 1357763, salaryListed: false,
      gp: 10, avg: { pts: 10, reb: 2, ast: 2, stl: 0, blk: 0, tov: 1 }, avgPoints: 34, game: { ...game, status: 2 }, locked: true,
    },
    {
      id: 3, name: 'Big Center', team: 'BOS', position: 'C', slots: ['C', '6TH'],
      salary: 30000000, salaryListed: true,
      injury: { status: 'OUT', label: 'Out', reason: 'Left Calf Strain', source: 'ESPN' },
      gp: 12, avg: { pts: 8, reb: 10, ast: 1, stl: 0, blk: 2, tov: 1 }, avgPoints: 60, game, locked: false,
    },
  ],
};

const savedLineup = {
  ...emptyLineup,
  slots: emptyLineup.slots.map((s) =>
    s.slot === 'PG'
      ? { ...s, player: { id: 1, name: 'Jayson Tatum', team: 'BOS', position: 'F-G', salary: 58456566 }, game }
      : s
  ),
  salary: { used: 58456566, cap: CAP, left: CAP - 58456566 },
};

// Bob picked a center whose game hasn't started, so it stays hidden from others.
const bobLineup = {
  ...emptyLineup,
  player: 'Bob',
  slots: emptyLineup.slots.map((s) => (s.slot === 'C' ? { ...s, hidden: true } : s)),
};

const daily = {
  date: DATE,
  entries: [
    { player: 'Bob', total: 0, final: false, players: 1, rank: 1 },
    { player: 'Amy', total: 0, final: false, players: 1, rank: 1 },
  ],
};
const overall = {
  entries: [{ player: 'Bob', days: 3, total: 540, average: 180, best: 220, wins: 2, rank: 1 }],
};

function respond(url, options = {}) {
  const token = options.headers?.['X-Fantasy-Token'];
  if (url === '/games/') return { date: '2026-11-23', source: 'live', games: [] };
  if (url === '/fantasy/me' && options.method === 'PATCH') {
    const { name } = JSON.parse(options.body);
    if (token !== TOKEN) return [401, { detail: 'bad token' }];
    return name === 'Bob' ? [409, { detail: '「Bob」已經有人使用' }] : { name };
  }
  if (url === '/fantasy/me') return token === TOKEN ? { name: 'Amy' } : [401, { detail: 'bad token' }];
  if (url === '/fantasy/users') return { name: JSON.parse(options.body).name, token: TOKEN };
  if (url === '/fantasy/leaderboard') return overall;
  if (url === '/fantasy/salary') return { cap: CAP, season: '2026-27', unlisted: 1357763 };
  if (url.startsWith('/fantasy/history/')) return { history: [] };
  if (url.endsWith('/leaderboard')) return daily;
  if (url.endsWith('/pool')) return pool;
  if (options.method === 'PUT') return token === TOKEN ? savedLineup : [401, { detail: 'no token' }];
  if (url.endsWith('/lineup/Bob')) return bobLineup;
  return currentLineup;
}

let currentLineup;

beforeEach(() => {
  currentLineup = emptyLineup;
  global.fetch = jest.fn((url, options) => {
    const result = respond(url, options);
    const [status, body] = Array.isArray(result) ? result : [200, result];
    return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
  });
  localStorage.setItem('fantasy-token', TOKEN);
  window.location.hash = `#/fantasy/${DATE}`;
});

afterEach(() => {
  localStorage.clear();
  window.location.hash = '';
});

test('shows scoring rules, my six empty slots and both leaderboards', async () => {
  render(<App />);
  expect(await screen.findAllByText('尚未選擇')).toHaveLength(6);
  expect(screen.getByText('三分球')).toBeInTheDocument();
  expect(screen.getAllByText('×−2')).toHaveLength(2); // 失誤、犯規
  expect(screen.getByText('×−1')).toBeInTheDocument();
  expect(screen.getByText('我的陣容')).toBeInTheDocument();
  expect(screen.getByText('Amy', { selector: 'strong' })).toBeInTheDocument(); // account bar
  expect(await screen.findByText('540')).toBeInTheDocument(); // overall total
  expect(screen.getByText('$148,465,000')).toBeInTheDocument(); // cap in the rules
  expect(screen.getByText('$148.47M')).toBeInTheDocument(); // salary left
  expect(screen.getAllByText('（你）')).toHaveLength(1);
});

test('picking a PG lists only eligible, unlocked players and saves with my token', async () => {
  render(<App />);
  const pickButtons = await screen.findAllByRole('button', { name: '選擇球員' });
  fireEvent.click(pickButtons[0]); // PG

  expect(await screen.findByText('選擇 PG（控球後衛）')).toBeInTheDocument();
  expect(screen.queryByText('Big Center')).not.toBeInTheDocument(); // a C cannot play PG
  expect(screen.getByText('Started Guy').closest('button')).toBeDisabled();

  fireEvent.click(screen.getByText('Jayson Tatum').closest('button'));

  await waitFor(() => {
    const put = global.fetch.mock.calls.find(([, o]) => o?.method === 'PUT');
    expect(put[0]).toBe(`/fantasy/${DATE}/lineup`);
    expect(put[1].headers['X-Fantasy-Token']).toBe(TOKEN);
    expect(JSON.parse(put[1].body).slots).toEqual({ PG: 1, SG: null, SF: null, PF: null, C: null, '6TH': null });
  });
  await waitFor(() => expect(screen.getAllByText('尚未選擇')).toHaveLength(5));
  expect(screen.queryByText('選擇 PG（控球後衛）')).not.toBeInTheDocument(); // picker closes after saving
  expect(screen.getByText('Jayson Tatum')).toBeInTheDocument();
});

test("viewing another player's lineup is read-only and hides unstarted picks", async () => {
  render(<App />);
  await screen.findAllByRole('button', { name: '選擇球員' });
  const board = (await screen.findByText('當日排行榜')).closest('section');
  fireEvent.click(within(board).getByText('Bob'));

  expect(await screen.findByText('Bob 的陣容')).toBeInTheDocument();
  expect(await screen.findByText('已選擇，開賽後公開')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '選擇球員' })).not.toBeInTheDocument();

  fireEvent.click(screen.getByText('‹ 回到我的陣容'));
  expect(await screen.findAllByRole('button', { name: '選擇球員' })).toHaveLength(6);
});

test('a new visitor joins with a nickname', async () => {
  localStorage.clear();
  render(<App />);
  fireEvent.change(await screen.findByLabelText('暱稱'), { target: { value: 'Amy' } });
  fireEvent.click(screen.getByRole('button', { name: '加入' }));

  expect(await screen.findAllByRole('button', { name: '選擇球員' })).toHaveLength(6);
  const post = global.fetch.mock.calls.find(([url]) => url === '/fantasy/users');
  expect(JSON.parse(post[1].body)).toEqual({ name: 'Amy' });
  expect(localStorage.getItem('fantasy-token')).toBe(TOKEN);
});

test('players over the remaining salary cannot be picked', async () => {
  // $100M already spent on other slots: $48.47M left for the 6TH slot.
  currentLineup = { ...emptyLineup, salary: { used: 100000000, cap: CAP, left: CAP - 100000000 } };
  render(<App />);
  const pickButtons = await screen.findAllByRole('button', { name: '選擇球員' });
  fireEvent.click(pickButtons[5]); // 6TH: anyone

  const tatum = await screen.findByText('Jayson Tatum');
  expect(screen.getAllByText('$48.47M')).toHaveLength(2); // salary-left tile and the picker's budget
  expect(tatum.closest('button')).toBeDisabled(); // $58.46M
  expect(screen.getByText('超出薪資')).toBeInTheDocument();
  expect(screen.getByText('Big Center').closest('button')).toBeEnabled(); // $30M

  fireEvent.click(screen.getByLabelText('只顯示薪資內'));
  expect(screen.queryByText('Jayson Tatum')).not.toBeInTheDocument();
});

test('the picker shows each player\'s availability and can hide players who are out', async () => {
  render(<App />);
  const pickButtons = await screen.findAllByRole('button', { name: '選擇球員' });
  fireEvent.click(pickButtons[5]); // 6TH: anyone

  const questionable = await screen.findByText('Questionable');
  expect(questionable).toHaveAttribute('title', 'Questionable：Right Knee Inflammation（NBA 官方傷兵報告）');
  expect(screen.getByText('Right Knee Inflammation')).toBeInTheDocument();
  expect(screen.getByText('Out')).toBeInTheDocument();
  expect(screen.getByText(/NBA 官方傷兵報告（11\/25 5:30 PM ET 更新）/)).toBeInTheDocument();

  fireEvent.click(screen.getByLabelText('隱藏 Out 球員'));
  expect(screen.queryByText('Big Center')).not.toBeInTheDocument();
  expect(screen.getByText('Jayson Tatum')).toBeInTheDocument(); // questionable players stay
});

test('a player can change their nickname', async () => {
  render(<App />);
  await screen.findAllByRole('button', { name: '選擇球員' });
  fireEvent.click(screen.getByRole('button', { name: '更改暱稱' }));

  const input = screen.getByLabelText('新暱稱');
  expect(input).toHaveValue('Amy');
  expect(screen.getByRole('button', { name: '儲存' })).toBeDisabled(); // unchanged

  fireEvent.change(input, { target: { value: 'Bob' } });
  fireEvent.click(screen.getByRole('button', { name: '儲存' }));
  expect(await screen.findByText('「Bob」已經有人使用')).toBeInTheDocument();

  fireEvent.change(input, { target: { value: 'Amelia' } });
  fireEvent.click(screen.getByRole('button', { name: '儲存' }));
  expect(await screen.findByText('Amelia', { selector: 'strong' })).toBeInTheDocument();

  const patch = global.fetch.mock.calls.filter(([, o]) => o?.method === 'PATCH').pop();
  expect(patch[1].headers['X-Fantasy-Token']).toBe(TOKEN);
  expect(JSON.parse(patch[1].body)).toEqual({ name: 'Amelia' });
  await waitFor(() =>
    expect(global.fetch.mock.calls.some(([url]) => url === `/fantasy/${DATE}/lineup/Amelia`)).toBe(true)
  );
});

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App';

const DATE = '2026-11-25';
const SLOTS = ['PG', 'SG', 'SF', 'PF', 'C', '6TH'];
const game = { id: 'g1', status: 1, statusText: '7:00 pm ET', startTimeUTC: '2026-11-26T00:00:00Z', home: true, opponent: 'NYK' };

const emptyLineup = {
  date: DATE,
  total: 0,
  final: false,
  slots: SLOTS.map((slot) => ({ slot, player: null, game: null, stats: null, points: 0, locked: false })),
};

const pool = {
  date: DATE,
  games: 1,
  players: [
    {
      id: 1, name: 'Jayson Tatum', team: 'BOS', position: 'F-G', slots: ['PG', 'SG', 'SF', 'PF', '6TH'],
      gp: 15, avg: { pts: 26, reb: 7, ast: 6, stl: 1, blk: 1, tov: 3 }, avgPoints: 109, game, locked: false,
    },
    {
      id: 2, name: 'Started Guy', team: 'LAL', position: 'G', slots: ['PG', 'SG', '6TH'],
      gp: 10, avg: { pts: 10, reb: 2, ast: 2, stl: 0, blk: 0, tov: 1 }, avgPoints: 34, game: { ...game, status: 2 }, locked: true,
    },
    {
      id: 3, name: 'Big Center', team: 'BOS', position: 'C', slots: ['C', '6TH'],
      gp: 12, avg: { pts: 8, reb: 10, ast: 1, stl: 0, blk: 2, tov: 1 }, avgPoints: 60, game, locked: false,
    },
  ],
};

const savedLineup = {
  ...emptyLineup,
  slots: emptyLineup.slots.map((s) =>
    s.slot === 'PG' ? { ...s, player: { id: 1, name: 'Jayson Tatum', team: 'BOS', position: 'F-G' }, game } : s
  ),
};

beforeEach(() => {
  global.fetch = jest.fn((url, options) => {
    let body;
    if (url === '/games/') body = { date: '2026-11-23', source: 'live', games: [] };
    else if (url === '/fantasy/history') body = { history: [] };
    else if (url.endsWith('/pool')) body = pool;
    else if (options?.method === 'PUT') body = savedLineup;
    else body = emptyLineup;
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  });
  window.location.hash = `#/fantasy/${DATE}`;
});

afterEach(() => {
  window.location.hash = '';
});

test('shows scoring rules and six empty slots', async () => {
  render(<App />);
  expect(await screen.findAllByText('尚未選擇')).toHaveLength(6);
  expect(screen.getByText('×−2')).toBeInTheDocument();
});

test('picking a PG lists only eligible, unlocked players and saves the lineup', async () => {
  render(<App />);
  const pickButtons = await screen.findAllByRole('button', { name: '選擇球員' });
  fireEvent.click(pickButtons[0]); // PG

  expect(await screen.findByText('選擇 PG（控球後衛）')).toBeInTheDocument();
  expect(screen.queryByText('Big Center')).not.toBeInTheDocument(); // a C cannot play PG
  expect(screen.getByText('Started Guy').closest('button')).toBeDisabled();

  fireEvent.click(screen.getByText('Jayson Tatum').closest('button'));

  await waitFor(() => {
    const put = global.fetch.mock.calls.find(([, o]) => o?.method === 'PUT');
    expect(put[0]).toBe(`/fantasy/${DATE}`);
    expect(JSON.parse(put[1].body).slots).toEqual({ PG: 1, SG: null, SF: null, PF: null, C: null, '6TH': null });
  });
  await waitFor(() => expect(screen.getAllByText('尚未選擇')).toHaveLength(5));
  expect(screen.queryByText('選擇 PG（控球後衛）')).not.toBeInTheDocument(); // picker closes after saving
  expect(screen.getByText('Jayson Tatum')).toBeInTheDocument();
});

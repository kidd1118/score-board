import { render, screen, within } from '@testing-library/react';
import App from './App';

const DATE = '2026-11-24';
const team = (id, tricode, city, name, score) => ({ id, tricode, city, name, record: '10-5', score, periods: [30, 25, 30, 25] });
const game = {
  id: '0022600052',
  status: 2,
  statusText: 'Q3',
  period: 3,
  clock: '5:12',
  startTimeUTC: null,
  arena: 'Kia Center',
  home: team(1, 'ORL', 'Orlando', 'Magic', 70),
  away: team(2, 'DET', 'Detroit', 'Pistons', 75),
  leaders: { home: null, away: null },
};
const stats = (extra) => ({
  played: true, min: '30:40', pts: 6, fgm: 3, fga: 3, fg2m: 3, fg3m: 0, fg3a: 0, ftm: 0, fta: 0, miss: 0,
  reb: 10, ast: 7, stl: 1, blk: 4, tov: 2, pf: 1, pm: 13, ...extra,
});
const detail = {
  date: DATE,
  game,
  teams: {
    away: {
      tricode: 'DET',
      players: [
        { id: 1, name: 'Ausar Thompson', position: 'F', starter: true, stats: stats(), points: 83, pickedBy: ['Amy', 'Bob'] },
        { id: 2, name: 'Bench Guy', position: '', starter: false, stats: stats({ pm: -4 }), points: 20, pickedBy: [] },
      ],
      bench: ['Cade Cunningham'],
    },
    home: { tricode: 'ORL', players: [], bench: [] },
  },
};

function respond(url) {
  if (url === '/games/') return { date: DATE, source: 'live', games: [game] };
  if (url === `/fantasy/${DATE}/game-leaders`)
    return { date: DATE, games: { [game.id]: { away: { id: 1, name: 'Ausar Thompson', points: 83 }, home: null } } };
  if (url === `/games/${DATE}/${game.id}`) return detail;
  return {};
}

beforeEach(() => {
  global.fetch = jest.fn((url) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(respond(url)) }));
});

afterEach(() => {
  window.location.hash = '';
});

test('a live game card shows each team’s best fantasy scorer and links to the game page', async () => {
  window.location.hash = '#/games';
  render(<App />);
  const card = (await screen.findByText(/Detroit Pistons/)).closest('article');
  expect(await within(card).findByText('Fantasy 積分最高')).toBeInTheDocument();
  expect(within(card).getByText('即時')).toBeInTheDocument();
  expect(within(card).getByText('Ausar Thompson')).toBeInTheDocument();
  expect(within(card).getByRole('link', { name: /完整數據與積分/ })).toHaveAttribute('href', `#/game/${DATE}/${game.id}`);
});

test('the game page lists each player’s stats, fantasy points and pickers', async () => {
  window.location.hash = `#/game/${DATE}/${game.id}`;
  render(<App />);
  expect(await screen.findByRole('heading', { name: 'DET @ ORL' })).toBeInTheDocument();
  expect(global.fetch).toHaveBeenCalledWith(`/games/${DATE}/${game.id}`);

  const row = screen.getByText('Ausar Thompson').closest('tr');
  expect(within(row).getByText('83')).toBeInTheDocument();
  expect(within(row).getByText('+13')).toBeInTheDocument();
  expect(within(row).getByText('被 2 人選：Amy、Bob')).toBeInTheDocument();
  expect(within(row).getByTitle('本隊 Fantasy 積分最高')).toBeInTheDocument();
  expect(screen.getByText('-4')).toBeInTheDocument();
  expect(screen.getByText('未上場：Cade Cunningham')).toBeInTheDocument();
  expect(screen.getByText('還沒有球員上場')).toBeInTheDocument(); // ORL has no rows yet
  expect(screen.getByRole('link', { name: /回到 2026-11-24 的比賽/ })).toHaveAttribute('href', `#/games/${DATE}`);
  expect(screen.getByRole('link', { name: 'Games' })).toHaveClass('active');
});

import { render, screen } from '@testing-library/react';
import App from './App';

const standings = {
  season: '2026-27',
  teams: [
    { id: 1, tricode: 'PHI', city: 'Philadelphia', name: '76ers', conference: 'East', rank: 1, wins: 14, losses: 4, pct: 0.778, gamesBack: 0, home: '7-3', road: '7-1', last10: '7-3', streak: 'L 1', diff: 1.8 },
    { id: 2, tricode: 'OKC', city: 'Oklahoma City', name: 'Thunder', conference: 'West', rank: 1, wins: 15, losses: 2, pct: 0.882, gamesBack: 0, home: '8-1', road: '7-1', last10: '9-1', streak: 'W 5', diff: 12.4 },
  ],
};

const profile = {
  id: 1610612738,
  season: '2026-27',
  tricode: 'BOS',
  city: 'Boston',
  name: 'Celtics',
  conference: 'East',
  division: 'Atlantic',
  wins: 11,
  losses: 6,
  confRank: 3,
  divRank: 2,
  coach: 'Joe Mazzulla',
  ranks: {
    pts: { value: 111.2, rank: 20 },
    reb: { value: 45.2, rank: 10 },
    ast: { value: 26.5, rank: 18 },
    oppPts: { value: 102.1, rank: 1 },
  },
  games: [
    { id: 'g1', date: '2026-10-20', opponent: 'DET', home: false, result: 'L', pts: 113, oppPts: 121, margin: -8 },
    { id: 'g2', date: '2026-10-23', opponent: 'NYK', home: true, result: 'W', pts: 107, oppPts: 103, margin: 4 },
  ],
  roster: [{ id: 1628369, name: 'Jayson Tatum', number: '0', position: 'F-G', age: 28.0, experience: '9' }],
};

beforeEach(() => {
  global.ResizeObserver = class {
    observe() {}
    disconnect() {}
  };
  global.fetch = jest.fn((url) =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve(url === '/team/standings' ? standings : profile),
    })
  );
});

afterEach(() => {
  window.location.hash = '';
});

test('renders standings split by conference', async () => {
  window.location.hash = '#/teams';
  render(<App />);
  expect(await screen.findByText(/Philadelphia 76ers/)).toBeInTheDocument();
  expect(screen.getByText(/Oklahoma City Thunder/)).toBeInTheDocument();
  expect(screen.getByText('東區')).toBeInTheDocument();
  expect(screen.getByText('西區')).toBeInTheDocument();
});

test('renders a team profile with roster links to players', async () => {
  window.location.hash = '#/teams/1610612738';
  render(<App />);
  expect(await screen.findByRole('heading', { name: 'Boston Celtics' })).toBeInTheDocument();
  expect(screen.getByText('102.1')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Jayson Tatum' })).toHaveAttribute('href', '#/players/1628369');
  expect(global.fetch).toHaveBeenCalledWith('/team/1610612738/profile');
});

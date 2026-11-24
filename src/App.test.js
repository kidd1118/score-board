import { render, screen } from '@testing-library/react';
import App from './App';

const payload = {
  date: '2026-11-24',
  source: 'live',
  games: [
    {
      id: '1',
      status: 3,
      statusText: 'Final',
      period: 4,
      clock: '',
      startTimeUTC: null,
      arena: 'TD Garden',
      home: { id: 1, tricode: 'BOS', city: 'Boston', name: 'Celtics', record: '10-5', score: 110, periods: [30, 25, 30, 25] },
      away: { id: 2, tricode: 'NYK', city: 'New York', name: 'Knicks', record: '9-6', score: 101, periods: [20, 30, 26, 25] },
      leaders: { home: { name: 'Jayson Tatum', points: 30, rebounds: 9, assists: 6 }, away: null },
    },
  ],
};

beforeEach(() => {
  global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(payload) }));
});

test('renders games from the API', async () => {
  render(<App />);
  expect(await screen.findByText(/Boston Celtics/)).toBeInTheDocument();
  expect(screen.getByText('Final')).toBeInTheDocument();
  expect(screen.getByText('Jayson Tatum')).toBeTruthy();
  expect(global.fetch).toHaveBeenCalledWith('/games/');
});

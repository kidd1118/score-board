import { render, screen } from '@testing-library/react';
import App from './App';

const profile = {
  id: 1628369,
  name: 'Jayson Tatum',
  team: { id: 1610612738, tricode: 'BOS', city: 'Boston', name: 'Celtics' },
  jersey: '0',
  position: 'Forward-Guard',
  height: '6-8',
  weight: '229',
  birthdate: '1998-03-03',
  country: 'USA',
  school: 'Duke',
  experience: 9,
  fromYear: 2017,
  toYear: 2026,
  draft: { year: '2017', round: '1', number: '3' },
  active: true,
  career: { gp: 616, pts: 23.6, reb: 7.4, ast: 3.9, fg_pct: 0.457 },
  seasons: [
    { season: '2017-18', team: 'BOS', gp: 80, min: 30.5, pts: 13.9, reb: 5.0, ast: 1.6, fg_pct: 0.475 },
    { season: '2018-19', team: 'BOS', gp: 79, min: 31.1, pts: 15.7, reb: 6.0, ast: 2.1, fg_pct: 0.45 },
  ],
};

beforeEach(() => {
  global.ResizeObserver = class {
    observe() {}
    disconnect() {}
  };
  global.fetch = jest.fn((url) => {
    const body = url.startsWith('/player/1628369/profile')
      ? profile
      : { players: [{ id: 1628369, full_name: 'Jayson Tatum', is_active: true }] };
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  });
  window.location.hash = '#/players/1628369';
});

afterEach(() => {
  window.location.hash = '';
});

test('renders the selected player profile', async () => {
  render(<App />);
  expect(await screen.findByRole('heading', { name: 'Jayson Tatum' })).toBeInTheDocument();
  expect(screen.getByText('23.6')).toBeInTheDocument();
  expect(screen.getByText('2017 第 1 輪第 3 順位')).toBeInTheDocument();
  expect(screen.getByText('2018-19')).toBeInTheDocument();
  expect(global.fetch).toHaveBeenCalledWith('/player/1628369/profile');
});

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App';

const board = (date, games = []) => ({ date, source: date === '2026-11-23' ? 'live' : 'stats', games });

beforeEach(() => {
  global.fetch = jest.fn((url) => {
    const m = url.match(/date=([\d-]+)/);
    return Promise.resolve({ ok: true, json: () => Promise.resolve(board(m ? m[1] : '2026-11-23')) });
  });
});

afterEach(() => {
  window.location.hash = '';
});

test('date strip marks today and loads the clicked date', async () => {
  window.location.hash = '#/games';
  render(<App />);
  expect(await screen.findByText('今天', { selector: '.day-week' })).toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: /11\/\d+/ })).toHaveLength(7);

  fireEvent.click(screen.getByRole('button', { name: /11\/21/ }));
  await waitFor(() => expect(window.location.hash).toBe('#/games/2026-11-21'));
  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/games/?date=2026-11-21'));
  expect(await screen.findByText('這天沒有比賽')).toBeInTheDocument();
});

test('a date in the URL is loaded directly', async () => {
  window.location.hash = '#/games/2026-11-20';
  render(<App />);
  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/games/?date=2026-11-20'));
  expect(await screen.findByRole('button', { name: /11\/20/, current: 'date' })).toBeInTheDocument();
});

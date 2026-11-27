import { useEffect, useState } from 'react';
import './App.css';
import GamesDashboard from './GamesDashboard';
import PlayersDashboard from './PlayersDashboard';
import TeamsDashboard from './TeamsDashboard';
import FantasyDashboard from './FantasyDashboard';
import GameDetail from './GameDetail';

const PAGES = [
  { key: 'games', label: 'Games' },
  { key: 'teams', label: 'Teams' },
  { key: 'players', label: 'Players' },
  { key: 'fantasy', label: 'Daily Fantasy' },
];

// Routes live in the URL hash so a refresh keeps the current view:
// #/games, #/games/<date>, #/game/<date>/<gameId>, #/teams, #/teams/<teamId>,
// #/players, #/players/<playerId>, #/fantasy, #/fantasy/<date>
function parseHash() {
  const [, page, param, extra] = window.location.hash.split('/');
  if (page === 'game' && /^\d{4}-\d{2}-\d{2}$/.test(param || '') && /^\w+$/.test(extra || '')) {
    return { page: 'game', id: null, date: param, gameId: extra };
  }
  return {
    page: PAGES.some((p) => p.key === page) ? page : 'games',
    id: param && /^\d+$/.test(param) ? Number(param) : null,
    date: param && /^\d{4}-\d{2}-\d{2}$/.test(param) ? param : null,
  };
}

function App() {
  const [route, setRoute] = useState(parseHash);

  useEffect(() => {
    const onHash = () => {
      setRoute(parseHash());
      window.scrollTo(0, 0);
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  return (
    <>
      <nav className="tabs">
        <a href="#/games" className="brand" aria-label="N.Baccarat.A Dashboard 首頁">
          <img src={`${process.env.PUBLIC_URL}/logo.svg`} alt="" width="32" height="32" />
          <span>N.Baccarat.A Dashboard</span>
        </a>
        {PAGES.map((p) => (
          <a
            key={p.key}
            href={`#/${p.key}`}
            className={route.page === p.key || (route.page === 'game' && p.key === 'games') ? 'active' : ''}
          >
            {p.label}
          </a>
        ))}
      </nav>
      {route.page === 'games' && (
        <GamesDashboard
          date={route.date}
          onDateChange={(d) => (window.location.hash = d ? `#/games/${d}` : '#/games')}
        />
      )}
      {route.page === 'game' && <GameDetail date={route.date} gameId={route.gameId} />}
      {route.page === 'teams' && <TeamsDashboard selectedId={route.id} />}
      {route.page === 'fantasy' && (
        <FantasyDashboard
          date={route.date}
          onDateChange={(d) => (window.location.hash = d ? `#/fantasy/${d}` : '#/fantasy')}
        />
      )}
      {route.page === 'players' && (
        <PlayersDashboard
          selectedId={route.id}
          onSelect={(id) => (window.location.hash = `#/players/${id}`)}
        />
      )}
    </>
  );
}

export default App;

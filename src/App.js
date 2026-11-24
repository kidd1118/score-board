import { useEffect, useState } from 'react';
import './App.css';
import GamesDashboard from './GamesDashboard';
import PlayersDashboard from './PlayersDashboard';
import TeamsDashboard from './TeamsDashboard';

const PAGES = [
  { key: 'games', label: '比賽' },
  { key: 'teams', label: '球隊' },
  { key: 'players', label: '球員' },
];

// Routes live in the URL hash so a refresh keeps the current view:
// #/games, #/teams, #/teams/<teamId>, #/players, #/players/<playerId>
function parseHash() {
  const [, page, id] = window.location.hash.split('/');
  return {
    page: PAGES.some((p) => p.key === page) ? page : 'games',
    id: id ? Number(id) : null,
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
        {PAGES.map((p) => (
          <a key={p.key} href={`#/${p.key}`} className={route.page === p.key ? 'active' : ''}>
            {p.label}
          </a>
        ))}
      </nav>
      {route.page === 'games' && <GamesDashboard />}
      {route.page === 'teams' && <TeamsDashboard selectedId={route.id} />}
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

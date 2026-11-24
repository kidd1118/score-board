import { useEffect, useState } from 'react';
import './App.css';
import GamesDashboard from './GamesDashboard';
import PlayersDashboard from './PlayersDashboard';

// Routes live in the URL hash so a refresh keeps the current view:
// #/games, #/players, #/players/<playerId>
function parseHash() {
  const [, page = 'games', id] = window.location.hash.split('/');
  return { page: page === 'players' ? 'players' : 'games', playerId: id ? Number(id) : null };
}

function App() {
  const [route, setRoute] = useState(parseHash);

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  return (
    <>
      <nav className="tabs">
        <a href="#/games" className={route.page === 'games' ? 'active' : ''}>比賽</a>
        <a href="#/players" className={route.page === 'players' ? 'active' : ''}>球員</a>
      </nav>
      {route.page === 'games' ? (
        <GamesDashboard />
      ) : (
        <PlayersDashboard
          selectedId={route.playerId}
          onSelect={(id) => (window.location.hash = `#/players/${id}`)}
        />
      )}
    </>
  );
}

export default App;

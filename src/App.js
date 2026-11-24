import { useCallback, useEffect, useMemo, useState } from 'react';
import './App.css';

const REFRESH_MS = 30000;
const STATUS = { SCHEDULED: 1, LIVE: 2, FINAL: 3 };
const FILTERS = [
  { key: 'all', label: '全部' },
  { key: STATUS.LIVE, label: '進行中' },
  { key: STATUS.FINAL, label: '已結束' },
  { key: STATUS.SCHEDULED, label: '未開始' },
];

function shiftDate(iso, days) {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function periodLabel(i) {
  return i < 4 ? `Q${i + 1}` : `OT${i - 3}`;
}

function formatStart(utc) {
  if (!utc) return null;
  return new Date(utc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function TeamRow({ team, winner, showScore }) {
  return (
    <div className={`team-row ${winner ? 'winner' : ''}`}>
      <span className="tricode">{team.tricode}</span>
      <span className="team-name">
        {team.city} {team.name}
        <small>{team.record}</small>
      </span>
      {showScore && <span className="score">{team.score ?? '-'}</span>}
    </div>
  );
}

function Leader({ tricode, leader }) {
  if (!leader) return null;
  return (
    <li>
      <span className="leader-team">{tricode}</span> {leader.name}
      <span className="leader-stats">
        {leader.points} PTS · {leader.rebounds} REB · {leader.assists} AST
      </span>
    </li>
  );
}

function GameCard({ game }) {
  const { home, away, status } = game;
  const started = status !== STATUS.SCHEDULED;
  const homeWin = status === STATUS.FINAL && home.score > away.score;
  const awayWin = status === STATUS.FINAL && away.score > home.score;
  const periods = Math.max(home.periods?.length || 0, away.periods?.length || 0);
  const start = formatStart(game.startTimeUTC);

  let badge = game.statusText;
  if (status === STATUS.LIVE && game.clock) badge = `${game.statusText} ${game.clock}`.trim();
  if (status === STATUS.SCHEDULED && start) badge = start;

  return (
    <article className={`game-card status-${status}`}>
      <header>
        <span className={`badge badge-${status}`}>
          {status === STATUS.LIVE && <span className="dot" />}
          {badge}
        </span>
        {game.arena && <span className="arena">{game.arena}</span>}
      </header>

      <TeamRow team={away} winner={awayWin} showScore={started} />
      <TeamRow team={home} winner={homeWin} showScore={started} />

      {started && periods > 0 && (
        <table className="linescore">
          <thead>
            <tr>
              <th />
              {Array.from({ length: periods }, (_, i) => (
                <th key={i}>{periodLabel(i)}</th>
              ))}
              <th>T</th>
            </tr>
          </thead>
          <tbody>
            {[away, home].map((t) => (
              <tr key={t.id}>
                <td>{t.tricode}</td>
                {Array.from({ length: periods }, (_, i) => (
                  <td key={i}>
                    {status === STATUS.LIVE && i >= game.period ? '' : t.periods?.[i] ?? ''}
                  </td>
                ))}
                <td className="total">{t.score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {started && (game.leaders.home || game.leaders.away) && (
        <ul className="leaders">
          <Leader tricode={away.tricode} leader={game.leaders.away} />
          <Leader tricode={home.tricode} leader={game.leaders.home} />
        </ul>
      )}
    </article>
  );
}

function App() {
  const [date, setDate] = useState(null); // null = today's live board
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('all');
  const [updatedAt, setUpdatedAt] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(date ? `/games/?date=${date}` : '/games/');
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || res.statusText);
      setData(body);
      setError(null);
      setUpdatedAt(new Date());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => {
    load();
  }, [load]);

  const hasLive = data?.games.some((g) => g.status === STATUS.LIVE);
  useEffect(() => {
    if (!hasLive) return undefined;
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [hasLive, load]);

  const counts = useMemo(() => {
    const c = { all: 0, [STATUS.LIVE]: 0, [STATUS.FINAL]: 0, [STATUS.SCHEDULED]: 0 };
    data?.games.forEach((g) => {
      c.all += 1;
      c[g.status] = (c[g.status] || 0) + 1;
    });
    return c;
  }, [data]);

  const games = (data?.games || []).filter((g) => filter === 'all' || g.status === filter);
  const shownDate = date || data?.date;

  return (
    <div className="dashboard">
      <header className="top-bar">
        <h1>NBA Games</h1>
        <div className="date-nav">
          <button onClick={() => shownDate && setDate(shiftDate(shownDate, -1))} disabled={!shownDate}>
            ‹
          </button>
          <input
            type="date"
            value={shownDate || ''}
            onChange={(e) => setDate(e.target.value || null)}
          />
          <button onClick={() => shownDate && setDate(shiftDate(shownDate, 1))} disabled={!shownDate}>
            ›
          </button>
          <button className="today" onClick={() => setDate(null)} disabled={date === null}>
            今天
          </button>
          <button onClick={load} disabled={loading}>
            {loading ? '載入中…' : '重新整理'}
          </button>
        </div>
      </header>

      <section className="summary">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            className={`stat ${filter === f.key ? 'active' : ''}`}
            onClick={() => setFilter(f.key)}
          >
            <span className="stat-value">{counts[f.key] || 0}</span>
            <span className="stat-label">{f.label}</span>
          </button>
        ))}
      </section>

      {updatedAt && (
        <p className="meta">
          更新於 {updatedAt.toLocaleTimeString()}
          {hasLive && ` · 每 ${REFRESH_MS / 1000} 秒自動更新`}
        </p>
      )}

      {error && <div className="error">無法取得比賽資料：{error}</div>}

      {!error && data && games.length === 0 && <div className="empty">這天沒有比賽</div>}

      <main className="games-grid">
        {games.map((g) => (
          <GameCard key={g.id} game={g} />
        ))}
      </main>
    </div>
  );
}

export default App;

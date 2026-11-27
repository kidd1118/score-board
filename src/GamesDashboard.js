import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { readJson } from './readJson';
import DateStrip from './DateStrip';

const REFRESH_MS = 30000;
const STATUS = { SCHEDULED: 1, LIVE: 2, FINAL: 3 };
const FILTERS = [
  { key: 'all', label: '全部' },
  { key: STATUS.LIVE, label: '進行中' },
  { key: STATUS.FINAL, label: '已結束' },
  { key: STATUS.SCHEDULED, label: '未開始' },
];

function periodLabel(i) {
  return i < 4 ? `Q${i + 1}` : `OT${i - 3}`;
}

// Local tip-off time; includes the local date because in Asia it is usually the next morning.
function formatStart(utc) {
  if (!utc) return null;
  return new Date(utc).toLocaleString([], {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
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

function FantasyLeader({ tricode, leader }) {
  if (!leader) return null;
  return (
    <li>
      <span className="leader-team">{tricode}</span> {leader.name}
      <span className="leader-stats">
        <strong>{leader.points}</strong> 分
      </span>
    </li>
  );
}

/** `date` links the card to its game page; `fantasy` holds each team's best fantasy scorer. */
export function GameCard({ game, date, fantasy, linked = true }) {
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

      {started && fantasy && (fantasy.home || fantasy.away) && (
        <div className="fantasy-leaders">
          <span className="meta">
            Fantasy 積分最高
            {status === STATUS.LIVE && <span className="live-tag">即時</span>}
          </span>
          <ul className="leaders">
            <FantasyLeader tricode={away.tricode} leader={fantasy.away} />
            <FantasyLeader tricode={home.tricode} leader={fantasy.home} />
          </ul>
        </div>
      )}

      {linked && date && started && (
        <a className="card-link" href={`#/game/${date}/${game.id}`}>
          完整數據與積分 ›
        </a>
      )}
    </article>
  );
}

/**
 * `date` (YYYY-MM-DD, US date) comes from the URL; null means today's live board.
 * `onDateChange(null | iso)` updates the URL.
 */
export default function GamesDashboard({ date = null, onDateChange }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('all');
  const [updatedAt, setUpdatedAt] = useState(null);
  const [liveDate, setLiveDate] = useState(null);
  const [fantasy, setFantasy] = useState(null);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    try {
      const res = await fetch(date ? `/games/?date=${date}` : '/games/');
      const body = await readJson(res);
      if (id !== requestId.current) return; // a newer date was requested meanwhile
      setData(body);
      setError(null);
      setUpdatedAt(new Date());
      if (body.source === 'live') setLiveDate(body.date);
      // Each started game's best fantasy scorers; the cards work without them.
      if (body.games.some((g) => g.status !== STATUS.SCHEDULED)) {
        fetch(`/fantasy/${body.date}/game-leaders`)
          .then((r) => readJson(r))
          .then((f) => id === requestId.current && setFantasy(f.games))
          .catch(() => {});
      }
    } catch (e) {
      if (id === requestId.current) setError(e.message);
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [date]);

  useEffect(() => {
    setData(null);
    setError(null);
    setFantasy(null);
    load();
  }, [load]);

  // Learn which US date the live board is on, so the strip can mark "今天".
  useEffect(() => {
    if (liveDate || date === null) return;
    fetch('/games/')
      .then((res) => (res.ok ? res.json() : null))
      .then((body) => body && setLiveDate(body.date))
      .catch(() => {});
  }, [date, liveDate]);

  const selectDate = (iso) => onDateChange(iso && iso === liveDate ? null : iso);

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
  const shownDate = date || data?.date || liveDate;

  return (
    <div className="dashboard">
      <header className="top-bar">
        <h1>NBA Games</h1>
        <div className="date-nav">
          <input
            type="date"
            aria-label="跳到日期"
            value={shownDate || ''}
            onChange={(e) => selectDate(e.target.value || null)}
          />
          <button className="today" onClick={() => onDateChange(null)} disabled={date === null}>
            今天
          </button>
          <button onClick={load} disabled={loading}>
            {loading ? '載入中…' : '重新整理'}
          </button>
        </div>
      </header>

      {shownDate && <DateStrip selected={shownDate} today={liveDate} onSelect={selectDate} />}

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
          日期為美國當地日期，開賽時間已換算為你的時區 · 更新於 {updatedAt.toLocaleTimeString()}
          {hasLive && ` · 每 ${REFRESH_MS / 1000} 秒自動更新`}
        </p>
      )}

      {error && <div className="error">無法取得比賽資料：{error}</div>}

      {!error && !data && loading && <div className="empty">載入中…</div>}

      {!error && data && games.length === 0 && (
        <div className="empty">{data.games.length ? '沒有符合篩選的比賽' : '這天沒有比賽'}</div>
      )}

      <main className="games-grid">
        {games.map((g) => (
          <GameCard key={g.id} game={g} date={data.date} fantasy={fantasy?.[g.id]} />
        ))}
      </main>
    </div>
  );
}

import { useEffect, useMemo, useState } from 'react';
import { readJson } from './readJson';
import SeasonChart from './SeasonChart';

const MAX_RESULTS = 100;
const METRICS = [
  { key: 'pts', label: '得分' },
  { key: 'reb', label: '籃板' },
  { key: 'ast', label: '助攻' },
  { key: 'min', label: '上場時間' },
];

const num = (v) => (v == null ? '-' : Number(v).toFixed(1));
const pct = (v) => (v == null ? '-' : `${(v * 100).toFixed(1)}%`);
const fmtTick = (v) => (Number.isInteger(v) ? String(v) : v.toFixed(1));

function headshot(id) {
  return `https://cdn.nba.com/headshots/nba/latest/260x190/${id}.png`;
}

/** One row per season for the chart; traded players keep only the combined "TOT" row. */
function chartSeasons(seasons) {
  const bySeason = new Map();
  seasons.forEach((s) => {
    if (!bySeason.has(s.season) || s.team === 'TOT') bySeason.set(s.season, s);
  });
  return [...bySeason.values()];
}

function PlayerList({ players, selectedId, onSelect }) {
  const [query, setQuery] = useState('');
  const [activeOnly, setActiveOnly] = useState(true);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return players.filter(
      (p) => (!activeOnly || p.is_active) && (!q || p.full_name.toLowerCase().includes(q))
    );
  }, [players, query, activeOnly]);

  return (
    <aside className="player-list">
      <input
        type="search"
        placeholder="搜尋球員姓名…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <label className="toggle">
        <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} />
        只顯示現役球員
      </label>
      <p className="meta">
        {matches.length} 位球員
        {matches.length > MAX_RESULTS && `，顯示前 ${MAX_RESULTS} 位`}
      </p>
      <ul>
        {matches.slice(0, MAX_RESULTS).map((p) => (
          <li key={p.id}>
            <button className={p.id === selectedId ? 'selected' : ''} onClick={() => onSelect(p.id)}>
              {p.full_name}
              {!p.is_active && <small>退役</small>}
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}

function PlayerProfile({ playerId }) {
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState(null);
  const [metric, setMetric] = useState('pts');

  useEffect(() => {
    let cancelled = false;
    setProfile(null);
    setError(null);
    fetch(`/player/${playerId}/profile`)
      .then(async (res) => {
        const body = await readJson(res);
        if (!cancelled) setProfile(body);
      })
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [playerId]);

  if (error) return <div className="error">無法取得球員資料：{error}</div>;
  if (!profile) return <div className="empty">載入中…</div>;

  const p = profile;
  const c = p.career || {};
  const draft = p.draft.year && p.draft.year !== 'Undrafted'
    ? `${p.draft.year} 第 ${p.draft.round} 輪第 ${p.draft.number} 順位`
    : '未經選秀';
  const bio = [
    ['身高', p.height],
    ['體重', p.weight && `${p.weight} lb`],
    ['生日', p.birthdate],
    ['國籍', p.country],
    ['學校', p.school],
    ['選秀', draft],
    ['年資', p.fromYear && `${p.fromYear}–${p.toYear}（${p.experience} 季）`],
  ];
  const metricLabel = METRICS.find((m) => m.key === metric).label;

  return (
    <section className="player-profile">
      <header className="profile-head">
        <img src={headshot(p.id)} alt="" onError={(e) => (e.currentTarget.style.display = 'none')} />
        <div>
          <h2>{p.name}</h2>
          <p className="meta">
            {p.team.city ? `${p.team.city} ${p.team.name}` : '自由球員 / 退役'}
            {p.jersey && ` · #${p.jersey}`}
            {p.position && ` · ${p.position}`}
          </p>
        </div>
      </header>

      <dl className="bio">
        {bio.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v || '-'}</dd>
          </div>
        ))}
      </dl>

      <h3>生涯例行賽平均</h3>
      <div className="summary career">
        {[
          ['得分', num(c.pts)],
          ['籃板', num(c.reb)],
          ['助攻', num(c.ast)],
          ['投籃命中率', pct(c.fg_pct)],
          ['出賽', c.gp ?? '-'],
        ].map(([label, value]) => (
          <div className="stat" key={label}>
            <span className="stat-value">{value}</span>
            <span className="stat-label">{label}</span>
          </div>
        ))}
      </div>

      {p.seasons.length > 0 && (
        <>
          <div className="chart-head">
            <h3>每季平均{metricLabel}</h3>
            <div className="segmented">
              {METRICS.map((m) => (
                <button
                  key={m.key}
                  className={metric === m.key ? 'active' : ''}
                  onClick={() => setMetric(m.key)}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
          <SeasonChart seasons={chartSeasons(p.seasons)} metric={metric} format={fmtTick} />

          <h3>逐季數據（例行賽）</h3>
          <div className="table-wrap">
            <table className="season-table">
              <thead>
                <tr>
                  <th>球季</th><th>球隊</th><th>出賽</th><th>時間</th><th>得分</th><th>籃板</th>
                  <th>助攻</th><th>抄截</th><th>阻攻</th><th>失誤</th><th>FG%</th><th>3P%</th><th>FT%</th>
                </tr>
              </thead>
              <tbody>
                {[...p.seasons].reverse().map((s, i) => (
                  <tr key={`${s.season}-${s.team}-${i}`} className={s.team === 'TOT' ? 'tot' : ''}>
                    <td>{s.season}</td><td>{s.team}</td><td>{s.gp}</td><td>{num(s.min)}</td>
                    <td>{num(s.pts)}</td><td>{num(s.reb)}</td><td>{num(s.ast)}</td><td>{num(s.stl)}</td>
                    <td>{num(s.blk)}</td><td>{num(s.tov)}</td><td>{pct(s.fg_pct)}</td>
                    <td>{pct(s.fg3_pct)}</td><td>{pct(s.ft_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

export default function PlayersDashboard({ selectedId, onSelect }) {
  const [players, setPlayers] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch('/player/')
      .then(async (res) => {
        const body = await readJson(res);
        setPlayers([...body.players].sort((a, b) => a.full_name.localeCompare(b.full_name)));
      })
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="dashboard">
      <header className="top-bar">
        <h1>NBA Players</h1>
      </header>
      {error && <div className="error">無法取得球員名單：{error}</div>}
      <div className="players-layout">
        <PlayerList players={players} selectedId={selectedId} onSelect={onSelect} />
        {selectedId ? (
          <PlayerProfile playerId={selectedId} />
        ) : (
          <div className="empty">從左側選擇一位球員</div>
        )}
      </div>
    </div>
  );
}

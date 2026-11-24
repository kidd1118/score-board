import { useCallback, useEffect, useMemo, useState } from 'react';
import DateStrip from './DateStrip';

const SLOT_LABELS = { PG: '控球後衛', SG: '得分後衛', SF: '小前鋒', PF: '大前鋒', C: '中鋒', '6TH': '第六人' };
const RULES = [
  ['得分', '×2'],
  ['籃板', '×3'],
  ['助攻', '×4'],
  ['抄截', '×5'],
  ['火鍋', '×5'],
  ['失誤', '×−2'],
];
const STAT_LABELS = [
  ['pts', '分'],
  ['reb', '板'],
  ['ast', '助'],
  ['stl', '抄'],
  ['blk', '鍋'],
  ['tov', '失誤'],
];
const MAX_POOL_ROWS = 80;
const REFRESH_MS = 30000;
const SCHEDULED = 1;
const LIVE = 2;

async function request(url, options) {
  const res = await fetch(url, options);
  const body = await res.json();
  if (!res.ok) throw new Error(body.detail || res.statusText);
  return body;
}

function formatStart(utc) {
  if (!utc) return '';
  return new Date(utc).toLocaleString([], { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function gameLabel(game) {
  if (!game) return '';
  const vs = `${game.home ? 'vs' : '@'} ${game.opponent}`;
  const when = game.status === SCHEDULED ? formatStart(game.startTimeUTC) || game.statusText : game.statusText;
  return `${vs} · ${when}`;
}

function statLine(stats) {
  return STAT_LABELS.map(([k, label]) => `${stats[k] ?? 0}${label}`).join(' ');
}

function avgLine(avg) {
  return STAT_LABELS.map(([k, label]) => `${Number(avg[k] ?? 0).toFixed(1)}${label}`).join(' ');
}

function SlotCard({ slot, active, editable, onPick, onRemove }) {
  const { player, game, stats, points, locked } = slot;
  return (
    <article className={`slot-card ${active ? 'active' : ''} ${game?.status === LIVE ? 'live' : ''}`}>
      <header>
        <span className="slot-name">{slot.slot}</span>
        <span className="slot-label">{SLOT_LABELS[slot.slot]}</span>
        {player && <span className="slot-points">{stats ? points : '–'}</span>}
      </header>
      {player ? (
        <>
          <div className="slot-player">{player.name}</div>
          <div className="meta">
            {player.team} · {player.position} · {gameLabel(game)}
          </div>
          {stats &&
            (stats.played ? (
              <div className="slot-stats">{statLine(stats)}</div>
            ) : (
              <div className="slot-stats muted">{game?.status === 3 ? '未上場（0 分）' : '尚未上場'}</div>
            ))}
        </>
      ) : (
        <div className="slot-empty">尚未選擇</div>
      )}
      <div className="slot-actions">
        {locked ? (
          <span className="lock">比賽已開始，已鎖定</span>
        ) : (
          editable && (
            <>
              <button onClick={onPick}>{player ? '更換' : '選擇球員'}</button>
              {player && (
                <button className="ghost" onClick={onRemove}>
                  移除
                </button>
              )}
            </>
          )
        )}
      </div>
    </article>
  );
}

function PlayerPicker({ slot, pool, pickedIds, saving, onChoose, onClose }) {
  const [query, setQuery] = useState('');
  const candidates = useMemo(() => {
    const q = query.trim().toLowerCase();
    return pool.players.filter(
      (p) => p.slots.includes(slot) && (!q || p.name.toLowerCase().includes(q) || p.team?.toLowerCase() === q)
    );
  }, [pool, slot, query]);

  return (
    <section className="picker">
      <header>
        <h3>
          選擇 {slot}（{SLOT_LABELS[slot]}）
        </h3>
        <button className="ghost" onClick={onClose}>
          關閉
        </button>
      </header>
      <input
        type="search"
        placeholder="搜尋球員姓名或球隊縮寫（例如 BOS）…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        autoFocus
      />
      <p className="meta">
        {candidates.length} 位可選球員，依本季平均積分排序
        {candidates.length > MAX_POOL_ROWS && `，顯示前 ${MAX_POOL_ROWS} 位`}
      </p>
      <ul>
        {candidates.slice(0, MAX_POOL_ROWS).map((p) => {
          const picked = pickedIds.has(p.id);
          return (
            <li key={p.id}>
              <button disabled={p.locked || picked || saving} onClick={() => onChoose(p.id)}>
                <span className="pick-main">
                  <strong>{p.name}</strong>
                  <span className="meta">
                    {p.team} · {p.position} · {gameLabel(p.game)}
                  </span>
                  <span className="meta">
                    平均 {avgLine(p.avg)} · {p.gp} 場
                  </span>
                </span>
                <span className="pick-side">
                  {p.locked ? '已開賽' : picked ? '已在陣容' : <strong>{p.avgPoints}</strong>}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function History({ history, current, onSelect }) {
  if (!history?.length) return null;
  return (
    <section className="standings history">
      <h3>歷史紀錄</h3>
      <table className="data-table games-table">
        <thead>
          <tr>
            <th>日期</th>
            <th>球員數</th>
            <th>狀態</th>
            <th>積分</th>
          </tr>
        </thead>
        <tbody>
          {history.map((h) => (
            <tr key={h.date} className={h.date === current ? 'current' : ''} onClick={() => onSelect(h.date)}>
              <td>{h.date}</td>
              <td>{h.players} / 6</td>
              <td>{h.final ? '已結算' : '未結算'}</td>
              <td>{h.total}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

/** `date` (YYYY-MM-DD, US date) comes from the URL; null means the live board's date. */
export default function FantasyDashboard({ date = null, onDateChange }) {
  const [liveDate, setLiveDate] = useState(null);
  const [lineup, setLineup] = useState(null);
  const [pool, setPool] = useState(null);
  const [history, setHistory] = useState(null);
  const [activeSlot, setActiveSlot] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    request('/games/')
      .then((body) => setLiveDate(body.date))
      .catch((e) => setError(e.message));
  }, []);

  const day = date || liveDate;

  const loadLineup = useCallback(() => {
    if (!day) return;
    request(`/fantasy/${day}`)
      .then((body) => {
        setLineup((prev) => (body.date === day ? body : prev));
        setError(null);
      })
      .catch((e) => setError(e.message));
  }, [day]);

  const loadHistory = useCallback(() => {
    request('/fantasy/history')
      .then((body) => setHistory(body.history))
      .catch(() => {});
  }, []);

  useEffect(() => {
    setLineup(null);
    setPool(null);
    setActiveSlot(null);
    loadLineup();
  }, [loadLineup]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // Fetch the player pool the first time a slot is opened for this day.
  useEffect(() => {
    if (!activeSlot || pool || !day) return;
    request(`/fantasy/${day}/pool`)
      .then((body) => body.date === day && setPool(body))
      .catch((e) => setError(e.message));
  }, [activeSlot, pool, day]);

  const anyLive = lineup?.slots.some((s) => s.game?.status === LIVE);
  useEffect(() => {
    if (!anyLive) return undefined;
    const id = setInterval(loadLineup, REFRESH_MS);
    return () => clearInterval(id);
  }, [anyLive, loadLineup]);

  const save = async (slot, playerId) => {
    const slots = Object.fromEntries(lineup.slots.map((s) => [s.slot, s.player?.id ?? null]));
    slots[slot] = playerId;
    setSaving(true);
    try {
      const body = await request(`/fantasy/${day}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slots }),
      });
      setLineup(body);
      setActiveSlot(null);
      setError(null);
      loadHistory();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const selectDate = (iso) => onDateChange(iso && iso === liveDate ? null : iso);
  const pickedIds = new Set((lineup?.slots || []).filter((s) => s.player).map((s) => s.player.id));
  const filled = pickedIds.size;
  const started = (lineup?.slots || []).filter((s) => s.locked).length;
  const editable = lineup && !lineup.final;

  return (
    <div className="dashboard">
      <header className="top-bar">
        <h1>每日小遊戲</h1>
        <div className="date-nav">
          <input type="date" aria-label="跳到日期" value={day || ''} onChange={(e) => selectDate(e.target.value || null)} />
          <button className="today" onClick={() => onDateChange(null)} disabled={date === null}>
            今天
          </button>
        </div>
      </header>

      {day && <DateStrip selected={day} today={liveDate} onSelect={selectDate} />}

      <section className="rules">
        <span className="meta">積分規則：</span>
        {RULES.map(([label, weight]) => (
          <span key={label} className="rule">
            {label} <strong>{weight}</strong>
          </span>
        ))}
      </section>

      {error && <div className="error">{error}</div>}

      {!lineup && !error && <div className="empty">載入中…</div>}

      {lineup && (
        <>
          <section className="summary fantasy-summary">
            <div className="stat">
              <span className="stat-value">{lineup.total}</span>
              <span className="stat-label">{lineup.final ? '本日總積分（已結算）' : '本日總積分'}</span>
            </div>
            <div className="stat">
              <span className="stat-value">{filled} / 6</span>
              <span className="stat-label">已選球員</span>
            </div>
            <div className="stat">
              <span className="stat-value">{started}</span>
              <span className="stat-label">已鎖定（比賽已開始）</span>
            </div>
          </section>
          <p className="meta">
            每位球員在他的比賽開始後鎖定，不能再換下或選入
            {anyLive && ` · 比賽進行中，每 ${REFRESH_MS / 1000} 秒更新積分`}
          </p>

          <div className="fantasy-layout">
            <div className="slots-grid">
              {lineup.slots.map((s) => (
                <SlotCard
                  key={s.slot}
                  slot={s}
                  active={activeSlot === s.slot}
                  editable={editable && !saving}
                  onPick={() => setActiveSlot(s.slot)}
                  onRemove={() => save(s.slot, null)}
                />
              ))}
            </div>

            {activeSlot &&
              (pool ? (
                <PlayerPicker
                  slot={activeSlot}
                  pool={pool}
                  pickedIds={pickedIds}
                  saving={saving}
                  onChoose={(id) => save(activeSlot, id)}
                  onClose={() => setActiveSlot(null)}
                />
              ) : (
                <section className="picker">
                  <div className="empty">載入球員名單…</div>
                </section>
              ))}
          </div>
        </>
      )}

      <History history={history} current={day} onSelect={selectDate} />
    </div>
  );
}

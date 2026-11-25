import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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

const TOKEN_KEY = 'fantasy-token';

function readToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function writeToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // storage blocked: the player stays signed in until the page reloads
  }
}

async function request(url, { token, headers, ...options } = {}) {
  const res = await fetch(url, {
    ...options,
    headers: { ...headers, ...(token ? { 'X-Fantasy-Token': token } : {}) },
  });
  const body = await res.json();
  if (!res.ok) {
    const error = new Error(body.detail || res.statusText);
    error.status = res.status;
    throw error;
  }
  return body;
}

const SORTS = {
  points: { label: '平均積分', compare: (a, b) => b.avgPoints - a.avgPoints },
  value: { label: '性價比（每百萬積分）', compare: (a, b) => valueOf(b) - valueOf(a) },
  salaryDesc: { label: '薪資高→低', compare: (a, b) => b.salary - a.salary },
  salaryAsc: { label: '薪資低→高', compare: (a, b) => a.salary - b.salary },
};

function valueOf(p) {
  return p.salary ? p.avgPoints / (p.salary / 1e6) : 0;
}

/** $62,587,158 -> "$62.59M" */
export function money(amount) {
  const sign = amount < 0 ? '−' : '';
  return `${sign}$${(Math.abs(amount) / 1e6).toFixed(2)}M`;
}

const fullMoney = (amount) => `$${amount.toLocaleString('en-US')}`;

// Severity drives the badge color; the label always says the status in words.
const INJURY_SEVERITY = {
  OFS: 'critical',
  OUT: 'critical',
  DOUBTFUL: 'serious',
  GTD: 'warning',
  QUESTIONABLE: 'warning',
  PROBABLE: 'good',
};
const UNAVAILABLE = new Set(['OUT', 'OFS']);

function InjuryBadge({ injury }) {
  if (!injury) return null;
  const source = injury.source === 'NBA' ? 'NBA 官方傷兵報告' : 'ESPN';
  return (
    <span
      className={`injury injury-${INJURY_SEVERITY[injury.status] || 'warning'}`}
      title={`${injury.label}${injury.reason ? `：${injury.reason}` : ''}（${source}）`}
    >
      {injury.label}
    </span>
  );
}

function formatReportTime(iso) {
  // The report's timestamp is Eastern Time without an offset; show it as published.
  const [date, time] = iso.split('T');
  const [, month, day] = date.split('-');
  const [hour, minute] = time.split(':').map(Number);
  const h12 = hour % 12 || 12;
  return `${Number(month)}/${Number(day)} ${h12}:${String(minute).padStart(2, '0')} ${hour < 12 ? 'AM' : 'PM'} ET`;
}

const sameName = (a, b) => !!a && !!b && a.toLowerCase() === b.toLowerCase();
const lineupUrl = (day, name) => `/fantasy/${day}/lineup/${encodeURIComponent(name)}`;

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
          <div className="slot-player">
            {player.name} <InjuryBadge injury={slot.injury} />
          </div>
          {slot.injury?.reason && <div className="meta injury-reason">{slot.injury.reason}</div>}
          <div className="meta">
            {player.team} · {player.position} · <span title={fullMoney(player.salary)}>{money(player.salary)}</span> ·{' '}
            {gameLabel(game)}
          </div>
          {stats &&
            (stats.played ? (
              <div className="slot-stats">{statLine(stats)}</div>
            ) : (
              <div className="slot-stats muted">{game?.status === 3 ? '未上場（0 分）' : '尚未上場'}</div>
            ))}
        </>
      ) : slot.hidden ? (
        <div className="slot-empty">已選擇，開賽後公開</div>
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

/** `budget` is the most this slot's player may earn: cap room plus the salary of whoever it replaces. */
function PlayerPicker({ slot, pool, pickedIds, budget, saving, onChoose, onClose }) {
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState('points');
  const [affordableOnly, setAffordableOnly] = useState(false);
  const [hideOut, setHideOut] = useState(false);
  const candidates = useMemo(() => {
    const q = query.trim().toLowerCase();
    return pool.players
      .filter(
        (p) =>
          p.slots.includes(slot) &&
          (!affordableOnly || p.salary <= budget) &&
          (!hideOut || !UNAVAILABLE.has(p.injury?.status)) &&
          (!q || p.name.toLowerCase().includes(q) || p.team?.toLowerCase() === q)
      )
      .sort(SORTS[sort].compare);
  }, [pool, slot, query, sort, affordableOnly, hideOut, budget]);

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
      <div className="picker-tools">
        <select aria-label="排序" value={sort} onChange={(e) => setSort(e.target.value)}>
          {Object.entries(SORTS).map(([key, s]) => (
            <option key={key} value={key}>
              依{s.label}
            </option>
          ))}
        </select>
        <label>
          <input type="checkbox" checked={affordableOnly} onChange={(e) => setAffordableOnly(e.target.checked)} />
          只顯示薪資內
        </label>
        <label>
          <input type="checkbox" checked={hideOut} onChange={(e) => setHideOut(e.target.checked)} />
          隱藏 Out 球員
        </label>
      </div>
      <p className="meta">
        這個位置最多可用 <strong title={fullMoney(budget)}>{money(budget)}</strong> · {candidates.length} 位球員
        {candidates.length > MAX_POOL_ROWS && `，顯示前 ${MAX_POOL_ROWS} 位`}
      </p>
      <ul>
        {candidates.slice(0, MAX_POOL_ROWS).map((p) => {
          const picked = pickedIds.has(p.id);
          const tooExpensive = p.salary > budget;
          return (
            <li key={p.id}>
              <button disabled={p.locked || picked || tooExpensive || saving} onClick={() => onChoose(p.id)}>
                <span className="pick-main">
                  <span className="pick-name">
                    <strong>{p.name}</strong> <InjuryBadge injury={p.injury} />
                  </span>
                  {p.injury?.reason && <span className="meta injury-reason">{p.injury.reason}</span>}
                  <span className="meta">
                    {p.team} · {p.position} · {gameLabel(p.game)}
                  </span>
                  <span className="meta">
                    平均 {avgLine(p.avg)} · {p.gp} 場
                  </span>
                </span>
                <span className="pick-side">
                  <span title={`${fullMoney(p.salary)}${p.salaryListed ? '' : '（未列入合約名單，以新秀底薪計）'}`}>
                    {money(p.salary)}
                    {!p.salaryListed && '*'}
                  </span>
                  <span>
                    {p.locked ? '已開賽' : picked ? '已在陣容' : tooExpensive ? '超出薪資' : <strong>{p.avgPoints} 分</strong>}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <p className="meta injury-source">
        {pool.injuryReport?.official
          ? `傷兵狀態：NBA 官方傷兵報告（${formatReportTime(pool.injuryReport.official.published)} 更新）${
              pool.injuryReport.espn ? '，尚未列入報告的球隊以 ESPN 補充' : ''
            }`
          : pool.injuryReport?.espn
            ? '傷兵狀態：ESPN（無法取得 NBA 官方傷兵報告）'
            : '目前無法取得傷兵狀態'}
      </p>
    </section>
  );
}

function JoinForm({ onJoined }) {
  const [mode, setMode] = useState('new');
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    const v = value.trim();
    if (!v) return;
    setBusy(true);
    setError(null);
    try {
      const account =
        mode === 'new'
          ? await request('/fantasy/users', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name: v }),
            })
          : { ...(await request('/fantasy/me', { token: v })), token: v };
      onJoined(account);
    } catch (err) {
      setError(err.status === 401 ? '金鑰不正確' : err.message);
      setBusy(false);
    }
  };

  return (
    <section className="join">
      <h3>{mode === 'new' ? '加入遊戲' : '用金鑰登入'}</h3>
      <p className="meta">
        {mode === 'new'
          ? '取一個暱稱就能組自己的陣容，和其他玩家比積分。'
          : '在其他裝置加入過的話，貼上當時的金鑰即可繼續使用同一個暱稱。'}
      </p>
      <form onSubmit={submit}>
        <input
          aria-label={mode === 'new' ? '暱稱' : '金鑰'}
          placeholder={mode === 'new' ? '暱稱（最多 20 字）' : '金鑰'}
          maxLength={mode === 'new' ? 20 : undefined}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <button type="submit" disabled={busy || !value.trim()}>
          {mode === 'new' ? '加入' : '登入'}
        </button>
      </form>
      {error && <div className="error">{error}</div>}
      <button
        type="button"
        className="link-button"
        onClick={() => {
          setMode(mode === 'new' ? 'key' : 'new');
          setValue('');
          setError(null);
        }}
      >
        {mode === 'new' ? '已經有暱稱？用金鑰登入' : '建立新暱稱'}
      </button>
    </section>
  );
}

function RenameForm({ me, token, onRenamed, onCancel }) {
  const [value, setValue] = useState(me);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const unchanged = value.trim() === me;

  const submit = async (e) => {
    e.preventDefault();
    if (!value.trim() || unchanged) return;
    setBusy(true);
    setError(null);
    try {
      const body = await request('/fantasy/me', {
        method: 'PATCH',
        token,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: value.trim() }),
      });
      onRenamed(body.name);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <form className="rename" onSubmit={submit}>
      <input
        aria-label="新暱稱"
        maxLength={20}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === 'Escape' && onCancel()}
        autoFocus
      />
      <button type="submit" disabled={busy || !value.trim() || unchanged}>
        儲存
      </button>
      <button type="button" className="link-button" onClick={onCancel}>
        取消
      </button>
      {error && <div className="error">{error}</div>}
      <p className="meta">所有陣容與紀錄都會跟著新暱稱，金鑰不變；舊暱稱之後可以被別人使用。</p>
    </form>
  );
}

function AccountBar({ me, token, onLogout, onRenamed }) {
  const [showKey, setShowKey] = useState(false);
  const [renaming, setRenaming] = useState(false);
  if (renaming) {
    return (
      <section className="account">
        <RenameForm
          me={me}
          token={token}
          onCancel={() => setRenaming(false)}
          onRenamed={(name) => {
            setRenaming(false);
            onRenamed(name);
          }}
        />
      </section>
    );
  }
  return (
    <section className="account">
      <span>
        玩家：<strong>{me}</strong>
      </span>
      <button className="link-button" onClick={() => setRenaming(true)}>
        更改暱稱
      </button>
      <button className="link-button" onClick={() => setShowKey(!showKey)}>
        {showKey ? '隱藏金鑰' : '顯示金鑰'}
      </button>
      <button className="link-button" onClick={onLogout}>
        登出
      </button>
      {showKey && (
        <p className="meta key">
          金鑰 <code>{token}</code>：在其他裝置用它登入。金鑰是編輯陣容的唯一憑證，請勿分享。
        </p>
      )}
    </section>
  );
}

function DailyBoard({ board, me, viewing, onView }) {
  return (
    <section className="standings board">
      <h3>當日排行榜</h3>
      {!board ? (
        <div className="empty">載入中…</div>
      ) : board.entries.length === 0 ? (
        <div className="empty">這天還沒有人組陣容</div>
      ) : (
        <table className="data-table games-table">
          <thead>
            <tr>
              <th>名次</th>
              <th>玩家</th>
              <th>球員</th>
              <th>狀態</th>
              <th>積分</th>
            </tr>
          </thead>
          <tbody>
            {board.entries.map((e) => (
              <tr key={e.player} className={sameName(e.player, viewing) ? 'current' : ''} onClick={() => onView(e.player)}>
                <td>{e.rank}</td>
                <td>
                  {e.player}
                  {sameName(e.player, me) && <span className="meta">（你）</span>}
                </td>
                <td>{e.players} / 6</td>
                <td>{e.final ? '已結算' : '進行中'}</td>
                <td>{e.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="meta">點選玩家查看陣容；尚未開賽的球員，開賽後才公開</p>
    </section>
  );
}

function OverallBoard({ board, me, viewing, onView }) {
  return (
    <section className="standings board">
      <h3>總排行榜</h3>
      {!board ? (
        <div className="empty">載入中…</div>
      ) : board.entries.length === 0 ? (
        <div className="empty">還沒有結算的日子</div>
      ) : (
        <div className="table-wrap">
          <table className="data-table games-table">
            <thead>
              <tr>
                <th>名次</th>
                <th>玩家</th>
                <th>天數</th>
                <th>單日冠軍</th>
                <th>最佳</th>
                <th>平均</th>
                <th>總積分</th>
              </tr>
            </thead>
            <tbody>
              {board.entries.map((e) => (
                <tr key={e.player} className={sameName(e.player, viewing) ? 'current' : ''} onClick={() => onView(e.player)}>
                  <td>{e.rank}</td>
                  <td>
                    {e.player}
                    {sameName(e.player, me) && <span className="meta">（你）</span>}
                  </td>
                  <td>{e.days}</td>
                  <td>{e.wins}</td>
                  <td>{e.best}</td>
                  <td>{e.average.toFixed(1)}</td>
                  <td>{e.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="meta">只計入已結算的日子，依總積分排名；單日冠軍需當天至少兩人參加 · 點選玩家查看該玩家這天的陣容</p>
    </section>
  );
}

function History({ history, current, onSelect }) {
  if (!history?.length) return null;
  return (
    <section className="standings history">
      <h3>我的紀錄</h3>
      <table className="data-table games-table">
        <thead>
          <tr>
            <th>日期</th>
            <th>球員數</th>
            <th>狀態</th>
            <th>名次</th>
            <th>積分</th>
          </tr>
        </thead>
        <tbody>
          {history.map((h) => (
            <tr key={h.date} className={h.date === current ? 'current' : ''} onClick={() => onSelect(h.date)}>
              <td>{h.date}</td>
              <td>{h.players} / 6</td>
              <td>{h.final ? '已結算' : '未結算'}</td>
              <td>
                {h.rank} / {h.entrants}
              </td>
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
  const [token, setToken] = useState(readToken);
  const [me, setMe] = useState(null);
  // Another player's lineup being looked at; null shows your own.
  const [viewing, setViewing] = useState(null);
  const [lineup, setLineup] = useState(null);
  const [pool, setPool] = useState(null);
  const [daily, setDaily] = useState(null);
  const [overall, setOverall] = useState(null);
  const [history, setHistory] = useState(null);
  const [activeSlot, setActiveSlot] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [salaryRules, setSalaryRules] = useState(null);
  const lineupRequest = useRef(0);

  useEffect(() => {
    request('/fantasy/salary')
      .then(setSalaryRules)
      .catch(() => {});
  }, []);

  useEffect(() => {
    request('/games/')
      .then((body) => setLiveDate(body.date))
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!token) {
      setMe(null);
      return;
    }
    request('/fantasy/me', { token })
      .then((body) => setMe(body.name))
      .catch((e) => {
        if (e.status === 401) {
          writeToken(null);
          setToken(null);
        } else setError(e.message);
      });
  }, [token]);

  const day = date || liveDate;
  const target = viewing || me;
  const mine = !!me && sameName(target, me);

  const loadLineup = useCallback(() => {
    const id = ++lineupRequest.current;
    if (!day || !target) return;
    request(lineupUrl(day, target), { token })
      .then((body) => {
        if (id !== lineupRequest.current) return;
        setLineup(body);
        setError(null);
      })
      .catch((e) => id === lineupRequest.current && setError(e.message));
  }, [day, target, token]);

  const loadDaily = useCallback(() => {
    if (!day) return;
    request(`/fantasy/${day}/leaderboard`)
      .then((body) => body.date === day && setDaily(body))
      .catch(() => {});
  }, [day]);

  const loadOverall = useCallback(() => {
    request('/fantasy/leaderboard')
      .then(setOverall)
      .catch(() => {});
  }, []);

  const loadHistory = useCallback(() => {
    if (!me) {
      setHistory(null);
      return;
    }
    request(`/fantasy/history/${encodeURIComponent(me)}`)
      .then((body) => setHistory(body.history))
      .catch(() => {});
  }, [me]);

  useEffect(() => {
    setLineup(null);
    setActiveSlot(null);
    loadLineup();
  }, [loadLineup]);

  useEffect(() => {
    setPool(null);
    setDaily(null);
    loadDaily();
  }, [loadDaily]);

  useEffect(() => {
    loadOverall();
  }, [loadOverall]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // A lineup settling can change the overall standings.
  useEffect(() => {
    if (lineup?.final) loadOverall();
  }, [lineup?.final, loadOverall]);

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
    const id = setInterval(() => {
      loadLineup();
      loadDaily();
    }, REFRESH_MS);
    return () => clearInterval(id);
  }, [anyLive, loadLineup, loadDaily]);

  const save = async (slot, playerId) => {
    const slots = Object.fromEntries(lineup.slots.map((s) => [s.slot, s.player?.id ?? null]));
    slots[slot] = playerId;
    setSaving(true);
    try {
      const body = await request(`/fantasy/${day}/lineup`, {
        method: 'PUT',
        token,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slots }),
      });
      lineupRequest.current += 1; // drop any older load still in flight
      setLineup(body);
      setActiveSlot(null);
      setError(null);
      loadDaily();
      loadHistory();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const join = (account) => {
    writeToken(account.token);
    setToken(account.token);
    setMe(account.name);
    setViewing(null);
  };

  // The lineup and history reload on their own because they depend on `me`.
  const renamed = (name) => {
    setMe(name);
    setViewing(null);
    loadDaily();
    loadOverall();
  };

  const logout = () => {
    if (!window.confirm(`登出後，這台裝置需要金鑰才能再編輯「${me}」的陣容。確定登出？`)) return;
    writeToken(null);
    setToken(null);
    setMe(null);
    setViewing(null);
  };

  const view = (name) => setViewing(sameName(name, me) ? null : name);
  const selectDate = (iso) => onDateChange(iso && iso === liveDate ? null : iso);
  const pickedIds = new Set((lineup?.slots || []).filter((s) => s.player).map((s) => s.player.id));
  const filled = (lineup?.slots || []).filter((s) => s.player || s.hidden).length;
  const started = (lineup?.slots || []).filter((s) => s.locked).length;
  const editable = mine && lineup && !lineup.final;
  const signingIn = token && !me;

  return (
    <div className="dashboard">
      <header className="top-bar">
        <h1>Daily Fantasy</h1>
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
        {salaryRules && (
          <span className="rule">
            6 人薪資上限 <strong>{fullMoney(salaryRules.cap)}</strong>
          </span>
        )}
      </section>

      {me && <AccountBar me={me} token={token} onLogout={logout} onRenamed={renamed} />}
      {!token && <JoinForm onJoined={join} />}

      {error && <div className="error">{error}</div>}

      {target && (
        <section className="lineup-section">
          <div className="lineup-head">
            <h2>{mine ? '我的陣容' : `${target} 的陣容`}</h2>
            {!mine && (
              <button className="link-button" onClick={() => setViewing(null)}>
                {me ? '‹ 回到我的陣容' : '關閉'}
              </button>
            )}
          </div>

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
                  <span className="stat-value" title={fullMoney(lineup.salary.left)}>
                    {money(lineup.salary.left)}
                  </span>
                  <span className="stat-label">
                    {lineup.salary.left < 0 ? '超出薪資上限' : '剩餘薪資'}（已用 {money(lineup.salary.used)}）
                  </span>
                </div>
                <div className="stat">
                  <span className="stat-value">{started}</span>
                  <span className="stat-label">已鎖定（比賽已開始）</span>
                </div>
              </section>
              <p className="meta">
                球員的比賽一開始就鎖定，不能再換下或選入
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
                      budget={
                        lineup.salary.left +
                        (lineup.slots.find((s) => s.slot === activeSlot)?.player?.salary ?? 0)
                      }
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
        </section>
      )}
      {signingIn && !error && <div className="empty">登入中…</div>}

      <div className="boards">
        <DailyBoard board={daily} me={me} viewing={target} onView={view} />
        <OverallBoard board={overall} me={me} viewing={target} onView={view} />
      </div>

      <History history={history} current={day} onSelect={selectDate} />
    </div>
  );
}

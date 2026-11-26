import { useEffect, useState } from 'react';
import { readJson } from './readJson';
import MarginChart from './MarginChart';

const CONFERENCES = [
  { key: 'East', label: '東區' },
  { key: 'West', label: '西區' },
];
const RECENT_GAMES = 10;

const one = (v) => (v == null ? '-' : Number(v).toFixed(1));
const signed = (v) => (v == null ? '-' : `${v > 0 ? '+' : ''}${Number(v).toFixed(1)}`);
const winPct = (v) => (v == null ? '-' : Number(v).toFixed(3).replace(/^0/, ''));

function logo(id) {
  return `https://cdn.nba.com/logos/nba/${id}/global/L/logo.svg`;
}

// In tables a failed logo keeps its space so names stay aligned; elsewhere it collapses.
function TeamLogo({ id, size, keepSpace = true }) {
  return (
    <img
      className="team-logo"
      src={logo(id)}
      alt=""
      width={size}
      height={size}
      onError={(e) => {
        e.currentTarget.style[keepSpace ? 'visibility' : 'display'] = keepSpace ? 'hidden' : 'none';
      }}
    />
  );
}

function useFetch(url) {
  const [state, setState] = useState({ data: null, error: null });
  useEffect(() => {
    let cancelled = false;
    setState({ data: null, error: null });
    fetch(url)
      .then(async (res) => {
        const body = await readJson(res);
        if (!cancelled) setState({ data: body, error: null });
      })
      .catch((e) => !cancelled && setState({ data: null, error: e.message }));
    return () => {
      cancelled = true;
    };
  }, [url]);
  return state;
}

function StandingsTable({ teams, label }) {
  return (
    <section className="standings">
      <h3>{label}</h3>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th><th>球隊</th><th>勝</th><th>敗</th><th>勝率</th><th>勝差</th>
              <th>主場</th><th>客場</th><th>近10場</th><th>連勝敗</th><th>淨勝分</th>
            </tr>
          </thead>
          <tbody>
            {teams.map((t) => (
              <tr
                key={t.id}
                className={t.rank === 6 || t.rank === 10 ? 'cutoff' : ''}
                onClick={() => (window.location.hash = `#/teams/${t.id}`)}
              >
                <td>{t.rank}</td>
                <td>
                  <a className="team-cell" href={`#/teams/${t.id}`}>
                    <TeamLogo id={t.id} size={22} />
                    {t.city} {t.name}
                  </a>
                </td>
                <td>{t.wins}</td>
                <td>{t.losses}</td>
                <td>{winPct(t.pct)}</td>
                <td>{t.gamesBack ? one(t.gamesBack) : '-'}</td>
                <td>{t.home}</td>
                <td>{t.road}</td>
                <td>{t.last10}</td>
                <td>{t.streak}</td>
                <td>{signed(t.diff)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Standings() {
  const { data, error } = useFetch('/team/standings');
  if (error) return <div className="error">無法取得戰績：{error}</div>;
  if (!data) return <div className="empty">載入中…</div>;
  return (
    <>
      <p className="meta">
        {data.season} 例行賽 · 粗線分隔季後賽直通區（1–6）、附加賽區（7–10）與淘汰區 · 點選球隊查看詳細資料
      </p>
      {CONFERENCES.map((c) => (
        <StandingsTable
          key={c.key}
          label={c.label}
          teams={data.teams.filter((t) => t.conference === c.key)}
        />
      ))}
    </>
  );
}

function TeamProfile({ teamId }) {
  const { data: t, error } = useFetch(`/team/${teamId}/profile`);
  if (error) return <div className="error">無法取得球隊資料：{error}</div>;
  if (!t) return <div className="empty">載入中…</div>;

  const confLabel = CONFERENCES.find((c) => c.key === t.conference)?.label || t.conference;
  const recent = [...t.games].reverse().slice(0, RECENT_GAMES);
  const tiles = [
    ['場均得分', t.ranks.pts],
    ['場均籃板', t.ranks.reb],
    ['場均助攻', t.ranks.ast],
    ['場均失分', t.ranks.oppPts],
  ];

  return (
    <section className="player-profile team-profile">
      <header className="profile-head">
        <TeamLogo id={t.id} size={80} keepSpace={false} />
        <div>
          <h2>{t.city} {t.name}</h2>
          <p className="meta">
            {t.season} · {t.wins}勝 {t.losses}敗
            {t.confRank && ` · ${confLabel}第 ${t.confRank}`}
            {t.divRank && ` · ${t.division}組第 ${t.divRank}`}
            {t.coach && ` · 總教練 ${t.coach}`}
          </p>
        </div>
      </header>

      <h3>本季數據（括號內為聯盟排名）</h3>
      <div className="summary career team-ranks">
        {tiles.map(([label, r]) => (
          <div className="stat" key={label}>
            <span className="stat-value">{one(r.value)}</span>
            <span className="stat-label">
              {label}
              {r.rank && `（第 ${r.rank}）`}
            </span>
          </div>
        ))}
      </div>

      {t.games.length > 0 && (
        <>
          <div className="chart-head">
            <h3>每場得失分差</h3>
            <div className="legend">
              <span><i className="swatch win" />勝</span>
              <span><i className="swatch loss" />敗</span>
            </div>
          </div>
          <MarginChart games={t.games} />

          <h3>最近 {recent.length} 場</h3>
          <div className="table-wrap">
            <table className="data-table games-table">
              <thead>
                <tr><th>日期</th><th>對手</th><th>結果</th><th>比分</th><th>分差</th></tr>
              </thead>
              <tbody>
                {recent.map((g) => (
                  <tr key={g.id}>
                    <td>{g.date}</td>
                    <td>{g.home ? 'vs' : '@'} {g.opponent}</td>
                    <td>{g.result === 'W' ? '勝' : '敗'}</td>
                    <td>{g.pts}–{g.oppPts}</td>
                    <td>{g.margin > 0 ? `+${g.margin}` : g.margin}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h3>球員名單</h3>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th><th>球員</th><th>位置</th><th>身高</th><th>體重</th><th>年齡</th><th>年資</th><th>學校</th>
            </tr>
          </thead>
          <tbody>
            {t.roster.map((p) => (
              <tr key={p.id}>
                <td>{p.number}</td>
                <td><a href={`#/players/${p.id}`}>{p.name}</a></td>
                <td>{p.position}</td>
                <td>{p.height}</td>
                <td>{p.weight}</td>
                <td>{p.age != null ? Math.floor(p.age) : '-'}</td>
                <td>{p.experience === 'R' ? '新秀' : p.experience}</td>
                <td>{p.school}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function TeamsDashboard({ selectedId }) {
  return (
    <div className="dashboard">
      <header className="top-bar">
        <h1>NBA Teams</h1>
        {selectedId && (
          <a className="back-link" href="#/teams">
            ‹ 返回戰績榜
          </a>
        )}
      </header>
      <div className="teams-body">
        {selectedId ? <TeamProfile teamId={selectedId} /> : <Standings />}
      </div>
    </div>
  );
}

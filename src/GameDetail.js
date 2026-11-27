import { useCallback, useEffect, useRef, useState } from 'react';
import { readJson } from './readJson';
import { GameCard } from './GamesDashboard';

const REFRESH_MS = 30000;
const LIVE = 2;

const shooting = (made, attempted) => `${made}-${attempted}`;
const signed = (n) => (n > 0 ? `+${n}` : `${n}`);

function TeamBox({ team, name, sortByPoints }) {
  const players = sortByPoints ? [...team.players].sort((a, b) => b.points - a.points) : team.players;
  const best = Math.max(0, ...team.players.map((p) => p.points));
  return (
    <section className="standings box-team">
      <h3>
        {team.tricode} <span className="meta">{name}</span>
      </h3>
      {players.length === 0 ? (
        <div className="empty">還沒有球員上場</div>
      ) : (
        <div className="table-wrap">
          <table className="data-table box-table">
            <thead>
              <tr>
                <th>球員</th>
                <th>積分</th>
                <th>分鐘</th>
                <th>得分</th>
                <th>籃板</th>
                <th>助攻</th>
                <th>抄截</th>
                <th>火鍋</th>
                <th>失誤</th>
                <th>犯規</th>
                <th>投籃</th>
                <th>三分</th>
                <th>罰球</th>
                <th>+/-</th>
              </tr>
            </thead>
            <tbody>
              {players.map((p) => {
                const s = p.stats;
                return (
                  <tr key={p.id} className={p.pickedBy.length ? 'picked' : ''}>
                    <td>
                      <div className="box-name">
                        {p.name}
                        {p.starter && <span className="meta"> {p.position || '先發'}</span>}
                      </div>
                      {p.pickedBy.length > 0 && (
                        <div className="meta picked-by" title={p.pickedBy.join('、')}>
                          被 {p.pickedBy.length} 人選：{p.pickedBy.join('、')}
                        </div>
                      )}
                    </td>
                    <td>
                      <strong>{p.points}</strong>
                      {p.points === best && best > 0 && (
                        <span className="mvp" title="本隊 Fantasy 積分最高">
                          ★
                        </span>
                      )}
                    </td>
                    <td>{s.min}</td>
                    <td>{s.pts}</td>
                    <td>{s.reb}</td>
                    <td>{s.ast}</td>
                    <td>{s.stl}</td>
                    <td>{s.blk}</td>
                    <td>{s.tov}</td>
                    <td>{s.pf}</td>
                    <td>{shooting(s.fgm, s.fga)}</td>
                    <td>{shooting(s.fg3m, s.fg3a)}</td>
                    <td>{shooting(s.ftm, s.fta)}</td>
                    <td>{signed(s.pm)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {team.bench.length > 0 && <p className="meta">未上場：{team.bench.join('、')}</p>}
    </section>
  );
}

/** One game's box score with fantasy points. `date` is the game's US date. */
export default function GameDetail({ date, gameId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [sortByPoints, setSortByPoints] = useState(false);
  const requestId = useRef(0);

  const load = useCallback(() => {
    const id = ++requestId.current;
    fetch(`/games/${date}/${gameId}`)
      .then(readJson)
      .then((body) => {
        if (id !== requestId.current) return;
        setData(body);
        setError(null);
      })
      .catch((e) => id === requestId.current && setError(e.message));
  }, [date, gameId]);

  useEffect(() => {
    setData(null);
    setError(null);
    load();
  }, [load]);

  const live = data?.game.status === LIVE;
  useEffect(() => {
    if (!live) return undefined;
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [live, load]);

  const game = data?.game;
  return (
    <div className="dashboard game-detail">
      <header className="top-bar">
        <div>
          <a className="link-button back-link" href={`#/games/${date}`}>
            ‹ 回到 {date} 的比賽
          </a>
          <h1>{game ? `${game.away.tricode} @ ${game.home.tricode}` : '比賽'}</h1>
        </div>
        {data && game.status !== 1 && (
          <label className="sort-toggle">
            <input type="checkbox" checked={sortByPoints} onChange={(e) => setSortByPoints(e.target.checked)} />
            依積分排序
          </label>
        )}
      </header>

      {error && <div className="error">無法取得比賽資料：{error}</div>}
      {!data && !error && <div className="empty">載入中…</div>}

      {data && (
        <>
          <div className="games-grid detail-card">
            <GameCard game={game} date={date} linked={false} />
          </div>
          <p className="meta">
            積分依 Daily Fantasy 的積分規則計算（最低 0 分）；★ 是各隊積分最高的球員，有底色的是有玩家選的球員
            {live && ` · 比賽進行中，每 ${REFRESH_MS / 1000} 秒更新`}
          </p>
          {game.status === 1 ? (
            <div className="empty">比賽還沒開始，開賽後會顯示每位球員的數據與積分</div>
          ) : (
            <div className="box-teams">
              <TeamBox team={data.teams.away} name={`${game.away.city} ${game.away.name}`} sortByPoints={sortByPoints} />
              <TeamBox team={data.teams.home} name={`${game.home.city} ${game.home.name}`} sortByPoints={sortByPoints} />
            </div>
          )}
        </>
      )}
    </div>
  );
}

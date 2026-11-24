import { useEffect, useRef, useState } from 'react';
import { barPath, niceMax } from './SeasonChart';

const HEIGHT = 220;
const PAD = { top: 12, right: 8, bottom: 12, left: 36 };

// Same shape as barPath, flipped: flat at the baseline, rounded at the bottom.
function barPathDown(x, y, w, h) {
  const r = Math.min(4, w / 2, h);
  return `M${x},${y}V${y + h - r}Q${x},${y + h} ${x + r},${y + h}H${x + w - r}Q${x + w},${y + h} ${x + w},${y + h - r}V${y}Z`;
}

/** Point margin of every game: wins rise above the zero line, losses drop below it. */
export default function MarginChart({ games }) {
  const wrapRef = useRef(null);
  const [width, setWidth] = useState(600);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return undefined;
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const played = games.filter((g) => g.margin != null);
  if (!played.length) return null;

  const yMax = niceMax(Math.max(...played.map((g) => Math.abs(g.margin))));
  const plotW = Math.max(width - PAD.left - PAD.right, 50);
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const slot = plotW / played.length;
  const gap = Math.max(2, slot * 0.25);
  const barW = Math.max(slot - gap, 2);
  const y = (v) => PAD.top + plotH / 2 - (v / yMax) * (plotH / 2);
  const zero = y(0);
  const hovered = hover !== null ? played[hover] : null;

  return (
    <div className="season-chart" ref={wrapRef}>
      <svg width={width} height={HEIGHT} role="img" aria-label="每場比賽得失分差">
        {[yMax, 0, -yMax].map((t) => (
          <g key={t}>
            <line className={t === 0 ? 'baseline' : 'grid'} x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} />
            <text className="axis" x={PAD.left - 6} y={y(t)} dy="0.32em" textAnchor="end">
              {t > 0 ? `+${t}` : t}
            </text>
          </g>
        ))}
        {played.map((g, i) => {
          const x = PAD.left + i * slot + gap / 2;
          const h = Math.abs(zero - y(g.margin));
          const win = g.margin > 0;
          return (
            <g key={g.id} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect className="hit" x={PAD.left + i * slot} y={PAD.top} width={slot} height={plotH} />
              {h > 0 && (
                <path
                  className={`bar ${win ? 'win' : 'loss'} ${hover !== null && hover !== i ? 'dim' : ''}`}
                  d={win ? barPath(x, zero - h, barW, h) : barPathDown(x, zero, barW, h)}
                />
              )}
            </g>
          );
        })}
      </svg>
      {hovered && (
        <div
          className="chart-tooltip"
          style={{
            left: Math.min(Math.max(PAD.left + hover * slot + slot / 2, 70), width - 70),
            top: Math.max(Math.min(y(hovered.margin), zero) - 8, 0),
          }}
        >
          <strong>{hovered.date}</strong> · {hovered.home ? 'vs' : '@'} {hovered.opponent}
          <div>
            {hovered.result} {hovered.pts}–{hovered.oppPts}（{hovered.margin > 0 ? '+' : ''}
            {hovered.margin}）
          </div>
        </div>
      )}
    </div>
  );
}

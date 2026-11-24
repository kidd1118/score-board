import { useEffect, useRef, useState } from 'react';

const HEIGHT = 220;
const PAD = { top: 16, right: 8, bottom: 28, left: 36 };

export function niceMax(value) {
  if (value <= 0) return 1;
  const step = 10 ** Math.floor(Math.log10(value));
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) {
    if (m * step >= value) return m * step;
  }
  return 10 * step;
}

// Rounded top corners (4px), flat on the baseline.
export function barPath(x, y, w, h) {
  const r = Math.min(4, w / 2, h);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

/** Single-series bar chart: one bar per season for the chosen stat. */
export default function SeasonChart({ seasons, metric, format }) {
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

  if (!seasons.length) return null;

  const values = seasons.map((s) => s[metric] ?? 0);
  const yMax = niceMax(Math.max(...values));
  const ticks = [0, yMax / 2, yMax];
  const plotW = Math.max(width - PAD.left - PAD.right, 50);
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const slot = plotW / seasons.length;
  const gap = Math.max(2, slot * 0.25);
  const barW = Math.max(slot - gap, 2);
  const labelEvery = Math.ceil(seasons.length / Math.max(Math.floor(plotW / 56), 1));
  const y = (v) => PAD.top + plotH - (v / yMax) * plotH;

  return (
    <div className="season-chart" ref={wrapRef}>
      <svg width={width} height={HEIGHT} role="img" aria-label={`${metric.toUpperCase()} per season`}>
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid" x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} />
            <text className="axis" x={PAD.left - 6} y={y(t)} dy="0.32em" textAnchor="end">
              {format(t)}
            </text>
          </g>
        ))}
        {seasons.map((s, i) => {
          const v = values[i];
          const x = PAD.left + i * slot + gap / 2;
          const h = (v / yMax) * plotH;
          return (
            <g
              key={s.season}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            >
              <rect className="hit" x={PAD.left + i * slot} y={PAD.top} width={slot} height={plotH} />
              {h > 0 && (
                <path
                  className={`bar ${hover !== null && hover !== i ? 'dim' : ''}`}
                  d={barPath(x, y(v), barW, h)}
                />
              )}
              {i % labelEvery === 0 && (
                <text className="axis" x={x + barW / 2} y={HEIGHT - 8} textAnchor="middle">
                  {s.season.slice(2)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {hover !== null && (
        <div
          className="chart-tooltip"
          style={{
            left: Math.min(PAD.left + hover * slot + slot / 2, width - 70),
            top: Math.max(y(values[hover]) - 8, 0),
          }}
        >
          <strong>{seasons[hover].season}</strong> · {seasons[hover].team}
          <div>
            {metric.toUpperCase()} {format(values[hover])}
          </div>
        </div>
      )}
    </div>
  );
}

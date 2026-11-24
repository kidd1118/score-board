/** A row of days around the selected date (YYYY-MM-DD, US date). */
export function shiftDate(iso, days) {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'];
const STRIP_DAYS = 3; // days shown on each side of the selected date

function dayParts(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return { weekday: WEEKDAYS[d.getDay()], label: `${d.getMonth() + 1}/${d.getDate()}` };
}

export default function DateStrip({ selected, today, onSelect }) {
  const days = [];
  for (let i = -STRIP_DAYS; i <= STRIP_DAYS; i += 1) days.push(shiftDate(selected, i));
  return (
    <nav className="date-strip" aria-label="選擇日期">
      <button className="strip-arrow" onClick={() => onSelect(shiftDate(selected, -1))} aria-label="前一天">
        ‹
      </button>
      {days.map((iso) => {
        const { weekday, label } = dayParts(iso);
        return (
          <button
            key={iso}
            className={`day ${iso === selected ? 'selected' : ''}`}
            aria-current={iso === selected ? 'date' : undefined}
            onClick={() => onSelect(iso)}
          >
            <span className="day-week">{iso === today ? '今天' : `週${weekday}`}</span>
            <span className="day-date">{label}</span>
          </button>
        );
      })}
      <button className="strip-arrow" onClick={() => onSelect(shiftDate(selected, 1))} aria-label="後一天">
        ›
      </button>
    </nav>
  );
}

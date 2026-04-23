import { useState, useEffect, useMemo } from 'react';
import { getCalendar } from '../utils/api';

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const DAYS = ['Mon','','Wed','','Fri','','Sun'];

const CELL_SIZE = 13;
const CELL_GAP = 3;
const ROW_HEIGHT = CELL_SIZE + CELL_GAP;

function intensityColor(miles, maxMiles) {
  if (!miles || miles <= 0) return 'rgba(255,255,255,0.03)';
  const ratio = Math.min(miles / maxMiles, 1);
  if (ratio < 0.25) return 'rgba(52,211,153,0.2)';
  if (ratio < 0.50) return 'rgba(52,211,153,0.4)';
  if (ratio < 0.75) return 'rgba(52,211,153,0.65)';
  return 'rgba(52,211,153,0.9)';
}

/**
 * ActivityCalendar — GitHub-style contribution heatmap.
 * Shows daily activity intensity over the past N months.
 */
export default function ActivityCalendar() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tooltip, setTooltip] = useState(null);

  useEffect(() => {
    getCalendar(12)
      .then(res => setData(res.days || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const { grid, monthLabels, maxMiles, weeks } = useMemo(() => {
    // Build a map of date -> data
    const dayMap = {};
    let maxM = 1;
    for (const d of data) {
      dayMap[d.date] = d;
      if (d.miles > maxM) maxM = d.miles;
    }

    // Generate 52 weeks of cells ending today
    const today = new Date();
    const cells = [];
    const mLabels = [];
    let lastMonth = -1;

    // Start from 52 weeks ago, aligned to Monday
    const start = new Date(today);
    start.setDate(start.getDate() - (52 * 7) - (start.getDay() === 0 ? 6 : start.getDay() - 1));

    let week = 0;
    const cursor = new Date(start);
    while (cursor <= today) {
      const dayOfWeek = cursor.getDay() === 0 ? 6 : cursor.getDay() - 1; // Mon=0, Sun=6
      const dateStr = cursor.toISOString().split('T')[0];
      const entry = dayMap[dateStr];

      if (dayOfWeek === 0 && cursor.getMonth() !== lastMonth) {
        mLabels.push({ month: MONTHS[cursor.getMonth()], week });
        lastMonth = cursor.getMonth();
      }

      cells.push({
        date: dateStr,
        week,
        day: dayOfWeek,
        miles: entry?.miles || 0,
        count: entry?.count || 0,
        minutes: entry?.minutes || 0,
        type: entry?.type || null,
      });

      cursor.setDate(cursor.getDate() + 1);
      if (dayOfWeek === 6) week++;
    }

    return { grid: cells, monthLabels: mLabels, maxMiles: maxM, weeks: week + 1 };
  }, [data]);

  if (loading) {
    return (
      <div className="glass-card chart-container" style={{ minHeight: 160 }}>
        <div className="section-header">
          <span className="section-title">Activity Calendar</span>
        </div>
        <div className="loading-state" style={{ padding: 'var(--space-lg)' }}>
          <div className="loading-spinner" />
        </div>
      </div>
    );
  }

  const svgWidth = weeks * (CELL_SIZE + CELL_GAP) + 30;
  const svgHeight = 7 * ROW_HEIGHT + 24;

  return (
    <div className="glass-card chart-container" style={{ overflow: 'hidden' }}>
      <div className="section-header">
        <span className="section-title">Activity Calendar</span>
        <span className="section-subtitle">Last 12 months</span>
      </div>

      <div style={{ overflowX: 'auto', padding: '0 var(--space-md) var(--space-md)' }}>
        <svg
          width={svgWidth}
          height={svgHeight}
          style={{ display: 'block' }}
          onMouseLeave={() => setTooltip(null)}
        >
          {/* Month labels */}
          {monthLabels.map((m, i) => (
            <text
              key={i}
              x={m.week * (CELL_SIZE + CELL_GAP) + 30}
              y={10}
              fill="var(--text-muted)"
              fontSize="10"
              fontFamily="Inter, sans-serif"
            >
              {m.month}
            </text>
          ))}

          {/* Day labels */}
          {DAYS.map((d, i) => (
            <text
              key={i}
              x={0}
              y={i * ROW_HEIGHT + 30}
              fill="var(--text-muted)"
              fontSize="9"
              fontFamily="Inter, sans-serif"
              dominantBaseline="middle"
            >
              {d}
            </text>
          ))}

          {/* Cells */}
          {grid.map((cell, i) => (
            <rect
              key={i}
              x={cell.week * (CELL_SIZE + CELL_GAP) + 30}
              y={cell.day * ROW_HEIGHT + 18}
              width={CELL_SIZE}
              height={CELL_SIZE}
              rx={2}
              ry={2}
              fill={intensityColor(cell.miles, maxMiles)}
              stroke="rgba(255,255,255,0.03)"
              strokeWidth={0.5}
              style={{ cursor: cell.count > 0 ? 'pointer' : 'default', transition: 'fill 0.15s ease' }}
              onMouseEnter={(e) => {
                if (cell.count > 0) {
                  const rect = e.target.getBoundingClientRect();
                  setTooltip({
                    x: rect.left + rect.width / 2,
                    y: rect.top - 8,
                    date: cell.date,
                    count: cell.count,
                    miles: cell.miles,
                    minutes: cell.minutes,
                    type: cell.type,
                  });
                } else {
                  setTooltip(null);
                }
              }}
            />
          ))}
        </svg>
      </div>

      {/* Legend */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 6,
        padding: '0 var(--space-md) var(--space-sm)', fontSize: '0.7rem', color: 'var(--text-muted)',
      }}>
        <span>Less</span>
        {[0, 0.2, 0.4, 0.65, 0.9].map((op, i) => (
          <span
            key={i}
            style={{
              width: 10, height: 10, borderRadius: 2, display: 'inline-block',
              background: op === 0 ? 'rgba(255,255,255,0.03)' : `rgba(52,211,153,${op})`,
            }}
          />
        ))}
        <span>More</span>
      </div>

      {/* Tooltip portal */}
      {tooltip && (
        <div
          style={{
            position: 'fixed',
            left: tooltip.x,
            top: tooltip.y,
            transform: 'translate(-50%, -100%)',
            background: 'rgba(19,19,19,0.95)',
            border: '1px solid rgba(255,255,255,0.15)',
            borderRadius: 8,
            padding: '8px 12px',
            fontSize: '0.75rem',
            pointerEvents: 'none',
            zIndex: 9999,
            whiteSpace: 'nowrap',
            boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 2, color: 'var(--text-primary)' }}>
            {new Date(tooltip.date + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}
          </div>
          <div style={{ color: '#38bdf8', fontFamily: 'Manrope' }}>
            {tooltip.count} {tooltip.count === 1 ? 'activity' : 'activities'} · {tooltip.miles.toFixed(1)} mi
          </div>
          <div style={{ color: 'var(--text-muted)', fontFamily: 'Manrope' }}>
            {Math.round(tooltip.minutes)} min total
          </div>
        </div>
      )}
    </div>
  );
}

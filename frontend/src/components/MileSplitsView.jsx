import React, { useMemo } from 'react';
import { BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import SafeResponsiveContainer from './SafeResponsiveContainer';
import { formatTime, formatHR } from '../utils/format';
import { CHART_MARGIN, GRID_PROPS, AXIS_TICK, BAR_CURSOR } from '../utils/chartkit';
import ChartTooltip from './ChartTooltip';

const ACCENT = '#26c6f9';
const HR_ACCENT = '#f472b6';

function paceOf(row) {
  // Full miles are exactly 1.0mi, so time-per-mile *is* pace; the trailing
  // partial mile needs its own distance to normalize.
  const dist = row.partial ? row.mile : 1;
  return row.time_seconds / 60 / dist;
}

export default function MileSplitsView({ mileSplits, handleFetchDetails, syncingDetails, activityId }) {
  const { fastestIdx, slowestIdx } = useMemo(() => {
    if (!mileSplits.length) return { fastestIdx: -1, slowestIdx: -1 };
    const fullMiles = mileSplits.map((r, i) => ({ i, r })).filter(({ r }) => !r.partial);
    if (!fullMiles.length) return { fastestIdx: -1, slowestIdx: -1 };
    let fastest = fullMiles[0], slowest = fullMiles[0];
    for (const m of fullMiles) {
      if (m.r.time_seconds < fastest.r.time_seconds) fastest = m;
      if (m.r.time_seconds > slowest.r.time_seconds) slowest = m;
    }
    return { fastestIdx: fastest.i, slowestIdx: slowest.i };
  }, [mileSplits]);

  if (!mileSplits.length) {
    return (
      <div className="glass-card chart-container" style={{ minWidth: 0, padding: 'var(--space-lg)' }}>
        <div style={{ height: 200, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 15, border: '1px dashed var(--border-medium)', borderRadius: 12 }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Granular split data not yet synced for this activity</span>
          <button
            className="filter-chip"
            onClick={() => handleFetchDetails(activityId)}
            disabled={syncingDetails}
            style={{ fontSize: '0.7rem' }}
          >
            {syncingDetails ? 'Syncing...' : 'Fetch Granular Data'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      <div className="glass-card chart-container" style={{ minWidth: 0, padding: 'var(--space-lg)' }}>
        <div className="section-header" style={{ marginBottom: 16 }}>
          <div>
            <span className="section-title">Splits</span>
            <span className="section-subtitle">time per mile</span>
          </div>
        </div>

        <SafeResponsiveContainer height={220}>
          <BarChart data={mileSplits} margin={CHART_MARGIN}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
            <XAxis
              dataKey="mile"
              tick={AXIS_TICK}
              tickFormatter={v => `${v}`}
            />
            <YAxis tick={AXIS_TICK} width={46} tickFormatter={v => formatTime(v)} />
            <Tooltip
              cursor={BAR_CURSOR}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const d = payload[0]?.payload;
                if (!d) return null;
                return (
                  <ChartTooltip title={`Mile ${d.mile}${d.partial ? ' (partial)' : ''}`}>
                    <div style={{ color: ACCENT, fontFamily: 'var(--font-display)' }}>
                      {formatTime(d.time_seconds)} {!d.partial && `(${paceOf(d).toFixed(2)}/mi pace)`}
                    </div>
                    {d.avg_hr != null && (
                      <div style={{ color: HR_ACCENT, marginTop: 2 }}>
                        {formatHR(d.avg_hr)} bpm avg
                      </div>
                    )}
                  </ChartTooltip>
                );
              }}
            />
            <Bar dataKey="time_seconds" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {mileSplits.map((row, i) => (
                <Cell
                  key={i}
                  fill={
                    i === fastestIdx ? '#4ade80'
                      : i === slowestIdx ? '#fb7185'
                      : row.partial ? `${ACCENT}55`
                      : ACCENT
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </SafeResponsiveContainer>

        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: '0.62rem', color: 'var(--text-secondary)', marginTop: 10 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: '#4ade80' }} /> fastest
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: '#fb7185' }} /> slowest
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: `${ACCENT}55` }} /> partial mile
          </span>
        </div>
      </div>

      <div className="glass-card" style={{ overflow: 'auto', padding: 'var(--space-lg)' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
              <th style={thStyle('left')}>Mile</th>
              <th style={thStyle('right')}>Time</th>
              <th style={thStyle('right')}>Pace</th>
              <th style={thStyle('right')}>Avg HR</th>
            </tr>
          </thead>
          <tbody>
            {mileSplits.map((row, i) => (
              <tr key={i} style={{ borderBottom: i < mileSplits.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}>
                <td style={{ padding: '10px 16px', fontWeight: 700, color: 'var(--text-primary)' }}>
                  {row.mile}{row.partial && <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}> (partial)</span>}
                </td>
                <td style={{ padding: '10px 16px', textAlign: 'right', fontFamily: 'Manrope, sans-serif', color: i === fastestIdx ? '#4ade80' : i === slowestIdx ? '#fb7185' : 'var(--text-secondary)' }}>
                  {formatTime(row.time_seconds)}
                </td>
                <td style={{ padding: '10px 16px', textAlign: 'right', fontFamily: 'Manrope, sans-serif', color: 'var(--text-secondary)' }}>
                  {row.partial ? '—' : `${paceOf(row).toFixed(2)}/mi`}
                </td>
                <td style={{ padding: '10px 16px', textAlign: 'right', fontFamily: 'Manrope, sans-serif', color: HR_ACCENT }}>
                  {row.avg_hr != null ? `${formatHR(row.avg_hr)} bpm` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function thStyle(align = 'left') {
  return {
    padding: '10px 16px',
    textAlign: align,
    color: 'var(--text-muted)',
    fontWeight: 600,
    fontSize: '0.72rem',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    whiteSpace: 'nowrap',
  };
}

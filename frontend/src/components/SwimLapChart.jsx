import { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, Cell, ResponsiveContainer,
} from 'recharts';

const STROKE_COLORS = {
  freestyle:    '#38bdf8',
  backstroke:   '#a78bfa',
  breaststroke: '#4ade80',
  butterfly:    '#facc15',
  kickboard:    '#fb923c',
  mixed:        '#94a3b8',
  rest:         '#334155',
  unknown:      '#64748b',
};

const STROKE_LABELS = {
  freestyle:    'Freestyle',
  backstroke:   'Backstroke',
  breaststroke: 'Breaststroke',
  butterfly:    'Butterfly',
  kickboard:    'Kickboard',
  mixed:        'Mixed',
  rest:         'Rest',
};

function fmtPace(seconds) {
  if (!seconds) return '—';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const unit = d.unit || 'm';
  return (
    <div style={{
      background: '#1e293b',
      border: '1px solid rgba(255,255,255,0.12)',
      borderRadius: 8,
      padding: '10px 14px',
      fontSize: '0.78rem',
      lineHeight: 1.7,
    }}>
      <div style={{ fontWeight: 700, marginBottom: 4, color: '#f1f5f9' }}>
        {d.is_rest ? 'Rest' : `Lap ${d.lap_number}`}
      </div>
      {!d.is_rest && (
        <>
          <div style={{ color: STROKE_COLORS[d.stroke_type] || STROKE_COLORS.unknown }}>
            {STROKE_LABELS[d.stroke_type] || 'Unknown stroke'}
          </div>
          <div style={{ color: 'var(--text-muted)' }}>
            Pace: <span style={{ color: '#f1f5f9' }}>{fmtPace(d.pace_per_100)}/{unit === 'yd' ? '100yd' : '100m'}</span>
          </div>
          {d.duration_seconds != null && (
            <div style={{ color: 'var(--text-muted)' }}>
              Duration: <span style={{ color: '#f1f5f9' }}>{fmtPace(d.duration_seconds)}</span>
            </div>
          )}
          {d.stroke_count > 0 && (
            <div style={{ color: 'var(--text-muted)' }}>
              Strokes: <span style={{ color: '#f1f5f9' }}>{d.stroke_count}</span>
            </div>
          )}
          {d.avg_heartrate > 0 && (
            <div style={{ color: 'var(--text-muted)' }}>
              Avg HR: <span style={{ color: '#f472b6' }}>{Math.round(d.avg_heartrate)} bpm</span>
            </div>
          )}
        </>
      )}
      {d.is_rest && (
        <div style={{ color: 'var(--text-muted)' }}>
          {fmtPace(d.duration_seconds)}
        </div>
      )}
    </div>
  );
}

export default function SwimLapChart({ swimData }) {
  const { laps = [], pool_length_meters, avg_pace_per_100, best_pace_per_100 } = swimData || {};

  // Determine display unit based on pool length
  const unit = useMemo(() => {
    if (!pool_length_meters) return 'm';
    // 25yd ≈ 22.86m, 50yd ≈ 45.72m
    const remainder = pool_length_meters % 22.86;
    return remainder < 1 ? 'yd' : 'm';
  }, [pool_length_meters]);

  const poolDisplay = useMemo(() => {
    if (!pool_length_meters) return null;
    if (unit === 'yd') return `${Math.round(pool_length_meters / 0.9144)}yd`;
    return `${Math.round(pool_length_meters)}m`;
  }, [pool_length_meters, unit]);

  // Inject unit into each lap for the tooltip
  const chartData = useMemo(() =>
    laps.map(l => ({ ...l, unit })),
    [laps, unit]
  );

  // Legend: unique stroke types present
  const strokeTypes = useMemo(() => {
    const seen = new Set();
    laps.forEach(l => {
      if (!l.is_rest && l.stroke_type) seen.add(l.stroke_type);
    });
    return [...seen];
  }, [laps]);

  if (!laps.length) {
    return (
      <div className="glass-card" style={{ padding: 'var(--space-xl)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
        No lap data available for this swim.
      </div>
    );
  }

  // Y-axis domain: add some headroom above the slowest pace
  const maxPace = Math.max(...laps.filter(l => l.pace_per_100).map(l => l.pace_per_100));
  const yMax = Math.ceil(maxPace * 1.15 / 10) * 10;

  return (
    <div className="glass-card chart-container" style={{ minWidth: 0 }}>
      {/* Header */}
      <div className="section-header" style={{ marginBottom: 16 }}>
        <div>
          <span className="section-title">Swim Laps</span>
          {poolDisplay && (
            <span className="section-subtitle">{poolDisplay} pool · {laps.length} laps</span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 16, fontSize: '0.75rem', color: 'var(--text-muted)', alignItems: 'center', flexWrap: 'wrap' }}>
          {avg_pace_per_100 && (
            <span>
              Avg <span style={{ color: '#38bdf8', fontWeight: 600 }}>
                {fmtPace(avg_pace_per_100)}/{unit === 'yd' ? '100yd' : '100m'}
              </span>
            </span>
          )}
          {best_pace_per_100 && (
            <span>
              Best <span style={{ color: '#4ade80', fontWeight: 600 }}>
                {fmtPace(best_pace_per_100)}/{unit === 'yd' ? '100yd' : '100m'}
              </span>
            </span>
          )}
        </div>
      </div>

      {/* Stroke legend */}
      {strokeTypes.length > 0 && (
        <div style={{ display: 'flex', gap: 16, marginBottom: 12, flexWrap: 'wrap' }}>
          {strokeTypes.map(st => (
            <div key={st} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.72rem', color: 'var(--text-muted)' }}>
              <div style={{ width: 10, height: 10, borderRadius: 2, background: STROKE_COLORS[st] || STROKE_COLORS.unknown }} />
              {STROKE_LABELS[st] || st}
            </div>
          ))}
        </div>
      )}

      {/* Chart */}
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={chartData} margin={{ top: 4, right: 4, left: -16, bottom: 0 }} barCategoryGap="20%">
          <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.05)" />
          <XAxis
            dataKey="lap_number"
            tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            domain={[0, yMax]}
            tickFormatter={v => v === 0 ? '' : fmtPace(v)}
            tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            width={38}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
          {avg_pace_per_100 && (
            <ReferenceLine
              y={avg_pace_per_100}
              stroke="#38bdf8"
              strokeDasharray="4 3"
              strokeOpacity={0.6}
              strokeWidth={1}
            />
          )}
          <Bar dataKey="pace_per_100" radius={[3, 3, 0, 0]} maxBarSize={28}>
            {chartData.map((entry, i) => (
              <Cell
                key={i}
                fill={
                  entry.is_rest
                    ? STROKE_COLORS.rest
                    : (STROKE_COLORS[entry.stroke_type] || STROKE_COLORS.unknown)
                }
                fillOpacity={entry.is_rest ? 0.4 : 0.85}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

import { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, Cell, ResponsiveContainer,
} from 'recharts';

const STROKE_COLORS = {
  freestyle:    '#26c6f9',
  backstroke:   '#a78bfa',
  breaststroke: '#4ade80',
  butterfly:    '#facc15',
  kickboard:    '#fb923c',
  mixed:        '#94a3b8',
  rest:         '#2a2a32',
  unknown:      '#4a4a56',
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

function fmtTime(seconds) {
  if (!seconds) return '—';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

function fmtDelta(currentSec, compareSec) {
  if (!currentSec || !compareSec) return null;
  const diff = currentSec - compareSec;
  if (Math.abs(diff) < 0.5) return { text: '—', color: 'var(--text-muted)' };
  const sign = diff < 0 ? '−' : '+';
  return {
    text: `${sign}${fmtTime(Math.abs(diff))}`,
    color: diff < 0 ? '#4ade80' : '#f87171',
  };
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const unit = d.unit || 'm';
  return (
    <div style={{
      background: '#18181c',
      border: '1px solid #2a2a32',
      borderRadius: 8,
      padding: '10px 14px',
      fontSize: '0.78rem',
      lineHeight: 1.7,
    }}>
      <div style={{ fontWeight: 700, marginBottom: 4, color: 'var(--text-primary)' }}>
        {d.is_rest ? 'Rest' : `Lap ${d.lap_number}`}
      </div>
      {!d.is_rest && (
        <>
          <div style={{ color: STROKE_COLORS[d.stroke_type] || STROKE_COLORS.unknown }}>
            {STROKE_LABELS[d.stroke_type] || 'Unknown stroke'}
          </div>
          <div style={{ color: 'var(--text-muted)' }}>
            Pace: <span style={{ color: 'var(--text-primary)' }}>{fmtTime(d.pace_per_100)}/{unit === 'yd' ? '100yd' : '100m'}</span>
          </div>
          {d.duration_seconds != null && (
            <div style={{ color: 'var(--text-muted)' }}>
              Split: <span style={{ color: 'var(--text-primary)' }}>{fmtTime(d.duration_seconds)}</span>
            </div>
          )}
          {d.stroke_count > 0 && (
            <div style={{ color: 'var(--text-muted)' }}>
              Strokes: <span style={{ color: 'var(--text-primary)' }}>{d.stroke_count}</span>
            </div>
          )}
          {d.avg_heartrate > 0 && (
            <div style={{ color: 'var(--text-muted)' }}>
              HR: <span style={{ color: '#f472b6' }}>{Math.round(d.avg_heartrate)} bpm</span>
            </div>
          )}
        </>
      )}
      {d.is_rest && (
        <div style={{ color: 'var(--text-muted)' }}>{fmtTime(d.duration_seconds)}</div>
      )}
    </div>
  );
}

const BEST_SET_KEYS = ['fastest_lap', 'fastest_50', 'fastest_500', 'fastest_1000'];
const BEST_SET_ICONS = { fastest_lap: '◈', fastest_50: '⇅', fastest_500: '▶▶', fastest_1000: '⬛' };

function BestSets({ bestSets, compareBestSets, swimActivities, compareId, onSelectCompare }) {
  const hasSets = bestSets && Object.keys(bestSets).length > 0;
  if (!hasSets) return null;

  return (
    <div style={{ marginTop: 'var(--space-xl)' }}>
      {/* Section header with compare picker */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
        <span style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)' }}>
          Best Sets
        </span>
        {swimActivities && swimActivities.length > 0 && (
          <select
            value={compareId || ''}
            onChange={e => onSelectCompare(e.target.value ? Number(e.target.value) : null)}
            style={{
              background: '#18181c',
              border: '1px solid #2a2a32',
              borderRadius: 8,
              color: compareId ? '#26c6f9' : 'var(--text-muted)',
              fontSize: '0.72rem',
              padding: '4px 8px',
              cursor: 'pointer',
              outline: 'none',
              maxWidth: 200,
            }}
          >
            <option value="">Compare with…</option>
            {swimActivities.map(s => (
              <option key={s.id} value={s.id}>{s.date} — {s.distance_miles != null ? `${(s.distance_miles * 1760).toFixed(0)}yd` : ''}</option>
            ))}
          </select>
        )}
      </div>

      {/* Column headers when comparing */}
      {compareBestSets && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 4, marginBottom: 6 }}>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', gridColumn: '2' }}>This swim</div>
          <div style={{ fontSize: '0.68rem', color: '#a78bfa', gridColumn: '3' }}>Previous</div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', gridColumn: '4' }}>Delta</div>
        </div>
      )}

      {/* Rows */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {BEST_SET_KEYS.map(key => {
          const cur = bestSets[key];
          if (!cur) return null;
          const cmp = compareBestSets?.[key];
          const delta = fmtDelta(cur.time_seconds, cmp?.time_seconds);

          return (
            <div key={key} style={{
              display: 'grid',
              gridTemplateColumns: compareBestSets ? '1fr 1fr 1fr 1fr' : '1fr 1fr',
              alignItems: 'center',
              padding: '8px 0',
              borderBottom: '1px solid #18181c',
            }}>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ color: '#26c6f9', fontSize: '0.65rem' }}>{BEST_SET_ICONS[key]}</span>
                {cur.label}
              </div>
              <div style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
                {fmtTime(cur.time_seconds)}
              </div>
              {compareBestSets && (
                <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#a78bfa', fontVariantNumeric: 'tabular-nums' }}>
                  {cmp ? fmtTime(cmp.time_seconds) : '—'}
                </div>
              )}
              {compareBestSets && delta && (
                <div style={{ fontSize: '0.8rem', fontWeight: 600, color: delta.color, fontVariantNumeric: 'tabular-nums' }}>
                  {delta.text}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function SwimLapChart({ swimData, compareSwimData, swimActivities, compareId, onSelectCompare }) {
  const { laps = [], pool_length_meters, avg_pace_per_100, best_pace_per_100, best_sets } = swimData || {};

  // Determine display unit based on pool length
  const unit = useMemo(() => {
    if (!pool_length_meters) return 'm';
    const remainder = pool_length_meters % 22.86;
    return remainder < 1 ? 'yd' : 'm';
  }, [pool_length_meters]);

  const poolDisplay = useMemo(() => {
    if (!pool_length_meters) return null;
    if (unit === 'yd') return `${Math.round(pool_length_meters / 0.9144)}yd`;
    return `${Math.round(pool_length_meters)}m`;
  }, [pool_length_meters, unit]);

  const chartData = useMemo(() =>
    laps.map(l => ({ ...l, unit })),
    [laps, unit]
  );

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

  const maxPace = Math.max(...laps.filter(l => l.pace_per_100).map(l => l.pace_per_100));
  const yMax = Math.ceil(maxPace * 1.15 / 10) * 10;

  return (
    <div className="glass-card chart-container" style={{ minWidth: 0 }}>
      {/* Header */}
      <div className="section-header" style={{ marginBottom: 16 }}>
        <div>
          <span className="section-title">Swim Laps</span>
          {poolDisplay && (
            <span className="section-subtitle">{poolDisplay} pool · {laps.filter(l => !l.is_rest).length} laps</span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 16, fontSize: '0.75rem', color: 'var(--text-muted)', alignItems: 'center', flexWrap: 'wrap' }}>
          {avg_pace_per_100 && (
            <span>Avg <span style={{ color: '#26c6f9', fontWeight: 600 }}>{fmtTime(avg_pace_per_100)}/{unit === 'yd' ? '100yd' : '100m'}</span></span>
          )}
          {best_pace_per_100 && (
            <span>Best <span style={{ color: '#4ade80', fontWeight: 600 }}>{fmtTime(best_pace_per_100)}/{unit === 'yd' ? '100yd' : '100m'}</span></span>
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
          <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.04)" />
          <XAxis
            dataKey="lap_number"
            tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            domain={[0, yMax]}
            tickFormatter={v => v === 0 ? '' : fmtTime(v)}
            tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            width={38}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
          {avg_pace_per_100 && (
            <ReferenceLine
              y={avg_pace_per_100}
              stroke="#26c6f9"
              strokeDasharray="4 3"
              strokeOpacity={0.5}
              strokeWidth={1}
            />
          )}
          <Bar dataKey="pace_per_100" radius={[3, 3, 0, 0]} maxBarSize={28}>
            {chartData.map((entry, i) => (
              <Cell
                key={i}
                fill={entry.is_rest ? STROKE_COLORS.rest : (STROKE_COLORS[entry.stroke_type] || STROKE_COLORS.unknown)}
                fillOpacity={entry.is_rest ? 0.3 : 0.85}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* Best Sets */}
      <BestSets
        bestSets={best_sets}
        compareBestSets={compareSwimData?.best_sets}
        swimActivities={swimActivities}
        compareId={compareId}
        onSelectCompare={onSelectCompare}
      />
    </div>
  );
}

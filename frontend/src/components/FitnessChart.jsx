/**
 * FitnessChart — CTL / ATL / TSB training load visualization.
 *
 * Uses a dual-axis ComposedChart:
 *   Left Y-axis  : CTL (fitness, 42-day EMA) and ATL (fatigue, 7-day EMA)
 *   Right Y-axis : TSB (form = CTL - ATL), with reference bands
 *   Background   : subtle daily stress bars
 *
 * Interpretation guide shown in the legend tooltip:
 *   TSB > 0   : Fresh (fitness > fatigue)
 *   TSB < -10 : Accumulated fatigue
 *   TSB < -25 : Overreaching risk
 */
import { useMemo, useState } from 'react';
import {
  ComposedChart, Line, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { useQuery } from '@tanstack/react-query';
import { getFitnessData } from '../utils/api';

const COLORS = {
  ctl:    '#34d399',   // green  — fitness
  atl:    '#fb7185',   // salmon — fatigue
  tsb:    '#818cf8',   // indigo — form
  tsbNeg: '#f87171',   // red    — fatigued form
  stress: '#394040',   // dark   — daily load bars
};

// Seconds → "M:SS" display — not used here but kept for consistency
function fmtDate(str) {
  if (!str) return '';
  // YYYY-MM-DD → "Apr 14"
  try {
    const d = new Date(str + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return str;
  }
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const byKey = Object.fromEntries(payload.map(p => [p.dataKey, p.value]));
  const tsb = byKey.tsb ?? 0;
  const tsbColor = tsb >= 5 ? COLORS.tsb : tsb >= -10 ? '#fbbf24' : COLORS.tsbNeg;

  return (
    <div style={{
      background: 'rgba(19,19,19,0.95)',
      border: '1px solid rgba(255,255,255,0.15)',
      borderRadius: 8,
      padding: '10px 14px',
      fontSize: '0.75rem',
      minWidth: 160,
    }}>
      <div style={{ color: 'var(--text-secondary)', marginBottom: 6, fontWeight: 600 }}>
        {fmtDate(label)}
      </div>
      {byKey.ctl !== undefined && (
        <div style={{ color: COLORS.ctl, marginBottom: 3 }}>
          CTL (Fitness) &nbsp; <strong>{byKey.ctl?.toFixed(1)}</strong>
        </div>
      )}
      {byKey.atl !== undefined && (
        <div style={{ color: COLORS.atl, marginBottom: 3 }}>
          ATL (Fatigue) &nbsp; <strong>{byKey.atl?.toFixed(1)}</strong>
        </div>
      )}
      {byKey.tsb !== undefined && (
        <div style={{ color: tsbColor, marginBottom: 3 }}>
          TSB (Form) &nbsp; <strong>{byKey.tsb?.toFixed(1)}</strong>
        </div>
      )}
      {byKey.daily_stress > 0 && (
        <div style={{ color: COLORS.stress, marginTop: 4, borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 4 }}>
          Load &nbsp; <strong>{byKey.daily_stress?.toFixed(0)}</strong>
        </div>
      )}
    </div>
  );
}

const DATE_PRESETS = [
  { label: '3 Mo', months: 3 },
  { label: '6 Mo', months: 6 },
  { label: '1 Yr', months: 12 },
  { label: '2 Yr', months: 24 },
  { label: 'All',  months: null },
];

export default function FitnessChart() {
  const [months, setMonths] = useState(6);

  const dateFrom = useMemo(() => {
    if (!months) return null;
    const d = new Date();
    d.setMonth(d.getMonth() - months);
    return d.toISOString().slice(0, 10);
  }, [months]);

  const { data: fitnessResult, isLoading } = useQuery({
    queryKey: ['fitness', dateFrom],
    queryFn: () => getFitnessData({ date_from: dateFrom }),
    staleTime: 2 * 60 * 1000,
  });

  const chartData = useMemo(() => {
    const raw = fitnessResult?.data || [];
    // Thin out daily data for longer windows to keep chart performant
    if (raw.length > 365) {
      return raw.filter((_, i) => i % 2 === 0);
    }
    return raw;
  }, [fitnessResult]);

  if (isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 220 }}>
        <div className="loading-spinner" />
      </div>
    );
  }

  if (!chartData.length) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 220, color: 'var(--text-muted)', fontSize: '0.8rem' }}>
        No training data available. Sync activities to see your fitness curve.
      </div>
    );
  }

  return (
    <div>
      {/* ── Header — stacks on mobile, row on desktop ── */}
      <div className="chart-header-stack" style={{ marginBottom: 'var(--space-md)' }}>
        <div>
          <div className="section-title">Fitness &amp; Fatigue</div>
          <p style={{ margin: '4px 0 0', fontSize: '0.68rem', color: 'var(--text-muted)', fontFamily: "'Inter', sans-serif" }}>
            Acute (ATL) vs Chronic (CTL) Training Load
          </p>
        </div>
        <div className="chart-header-controls">
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 16, height: 2, background: COLORS.ctl, borderRadius: 1 }} />
              <span style={{ fontSize: '0.58rem', color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase' }}>Fitness</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 16, height: 0, borderTop: `2px dashed ${COLORS.atl}` }} />
              <span style={{ fontSize: '0.58rem', color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase' }}>Fatigue</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 16, height: 0, borderTop: `2px dashed ${COLORS.tsb}` }} />
              <span style={{ fontSize: '0.58rem', color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase' }}>Form</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 2 }}>
            {DATE_PRESETS.map(p => (
              <button
                key={p.label}
                onClick={() => setMonths(p.months)}
                className="filter-chip"
                style={{
                  fontSize: '0.62rem',
                  padding: '2px 8px',
                  opacity: months === p.months ? 1 : 0.45,
                  background: months === p.months ? 'rgba(52,211,153,0.12)' : undefined,
                  borderColor: months === p.months ? 'rgba(52,211,153,0.4)' : undefined,
                  color: months === p.months ? '#34d399' : undefined,
                }}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── CTL / ATL chart ── */}
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={chartData} margin={{ top: 10, right: 40, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={fmtDate}
            tick={{ fill: '#555', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            yAxisId="load"
            tick={{ fill: '#444', fontSize: 9 }}
            axisLine={false}
            tickLine={false}
            width={28}
          />
          <YAxis
            yAxisId="form"
            orientation="right"
            tick={{ fill: '#444', fontSize: 9 }}
            axisLine={false}
            tickLine={false}
            width={36}
          />
          <Tooltip content={<CustomTooltip />} />

          <ReferenceLine yAxisId="form" y={0} stroke="rgba(255,255,255,0.08)" strokeDasharray="4 4" />

          {/* Daily load bars (very subtle background) */}
          <Bar
            yAxisId="load"
            dataKey="daily_stress"
            fill="rgba(255,255,255,0.04)"
            radius={[1, 1, 0, 0]}
            maxBarSize={6}
          />

          {/* ATL (fatigue) — dashed salmon */}
          <Line
            yAxisId="load"
            type="monotone"
            dataKey="atl"
            stroke={COLORS.atl}
            strokeWidth={1.5}
            strokeDasharray="5 4"
            dot={false}
            activeDot={{ r: 3, fill: COLORS.atl }}
          />

          {/* CTL (fitness) — solid green */}
          <Line
            yAxisId="load"
            type="monotone"
            dataKey="ctl"
            stroke={COLORS.ctl}
            strokeWidth={2.5}
            dot={false}
            activeDot={{ r: 4, fill: COLORS.ctl }}
          />

          {/* TSB (form) — dashed indigo, right axis */}
          <Line
            yAxisId="form"
            type="monotone"
            dataKey="tsb"
            stroke={COLORS.tsb}
            strokeWidth={1.5}
            strokeDasharray="5 3"
            dot={false}
            activeDot={{ r: 3, fill: COLORS.tsb }}
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* ── HR params footnote ── */}
      {fitnessResult?.max_hr && (
        <div style={{ marginTop: 8, fontSize: '0.6rem', color: 'var(--text-muted)', opacity: 0.5 }}>
          TRIMP model · Max HR {fitnessResult.max_hr} bpm · Resting HR {fitnessResult.resting_hr} bpm
        </div>
      )}
    </div>
  );
}

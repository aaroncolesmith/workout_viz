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
import { SCRUB_CURSOR } from '../utils/chartkit';
import { formatShortDate, formatDate } from '../utils/format';

const COLORS = {
  ctl:    '#34d399',   // green  — fitness
  atl:    '#fb7185',   // salmon — fatigue
  tsb:    '#818cf8',   // indigo — form
  tsbNeg: '#f87171',   // red    — fatigued form
  stress: '#394040',   // dark   — daily load bars
};

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const byKey = Object.fromEntries(payload.map(p => [p.dataKey, p.value]));
  const tsb = byKey.tsb ?? 0;
  const tsbColor = tsb >= 5 ? COLORS.tsb : tsb >= -10 ? '#fbbf24' : COLORS.tsbNeg;

  return (
    <div style={{
      background: '#0d0d0f',
      border: '1px solid #2a2a32',
      borderRadius: 8,
      padding: '8px 12px',
      fontSize: 12,
      minWidth: 160,
    }}>
      <div style={{ color: 'var(--text-secondary)', marginBottom: 6, fontWeight: 600 }}>
        {formatDate(label)}
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
  { label: '30D', days: 30 },
  { label: '3 Mo', days: 90 },
  { label: '6 Mo', days: 182 },
  { label: '1 Yr', days: 365 },
  { label: '2 Yr', days: 730 },
  { label: 'All',  days: null },
];

export default function FitnessChart() {
  const [days, setDays] = useState(182);

  const dateFrom = useMemo(() => {
    if (!days) return null;
    const d = new Date();
    d.setDate(d.getDate() - days);
    return d.toISOString().slice(0, 10);
  }, [days]);

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
                onClick={() => setDays(p.days)}
                className="filter-chip"
                style={{
                  fontSize: '0.62rem',
                  padding: '2px 8px',
                  opacity: days === p.days ? 1 : 0.45,
                  background: days === p.days ? 'rgba(52,211,153,0.12)' : undefined,
                  borderColor: days === p.days ? 'rgba(52,211,153,0.4)' : undefined,
                  color: days === p.days ? '#34d399' : undefined,
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
        <ComposedChart data={chartData} margin={{ top: 10, right: 2, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={v => formatShortDate(v)}
            tick={{ fill: '#555', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
            minTickGap={28}
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
            width={30}
          />
          <Tooltip cursor={SCRUB_CURSOR} content={<CustomTooltip />} />

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

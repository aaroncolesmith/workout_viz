/**
 * EfficiencyTrend (COR-2) — pace:HR efficiency over time.
 *
 * EF = meters/min per heartbeat: rises when the same heart rate buys more
 * speed, independent of how hard individual days felt.  Dots are individual
 * runs (tooltip includes aerobic decoupling for long runs); the line is the
 * 42-day rolling mean; the verdict sentence interprets the trend.
 */
import { useQuery } from '@tanstack/react-query';
import {
  ComposedChart, Line, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts';
import { getEfficiencyTrend } from '../utils/api';
import { formatShortDate, formatDate, formatPace } from '../utils/format';
import SafeResponsiveContainer from './SafeResponsiveContainer';

const ACCENT = '#34d399';

export default function EfficiencyTrend({ days = 365 }) {
  const { data } = useQuery({
    queryKey: ['efficiency', days],
    queryFn: () => getEfficiencyTrend({ days }),
    staleTime: 5 * 60 * 1000,
  });

  const points = data?.points || [];
  if (points.length < 3) return null;

  return (
    <div className="glass-card chart-container" style={{ minWidth: 0, minHeight: 300 }}>
      <div className="section-header">
        <span className="section-title">Running Efficiency</span>
        <span className="section-subtitle">speed per heartbeat · higher is fitter</span>
      </div>
      {data.verdict && (
        <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: 8 }}>
          {data.verdict}
        </div>
      )}
      <SafeResponsiveContainer height={230}>
        <ComposedChart data={points} margin={{ top: 5, right: 8, bottom: 0, left: -14 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis
            dataKey="date" tick={{ fontSize: 10 }}
            tickFormatter={v => formatShortDate(v)} minTickGap={28}
          />
          <YAxis
            domain={['auto', 'auto']} tick={{ fontSize: 10 }} width={44}
            tickFormatter={v => v.toFixed(2)}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0]?.payload;
              if (!d) return null;
              return (
                <div style={{ background: '#0d0d0f', border: '1px solid #2a2a32', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>{formatDate(d.date)}</div>
                  <div style={{ color: ACCENT, fontFamily: 'var(--font-display)' }}>
                    EF {d.ef.toFixed(2)} · {formatPace(d.pace)}/mi at {Math.round(d.avg_hr)} bpm
                  </div>
                  {d.decoupling != null && (
                    <div style={{ color: d.decoupling > 5 ? '#fb923c' : 'var(--text-secondary)', marginTop: 2 }}>
                      Decoupling {d.decoupling > 0 ? '+' : ''}{d.decoupling}%
                      {d.decoupling > 5 ? ' — faded late' : ' — held steady'}
                    </div>
                  )}
                </div>
              );
            }}
          />
          <Scatter dataKey="ef" fill={ACCENT} fillOpacity={0.35} r={2.5} isAnimationActive={false} />
          <Line type="monotone" dataKey="ef_rolling" stroke={ACCENT} strokeWidth={2}
                dot={false} isAnimationActive={false} />
        </ComposedChart>
      </SafeResponsiveContainer>
    </div>
  );
}

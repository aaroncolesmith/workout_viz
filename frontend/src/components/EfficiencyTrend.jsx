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
import { CHART_MARGIN, GRID_PROPS, AXIS_TICK, SCRUB_CURSOR } from '../utils/chartkit';
import ChartTooltip from './ChartTooltip';
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
        <ComposedChart data={points} margin={CHART_MARGIN}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis
            dataKey="date" tick={AXIS_TICK}
            tickFormatter={v => formatShortDate(v)} minTickGap={28}
          />
          <YAxis
            domain={['auto', 'auto']} tick={AXIS_TICK} width={44}
            tickFormatter={v => v.toFixed(2)}
          />
          <Tooltip
            cursor={SCRUB_CURSOR}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0]?.payload;
              if (!d) return null;
              return (
                <ChartTooltip title={formatDate(d.date)}>
                  <div style={{ color: ACCENT, fontFamily: 'var(--font-display)' }}>
                    EF {d.ef.toFixed(2)} · {formatPace(d.pace)}/mi at {Math.round(d.avg_hr)} bpm
                  </div>
                  {d.decoupling != null && (
                    <div style={{ color: d.decoupling > 5 ? '#fb923c' : 'var(--text-secondary)', marginTop: 2 }}>
                      Decoupling {d.decoupling > 0 ? '+' : ''}{d.decoupling}%
                      {d.decoupling > 5 ? ' — faded late' : ' — held steady'}
                    </div>
                  )}
                </ChartTooltip>
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

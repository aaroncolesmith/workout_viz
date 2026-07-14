/**
 * ReadinessHistory (RDY-4) — blended readiness score over time.
 *
 * Line is the daily readiness score (load + body signals, exactly as it
 * would have read that morning); amber dots flag days you trained hard on
 * a sub-30 "red" morning.
 */
import { useQuery } from '@tanstack/react-query';
import {
  ComposedChart, Line, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine,
} from 'recharts';
import { getReadinessHistory } from '../utils/api';
import { formatShortDate, formatDate } from '../utils/format';
import SafeResponsiveContainer from './SafeResponsiveContainer';

const ACCENT = '#38bdf8';
const FLAG = '#fbbf24';

const ZONE_LABEL = {
  peak: 'Peak Form', ready: 'Ready', moderate: 'Moderate',
  easy: 'Tired', recovery: 'Recovery',
};

export default function ReadinessHistory({ days = 90 }) {
  const { data } = useQuery({
    queryKey: ['readiness-history', days],
    queryFn: () => getReadinessHistory(days),
    staleTime: 5 * 60 * 1000,
  });

  const points = (data?.data || []).map(p => ({
    ...p,
    flag: p.hard_on_red ? p.score : null,
  }));
  if (points.length < 7) return null;
  const flagged = points.filter(p => p.hard_on_red).length;

  return (
    <div className="glass-card chart-container" style={{ minWidth: 0, minHeight: 300 }}>
      <div className="section-header">
        <span className="section-title">Readiness History</span>
        <span className="section-subtitle">
          {flagged > 0
            ? `${flagged} hard session${flagged === 1 ? '' : 's'} on red days`
            : `last ${days} days`}
        </span>
      </div>
      <SafeResponsiveContainer height={230}>
        <ComposedChart data={points} margin={{ top: 5, right: 8, bottom: 0, left: -8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis
            dataKey="date" tick={{ fontSize: 10 }}
            tickFormatter={v => formatShortDate(v)} minTickGap={28}
          />
          <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} width={40} />
          <ReferenceLine y={30} stroke="#f87171" strokeOpacity={0.25} strokeDasharray="4 4" />
          <ReferenceLine y={70} stroke="#4ade80" strokeOpacity={0.25} strokeDasharray="4 4" />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0]?.payload;
              if (!d) return null;
              return (
                <div style={{ background: '#0d0d0f', border: '1px solid #2a2a32', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>{formatDate(d.date)}</div>
                  <div style={{ color: ACCENT, fontFamily: 'var(--font-display)' }}>
                    Readiness {d.score} · {ZONE_LABEL[d.zone] || d.zone}
                  </div>
                  {d.daily_stress > 0 && (
                    <div style={{ color: 'var(--text-secondary)', marginTop: 2 }}>
                      Training stress {Math.round(d.daily_stress)}
                    </div>
                  )}
                  {d.hard_on_red && (
                    <div style={{ color: FLAG, marginTop: 2 }}>
                      ⚠ Hard session on a red-zone morning
                    </div>
                  )}
                </div>
              );
            }}
          />
          <Line type="monotone" dataKey="score" stroke={ACCENT} strokeWidth={2}
                dot={false} isAnimationActive={false} />
          <Scatter dataKey="flag" fill={FLAG} r={4} isAnimationActive={false} />
        </ComposedChart>
      </SafeResponsiveContainer>
    </div>
  );
}

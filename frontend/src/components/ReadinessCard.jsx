/**
 * ReadinessCard — today's training readiness at a glance.
 *
 * Queries GET /api/stats/readiness (backed by the TRIMP fitness model)
 * and renders a compact banner with score, zone, recommendation, and
 * CTL/ATL/TSB context numbers.
 */
import { useQuery } from '@tanstack/react-query';
import { getReadiness } from '../utils/api';

const ZONE_CONFIG = {
  peak:     { color: '#4ade80', bg: 'rgba(74,222,128,0.08)',  border: 'rgba(74,222,128,0.25)',  label: 'Peak Form'   },
  ready:    { color: '#38bdf8', bg: 'rgba(56,189,248,0.08)',  border: 'rgba(56,189,248,0.25)',  label: 'Ready'       },
  moderate: { color: '#fbbf24', bg: 'rgba(251,191,36,0.08)',  border: 'rgba(251,191,36,0.25)',  label: 'Moderate'    },
  easy:     { color: '#fb923c', bg: 'rgba(251,146,60,0.08)',  border: 'rgba(251,146,60,0.25)',  label: 'Tired'       },
  recovery: { color: '#f87171', bg: 'rgba(248,113,113,0.08)', border: 'rgba(248,113,113,0.25)', label: 'Recovery'    },
};

export default function ReadinessCard() {
  const { data, isLoading } = useQuery({
    queryKey: ['readiness'],
    queryFn: getReadiness,
    staleTime: 2 * 60 * 1000,
  });

  if (isLoading || !data) return null;

  const zone = ZONE_CONFIG[data.zone] || ZONE_CONFIG.moderate;
  const tsbSign = data.tsb >= 0 ? '+' : '';

  return (
    <div style={{
      background: zone.bg,
      border: `1px solid ${zone.border}`,
      borderRadius: 'var(--radius-lg)',
      padding: '14px 20px',
      marginBottom: 'var(--space-lg)',
      display: 'flex',
      alignItems: 'center',
      gap: 20,
      flexWrap: 'wrap',
    }}>
      {/* Score block */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
        <div style={{ width: 6, height: 36, borderRadius: 3, background: zone.color, flexShrink: 0 }} />
        <div>
          <div style={{ fontSize: '2rem', fontWeight: 800, color: zone.color, lineHeight: 1, fontFamily: 'var(--font-mono)' }}>
            {data.score}
          </div>
          <div style={{ fontSize: '0.65rem', color: zone.color, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', opacity: 0.8 }}>
            {zone.label}
          </div>
        </div>
      </div>

      {/* Divider */}
      <div style={{ width: 1, height: 40, background: zone.border, flexShrink: 0 }} />

      {/* Recommendation */}
      <div style={{ flex: 1, minWidth: 180 }}>
        <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>
          Today's Recommendation
        </div>
        <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
          {data.recommendation}
        </div>
      </div>

      {/* Divider */}
      <div style={{ width: 1, height: 40, background: zone.border, flexShrink: 0 }} />

      {/* CTL / ATL / TSB mini stats */}
      <div style={{ display: 'flex', gap: 20, flexShrink: 0 }}>
        {[
          { label: 'Fitness', val: data.ctl.toFixed(1), sub: 'CTL 42d', color: '#38bdf8' },
          { label: 'Fatigue', val: data.atl.toFixed(1), sub: 'ATL 7d',  color: '#fb923c' },
          { label: 'Form',    val: `${tsbSign}${data.tsb.toFixed(1)}`, sub: 'TSB', color: zone.color },
        ].map(({ label, val, sub, color }) => (
          <div key={label} style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '1.1rem', fontWeight: 700, color, fontFamily: 'var(--font-mono)' }}>
              {val}
            </div>
            <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {sub}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

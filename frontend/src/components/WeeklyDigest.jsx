/**
 * WeeklyDigest (COR-4) — the week's narrative, composed server-side from
 * the same services that power the charts, so it can never disagree
 * with them.
 */
import { useQuery } from '@tanstack/react-query';
import { getWeeklyDigest } from '../utils/api';

const KIND_ICON = {
  volume: '📊', efficiency: '⚡', best_moment: '🏆', body: '🫀', insight: '🔍',
};

export default function WeeklyDigest() {
  const { data } = useQuery({
    queryKey: ['weekly-digest'],
    queryFn: getWeeklyDigest,
    staleTime: 10 * 60 * 1000,
  });

  if (!data || data.stats.activities === 0) return null;

  return (
    <div className="glass-card" style={{ padding: 'var(--space-lg)', marginBottom: 'var(--space-xl)' }}>
      <div className="section-header" style={{ marginBottom: 12 }}>
        <span className="section-title">Your Week</span>
        <span className="section-subtitle">
          {data.stats.activities} activities · {data.stats.miles} mi
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {data.sections.map(s => (
          <div key={s.kind} style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
            <span style={{ fontSize: '0.8rem', flexShrink: 0 }} aria-hidden="true">
              {KIND_ICON[s.kind] || '•'}
            </span>
            <div style={{ minWidth: 0 }}>
              <span style={{
                fontSize: '0.62rem', fontWeight: 700, textTransform: 'uppercase',
                letterSpacing: '0.1em', color: 'var(--text-muted)', marginRight: 8,
              }}>
                {s.title}
              </span>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                {s.text}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

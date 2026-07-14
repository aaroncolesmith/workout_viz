/**
 * CorrelationCards (COR-3) — statistically-gated body→performance findings.
 *
 * Each card shows the headline plus the underlying cohort stats (n and
 * effort-adjusted pace for both sides) — never a claim the user can't
 * inspect.  Dismissals persist per-factor in localStorage.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getCorrelations } from '../utils/api';

const DISMISS_KEY = 'volken_dismissed_correlations';

const FACTOR_ICON = { sleep: '🌙', hrv: '📈', rhr: '❤️', rest: '🔋' };

function loadDismissed() {
  try { return new Set(JSON.parse(localStorage.getItem(DISMISS_KEY) || '[]')); }
  catch { return new Set(); }
}

export default function CorrelationCards() {
  const [dismissed, setDismissed] = useState(loadDismissed);
  const { data } = useQuery({
    queryKey: ['correlations'],
    // Wrapped: react-query passes a context object to queryFn, which must
    // not land in the `days` parameter.
    queryFn: () => getCorrelations(),
    staleTime: 10 * 60 * 1000,
  });

  const findings = (data?.findings || []).filter(f => !dismissed.has(f.factor));
  if (!findings.length) return null;

  const dismiss = (factor) => {
    const next = new Set(dismissed);
    next.add(factor);
    setDismissed(next);
    try { localStorage.setItem(DISMISS_KEY, JSON.stringify([...next])); } catch { /* private mode */ }
  };

  return (
    <div style={{ marginBottom: 'var(--space-xl)' }}>
      <div className="section-header">
        <span className="section-title">Patterns in Your Data</span>
        <span className="section-subtitle">effort-adjusted · {data.runs_analyzed} runs analyzed</span>
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: 12,
      }}>
        {findings.slice(0, 3).map(f => (
          <div
            key={f.factor}
            className="glass-card"
            style={{ padding: '14px 16px', position: 'relative' }}
          >
            <button
              onClick={() => dismiss(f.factor)}
              aria-label="Dismiss"
              style={{
                position: 'absolute', top: 8, right: 10, background: 'none',
                border: 'none', color: 'var(--text-muted)', cursor: 'pointer',
                fontSize: '0.8rem', padding: 2,
              }}
            >
              ✕
            </button>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.45, paddingRight: 18 }}>
              {FACTOR_ICON[f.factor] || '•'} {f.headline}
            </div>
            <div style={{ display: 'flex', gap: 14, marginTop: 10 }}>
              {f.cohorts.map(c => (
                <div key={c.label} style={{ fontSize: '0.62rem', color: 'var(--text-secondary)' }}>
                  <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, color: 'var(--text-primary)', fontSize: '0.78rem' }}>
                    {c.adj_pace_str}
                  </span>
                  {' '}· {c.label} ({c.n})
                </div>
              ))}
            </div>
            <div style={{ marginTop: 8, fontSize: '0.58rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: f.confidence === 'high' ? '#4ade80' : '#fbbf24' }}>
              {f.confidence} confidence
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

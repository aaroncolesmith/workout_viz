/**
 * MetricTile — one daily health metric at a glance (BIO-7).
 *
 * Big number (latest value), delta chip vs the 30-day rolling average,
 * and a 30-day sparkline of the 7-day rolling mean.  Colored only by the
 * metric's accent; delta chips use direction-of-goodness (lower resting HR
 * is good, lower HRV is not).
 */
import { METRIC_CONFIG, formatMetricValue, metricUnit } from '../utils/metrics';

function deltaColor(metric, delta) {
  const dir = METRIC_CONFIG[metric]?.goodDirection;
  if (!dir || !delta) return 'var(--text-secondary)';
  const improved = dir === 'up' ? delta > 0 : delta < 0;
  return improved ? '#4ade80' : '#f87171';
}

function Sparkline({ values, accent, width = 92, height = 30 }) {
  if (!values || values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (width - 4) + 2;
    const y = height - 3 - ((v - min) / span) * (height - 6);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const [lastX, lastY] = pts[pts.length - 1].split(',');
  return (
    <svg width={width} height={height} aria-hidden="true" style={{ flexShrink: 0 }}>
      <polyline
        points={pts.join(' ')}
        fill="none"
        stroke={accent}
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity="0.85"
      />
      <circle cx={lastX} cy={lastY} r="2.5" fill={accent} />
    </svg>
  );
}

export default function MetricTile({ data, selected, onClick }) {
  const cfg = METRIC_CONFIG[data.metric] || { accent: 'var(--text-accent)' };
  const delta = data.vs_30d_avg;
  const showDelta = delta != null && data.avg_30d != null;
  const color = deltaColor(data.metric, delta);
  const arrow = delta > 0 ? '▲' : delta < 0 ? '▼' : '—';

  return (
    <button
      onClick={onClick}
      className="glass-card"
      style={{
        padding: '14px 16px',
        textAlign: 'left',
        cursor: 'pointer',
        border: `1px solid ${selected ? `${cfg.accent}66` : 'rgba(255,255,255,0.06)'}`,
        background: selected ? `${cfg.accent}0d` : undefined,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        minWidth: 0,
      }}
    >
      <div style={{
        fontSize: '0.6rem', fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.12em', color: 'var(--text-secondary)',
        display: 'flex', alignItems: 'center', gap: 6,
      }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: cfg.accent, flexShrink: 0 }} />
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {data.label}
        </span>
        {data.out_of_band && (
          <span
            title="Outside your normal range"
            style={{
              marginLeft: 'auto', fontSize: '0.55rem', fontWeight: 700,
              color: '#fbbf24', border: '1px solid #fbbf2455',
              borderRadius: 10, padding: '1px 6px', flexShrink: 0,
            }}
          >
            ⚠ unusual
          </span>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 10, justifyContent: 'space-between' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{
            fontSize: '1.55rem', fontWeight: 800, lineHeight: 1,
            fontFamily: 'var(--font-display)', color: 'var(--text-primary)',
            letterSpacing: '-0.02em',
          }}>
            {formatMetricValue(data.metric, data.today)}
            {metricUnit(data.metric, data.unit) && (
              <span style={{ fontSize: '0.65rem', fontWeight: 600, color: 'var(--text-muted)', marginLeft: 4 }}>
                {metricUnit(data.metric, data.unit)}
              </span>
            )}
          </div>
          <div style={{ fontSize: '0.62rem', marginTop: 5, color, fontWeight: 600 }}>
            {showDelta
              ? <>{arrow} {formatMetricValue(data.metric, Math.abs(delta))} vs 30-day avg</>
              : <span style={{ color: 'var(--text-muted)' }}>building baseline…</span>}
          </div>
        </div>
        <Sparkline values={data.spark_30d} accent={cfg.accent} />
      </div>
    </button>
  );
}

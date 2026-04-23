import { formatDuration, activityColor, activityLabel } from '../utils/format';
import SportBadge from './SportBadge';

// HR zones as % of max HR
const ZONES = [
  { label: 'Z1', name: 'Easy',      min: 0,   max: 0.60, color: '#60a5fa' },
  { label: 'Z2', name: 'Aerobic',   min: 0.60, max: 0.70, color: '#34d399' },
  { label: 'Z3', name: 'Tempo',     min: 0.70, max: 0.80, color: '#fbbf24' },
  { label: 'Z4', name: 'Threshold', min: 0.80, max: 0.90, color: '#fb923c' },
  { label: 'Z5', name: 'Max',       min: 0.90, max: 1.00, color: '#f87171' },
];

function hrZone(avgHr, maxHr) {
  if (!avgHr || !maxHr) return null;
  const pct = avgHr / maxHr;
  return ZONES.find(z => pct >= z.min && pct < z.max) || ZONES[4];
}

function TrainingLoadBar({ avgHr, maxHr, durationMin }) {
  if (!avgHr || !durationMin) return null;

  const restingHr = 60;
  const effectiveMax = maxHr || 185;
  const deltaHr = Math.max(0, Math.min(1, (avgHr - restingHr) / (effectiveMax - restingHr)));
  // Simplified TRIMP: duration × ΔHR × 0.64 × e^(1.92 × ΔHR)
  const trimp = Math.round(durationMin * deltaHr * 0.64 * Math.exp(1.92 * deltaHr));
  // Normalise to 0–100 for display (cap at 150 TRIMP = "very hard")
  const pct = Math.min(100, Math.round((trimp / 150) * 100));
  const zone = hrZone(avgHr, effectiveMax);
  const color = zone?.color || '#38bdf8';

  return (
    <div className="glass-card" style={{ padding: 'var(--space-lg)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, marginBottom: 4 }}>
            Est. Training Load
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, fontFamily: "'Manrope', sans-serif", color }}>
            {trimp}
          </div>
          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: 2 }}>TRIMP units</div>
        </div>
        {zone && (
          <div style={{
            padding: '4px 12px',
            borderRadius: 20,
            background: `${zone.color}18`,
            border: `1px solid ${zone.color}40`,
            fontSize: '0.72rem',
            fontWeight: 600,
            color: zone.color,
          }}>
            {zone.label} · {zone.name}
          </div>
        )}
      </div>

      {/* Load bar */}
      <div style={{ height: 6, background: 'rgba(255,255,255,0.08)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{
          height: '100%',
          width: `${pct}%`,
          background: `linear-gradient(90deg, #60a5fa, ${color})`,
          borderRadius: 3,
          transition: 'width 0.6s ease',
        }} />
      </div>

      {/* Zone scale labels */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6 }}>
        {ZONES.map(z => (
          <span key={z.label} style={{
            fontSize: '0.6rem',
            color: zone?.label === z.label ? z.color : 'rgba(255,255,255,0.25)',
            fontWeight: zone?.label === z.label ? 700 : 400,
          }}>
            {z.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function HRSummaryCard({ activity }) {
  const { average_heartrate, max_heartrate } = activity;
  if (!average_heartrate) return null;

  const effectiveMax = max_heartrate || 185;
  const avgPct = Math.round((average_heartrate / effectiveMax) * 100);
  const zone = hrZone(average_heartrate, effectiveMax);

  return (
    <div className="glass-card" style={{ padding: 'var(--space-lg)' }}>
      <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, marginBottom: 12 }}>
        Heart Rate
      </div>

      <div style={{ display: 'flex', gap: 'var(--space-xl)', marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, fontFamily: "'Manrope', sans-serif", color: '#f472b6' }}>
            {Math.round(average_heartrate)}
          </div>
          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>avg bpm</div>
        </div>
        {max_heartrate && (
          <div>
            <div style={{ fontSize: '1.6rem', fontWeight: 700, fontFamily: "'Manrope', sans-serif", color: '#ef4444' }}>
              {Math.round(max_heartrate)}
            </div>
            <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>max bpm</div>
          </div>
        )}
        <div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, fontFamily: "'Manrope', sans-serif", color: zone?.color || '#94a3b8' }}>
            {avgPct}%
          </div>
          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>of max</div>
        </div>
      </div>

      {/* HR zone segments */}
      <div style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', gap: 2 }}>
        {ZONES.map(z => {
          const active = zone?.label === z.label;
          return (
            <div
              key={z.label}
              style={{
                flex: 1,
                background: active ? z.color : `${z.color}28`,
                borderRadius: 2,
                transition: 'background 0.3s',
              }}
            />
          );
        })}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 5 }}>
        {ZONES.map(z => (
          <span key={z.label} style={{
            fontSize: '0.6rem',
            color: zone?.label === z.label ? z.color : 'rgba(255,255,255,0.25)',
            fontWeight: zone?.label === z.label ? 700 : 400,
          }}>
            {z.name}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function StrengthOverview({ activity }) {
  const color = activityColor(activity.type);
  const label = activityLabel(activity.type);

  const isAppleHealth = activity.source === 'apple_health';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>

      {/* Type + source banner */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 'var(--space-md)',
        padding: 'var(--space-md) var(--space-lg)',
        background: `${color}0a`,
        border: `1px solid ${color}20`,
        borderRadius: 10,
      }}>
        <SportBadge type={activity.type} size={40} />
        <div>
          <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>{label}</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 2 }}>
            {formatDuration(activity.moving_time_min)} session
            {isAppleHealth && (
              <span style={{
                marginLeft: 8,
                padding: '1px 8px',
                background: 'rgba(251,146,60,0.12)',
                border: '1px solid rgba(251,146,60,0.3)',
                borderRadius: 10,
                color: '#fb923c',
                fontSize: '0.65rem',
                fontWeight: 600,
              }}>
                Apple Health
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Training load + HR side by side */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-md)' }}>
        <TrainingLoadBar
          avgHr={activity.average_heartrate}
          maxHr={activity.max_heartrate}
          durationMin={activity.moving_time_min}
        />
        <HRSummaryCard activity={activity} />
      </div>

      {/* No HR data state */}
      {!activity.average_heartrate && (
        <div className="glass-card" style={{ padding: 'var(--space-xl)', textAlign: 'center' }}>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            No heart rate data available for this session.
          </div>
        </div>
      )}
    </div>
  );
}

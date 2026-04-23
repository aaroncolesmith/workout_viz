import {
  formatPace, formatDistance, formatDuration, formatHR,
  formatElevation, activityColor,
  activityLabel, isStrengthType, formatDate, formatActivityName,
} from '../utils/format';
import SportBadge from './SportBadge';

export default function ActivityHeader({ activity }) {
  const isStrength = isStrengthType(activity.type);
  const isAppleHealth = activity.source === 'apple_health';
  const accentColor = activityColor(activity.type);

  return (
    <>
      {/* ── Two-column hero header ── */}
      <div className="detail-header">
        {/* Left: badge + type label + title + date */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <SportBadge type={activity.type} size={30} />
            <span style={{
              fontFamily: "'Inter', sans-serif",
              fontSize: '0.62rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.16em',
              color: accentColor,
            }}>
              {activityLabel(activity.sport_type || activity.type)}
            </span>
            {activity.trainer && (
              <span style={{ fontSize: '0.62rem', color: 'var(--text-muted)', fontFamily: "'Inter', sans-serif" }}>
                · Indoor
              </span>
            )}
            {isAppleHealth && (
              <span style={{
                fontSize: '0.62rem', color: '#fb923c',
                background: 'rgba(251,146,60,0.1)',
                border: '1px solid rgba(251,146,60,0.25)',
                borderRadius: 10, padding: '1px 8px',
                fontFamily: "'Inter', sans-serif",
              }}>
                Apple Health
              </span>
            )}
          </div>
          <h1 className="detail-title">{formatActivityName(activity)}</h1>
          <div className="detail-meta" style={{ marginTop: 8 }}>
            <span className="detail-meta-item">{formatDate(activity.date)}</span>
          </div>
        </div>

        {/* Right: hero distance (GPS) or hero duration (strength) */}
        {!isStrength && activity.distance_miles ? (
          <div className="detail-hero-metric">
            <div className="detail-hero-value" style={{ color: accentColor }}>
              {formatDistance(activity.distance_miles)}
            </div>
            <div className="detail-hero-unit">Total Miles</div>
          </div>
        ) : isStrength && activity.moving_time_min ? (
          <div className="detail-hero-metric">
            <div className="detail-hero-value" style={{ color: accentColor, fontSize: '3.5rem' }}>
              {formatDuration(activity.moving_time_min)}
            </div>
            <div className="detail-hero-unit">Duration</div>
          </div>
        ) : null}
      </div>

      {/* ── Horizontal stat bar ── */}
      <div className="detail-stats-grid">
        {!isStrength && (
          <div className="glass-card stat-card">
            <span className="stat-label">Distance</span>
            <span className="stat-value">
              {formatDistance(activity.distance_miles)}<span className="stat-unit">mi</span>
            </span>
          </div>
        )}

        <div className="glass-card stat-card">
          <span className="stat-label">Duration</span>
          <span className="stat-value">{formatDuration(activity.moving_time_min)}</span>
        </div>

        {!isStrength && (
          <div className="glass-card stat-card">
            <span className="stat-label">Pace</span>
            <span className="stat-value">
              {formatPace(activity.pace)}<span className="stat-unit">/mi</span>
            </span>
          </div>
        )}

        <div className="glass-card stat-card">
          <span className="stat-label">Avg HR</span>
          <span className="stat-value" style={{ color: activity.average_heartrate ? '#f472b6' : 'inherit' }}>
            {formatHR(activity.average_heartrate)}<span className="stat-unit">bpm</span>
          </span>
        </div>

        <div className="glass-card stat-card">
          <span className="stat-label">Max HR</span>
          <span className="stat-value" style={{ color: activity.max_heartrate ? '#ef4444' : 'inherit' }}>
            {formatHR(activity.max_heartrate)}<span className="stat-unit">bpm</span>
          </span>
        </div>

        {!isStrength && (
          <div className="glass-card stat-card">
            <span className="stat-label">Elevation</span>
            <span className="stat-value">
              {formatElevation(activity.total_elevation_gain)}<span className="stat-unit">ft</span>
            </span>
          </div>
        )}

        {activity.average_cadence && !isStrength && (
          <div className="glass-card stat-card">
            <span className="stat-label">Cadence</span>
            <span className="stat-value">
              {Math.round(activity.average_cadence * 2)}<span className="stat-unit">spm</span>
            </span>
          </div>
        )}

        {activity.average_watts && (
          <div className="glass-card stat-card">
            <span className="stat-label">Avg Power</span>
            <span className="stat-value">
              {Math.round(activity.average_watts)}<span className="stat-unit">W</span>
            </span>
          </div>
        )}
      </div>
    </>
  );
}

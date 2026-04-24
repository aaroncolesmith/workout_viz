import SyncPanel from '../components/SyncPanel';

function SettingsSection({ title, description, children }) {
  return (
    <div
      className="glass-card"
      style={{
        padding: 'var(--space-xl)',
        marginBottom: 'var(--space-lg)',
      }}
    >
      <div style={{ marginBottom: 'var(--space-md)' }}>
        <div style={{
          fontSize: '0.65rem',
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.18em',
          color: 'var(--text-muted)',
          marginBottom: 4,
        }}>
          {title}
        </div>
        {description && (
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            {description}
          </div>
        )}
      </div>
      {children}
    </div>
  );
}

export default function Settings() {
  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <div className="section-header" style={{ marginBottom: 'var(--space-lg)' }}>
        <span className="section-title">Settings</span>
      </div>

      <SettingsSection
        title="Data Sources"
        description="Connect Strava, import Apple Health exports, or backfill splits. HealthKit sync runs automatically from the iOS companion app."
      >
        <SyncPanel />
      </SettingsSection>
    </div>
  );
}

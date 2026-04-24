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

function NativeHealthKitSection() {
  const hasNative = typeof window !== 'undefined' && window.WorkoutVizNative?.available;

  if (!hasNative) {
    return (
      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
        Apple HealthKit sync is only available from the iOS companion app.
      </div>
    );
  }

  const trigger = () => window.WorkoutVizNative.backfill();
  const reset   = () => {
    if (window.confirm('Reset backfill progress? Next backfill will re-upload every workout.')) {
      window.WorkoutVizNative.resetBackfill();
    }
  };

  const btn = (label, onClick, tone) => (
    <button
      onClick={onClick}
      style={{
        background: 'transparent',
        border: `1px solid ${tone}55`,
        color: tone,
        fontFamily: "'Inter', sans-serif",
        fontWeight: 600,
        fontSize: '0.75rem',
        letterSpacing: '0.04em',
        padding: '8px 14px',
        borderRadius: 6,
        cursor: 'pointer',
      }}
    >
      {label}
    </button>
  );

  return (
    <div style={{ display: 'flex', gap: 'var(--space-sm)', flexWrap: 'wrap' }}>
      {btn('Backfill HealthKit', trigger, '#34d399')}
      {btn('Reset progress',     reset,   '#f87171')}
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
        title="Apple HealthKit (iOS app)"
        description="Pull every workout from your iPhone's HealthKit — including indoor treadmill runs — and compute splits and fastest segments. Resumable; tap again if interrupted."
      >
        <NativeHealthKitSection />
      </SettingsSection>

      <SettingsSection
        title="Strava & Apple Health export"
        description="Connect Strava to pull activities and splits, or drop in an Apple Health export.zip for a one-shot import."
      >
        <SyncPanel />
      </SettingsSection>
    </div>
  );
}

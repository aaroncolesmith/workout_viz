import { activityColor } from '../utils/format';

const TYPE_ABBR = {
  Run: 'RUN', VirtualRun: 'RUN', TrailRun: 'TRL',
  Ride: 'RIDE', VirtualRide: 'RIDE',
  Hike: 'HIKE', Walk: 'WALK', Swim: 'SWIM',
  WeightTraining: 'STR', Workout: 'WKT', HIIT: 'HIIT',
  Yoga: 'YOGA', CoreTraining: 'CORE', Pilates: 'PLTS',
  Crossfit: 'CRFT', Rowing: 'ROW', Elliptical: 'ELLI',
  AlpineSki: 'SKI', NordicSki: 'SKI',
  Recovery: 'RCVR', MindAndBody: 'MIND',
  FunctionalStrengthTraining: 'STR',
  StairStepper: 'STAIR',
};

export default function SportBadge({ type, size = 36 }) {
  const color = activityColor(type);
  const abbr = TYPE_ABBR[type] || (type ? type.slice(0, 4).toUpperCase() : '?');
  const radius = Math.round(size * 0.2);
  return (
    <div style={{
      minWidth: size,
      height: size,
      padding: '0 6px',
      borderRadius: radius,
      background: `${color}14`,
      border: `1px solid ${color}35`,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      flexShrink: 0,
      color,
      fontFamily: "var(--font-display)",
      fontWeight: 800,
      fontSize: Math.round(size * 0.24),
      letterSpacing: '-0.01em',
      whiteSpace: 'nowrap',
      userSelect: 'none',
    }}>
      {abbr}
    </div>
  );
}

import { activityColor } from '../utils/format';

const TYPE_ABBR = {
  Run: 'RN', VirtualRun: 'RN', TrailRun: 'TR',
  Ride: 'RI', VirtualRide: 'RI',
  Hike: 'HK', Walk: 'WK', Swim: 'SW',
  WeightTraining: 'WT', Workout: 'WO', HIIT: 'HI',
  Yoga: 'YG', CoreTraining: 'CR', Pilates: 'PL',
  Crossfit: 'CF', Rowing: 'RW', Elliptical: 'EL',
  AlpineSki: 'SK', NordicSki: 'SK',
  Recovery: 'RC', MindAndBody: 'MB',
  FunctionalStrengthTraining: 'ST',
  StairStepper: 'SS',
};

export default function SportBadge({ type, size = 36 }) {
  const color = activityColor(type);
  const abbr = TYPE_ABBR[type] || (type ? type.slice(0, 2).toUpperCase() : '??');
  const radius = Math.round(size * 0.2);
  return (
    <div style={{
      width: size,
      height: size,
      borderRadius: radius,
      background: `${color}14`,
      border: `1px solid ${color}35`,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      flexShrink: 0,
      color,
      fontFamily: "'Manrope', sans-serif",
      fontWeight: 800,
      fontSize: Math.round(size * 0.28),
      letterSpacing: '-0.02em',
      userSelect: 'none',
    }}>
      {abbr}
    </div>
  );
}

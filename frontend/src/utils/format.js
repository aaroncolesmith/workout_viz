/**
 * Formatting utilities for workout metrics.
 */

/** Format pace as M:SS / mi */
export function formatPace(pace) {
  if (!pace || pace <= 0 || pace > 30) return '—';
  const mins = Math.floor(pace);
  const secs = Math.round((pace - mins) * 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/** Format distance with unit */
export function formatDistance(miles) {
  if (miles == null) return '—';
  return miles < 10 ? miles.toFixed(2) : miles.toFixed(1);
}

/** Format duration in minutes as Hh Mm or Mm */
export function formatDuration(minutes) {
  if (!minutes) return '—';
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const hrs = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);
  return `${hrs}h ${mins}m`;
}

/** Format time in seconds as H:MM:SS or M:SS */
export function formatTime(seconds) {
  if (seconds == null) return '—';
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.round(seconds % 60);
  if (hrs > 0) return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/** Format heart rate */
export function formatHR(hr) {
  if (!hr) return '—';
  return Math.round(hr).toString();
}

/** Format elevation */
export function formatElevation(meters) {
  if (!meters && meters !== 0) return '—';
  const feet = meters * 3.28084;
  return `${Math.round(feet)}`;
}

// Activity type category sets — used for conditional UI logic
export const STRENGTH_TYPES = new Set([
  'WeightTraining', 'Workout', 'HIIT', 'CoreTraining',
  'Yoga', 'Pilates', 'Dance', 'MindAndBody', 'Recovery',
  'Cooldown', 'Crossfit', 'Elliptical', 'StairStepper',
  'Rowing', 'FunctionalStrengthTraining',
]);

export const GPS_TYPES = new Set([
  'Run', 'VirtualRun', 'TrailRun', 'Ride', 'VirtualRide',
  'Hike', 'Walk', 'Swim', 'Kayaking', 'Canoeing',
  'NordicSki', 'AlpineSki', 'Snowshoe', 'IceSkate',
]);

export const SWIM_TYPES = new Set(['Swim']);

export function isStrengthType(type) { return STRENGTH_TYPES.has(type); }
export function isGpsType(type)      { return GPS_TYPES.has(type) || !STRENGTH_TYPES.has(type); }
export function isSwimType(type)     { return SWIM_TYPES.has(type); }

/** Get icon character for activity type (text icons — no emoji for premium feel) */
export function activityIcon(type) {
  const icons = {
    Run: '🏃', VirtualRun: '🏃', TrailRun: '🏔',
    Ride: '🚴', VirtualRide: '🚴',
    Hike: '🥾', Walk: '🚶',
    Swim: '🏊',
    WeightTraining: '🏋️',
    Workout: '💪', FunctionalStrengthTraining: '💪',
    HIIT: '⚡',
    CoreTraining: '🎯',
    Yoga: '🧘', Pilates: '🧘',
    MindAndBody: '🧘',
    Crossfit: '🔥',
    Elliptical: '〇',
    StairStepper: '📶',
    Rowing: '🚣',
    Recovery: '💆',
    AlpineSki: '⛷️', NordicSki: '⛷️',
    Soccer: '⚽',
  };
  return icons[type] || '🏃';
}

/** Get CSS class for activity type */
export function activityClass(type) {
  if (STRENGTH_TYPES.has(type)) return 'workout';
  const classes = {
    Run: 'run', VirtualRun: 'run', TrailRun: 'run',
    Ride: 'ride', VirtualRide: 'ride',
    Hike: 'hike', Walk: 'walk',
    Swim: 'swim',
  };
  return classes[type] || '';
}

/** Get color for activity type */
export function activityColor(type) {
  if (STRENGTH_TYPES.has(type)) return '#f472b6';
  const colors = {
    Run: '#38bdf8', VirtualRun: '#38bdf8', TrailRun: '#38bdf8',
    Ride: '#818cf8', VirtualRide: '#818cf8',
    Hike: '#34d399', Walk: '#fbbf24',
    Swim: '#22d3ee',
  };
  return colors[type] || '#94a3b8';
}

/** Human-readable label for activity type */
export function activityLabel(type) {
  const labels = {
    WeightTraining: 'Weight Training',
    FunctionalStrengthTraining: 'Strength Training',
    CoreTraining: 'Core Training',
    MindAndBody: 'Mind & Body',
    VirtualRun: 'Virtual Run',
    VirtualRide: 'Virtual Ride',
    TrailRun: 'Trail Run',
    NordicSki: 'Nordic Ski',
    AlpineSki: 'Alpine Ski',
    StairStepper: 'Stair Stepper',
  };
  return labels[type] || type;
}

/** Parse date string in local timezone if it's a YYYY-MM-DD format */
export function parseLocalDate(dateStr) {
  if (!dateStr || dateStr === 'NaT') return new Date(NaN);
  if (typeof dateStr === 'string' && dateStr.length === 10 && dateStr.includes('-')) {
    // Append T12:00:00 to ensure it stays on the same day in the user's local timezone
    return new Date(`${dateStr}T12:00:00`);
  }
  return new Date(dateStr);
}

/** Format date string nicely */
export function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = parseLocalDate(dateStr);
  if (isNaN(d)) return dateStr;
  return d.toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric'
  });
}

/** Format as M/D (e.g. 3/5) */
export function formatShortDate(dateStr) {
  if (!dateStr) return '';
  const d = parseLocalDate(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

/** Format date for relative display */
export function formatRelativeDate(dateStr) {
  if (!dateStr) return '';
  const d = parseLocalDate(dateStr);
  if (isNaN(d.getTime())) return dateStr;

  const now = new Date();
  // Strip time from both dates to get purely daily diff
  const dStart = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const nowStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());

  const diffDays = Math.floor((nowStart - dStart) / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  return formatDate(dateStr);
}

/**
 * Compact relative age: "5d ago", "2.4wk ago", "6.5M ago", "1.2yr ago".
 * Intended for dense UI like timeline cards.
 */
export function formatRelativeAge(dateStr) {
  if (!dateStr) return '';
  const d = parseLocalDate(dateStr);
  if (isNaN(d.getTime())) return dateStr;

  const now = new Date();
  const dStart = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const nowStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diffDays = Math.floor((nowStart - dStart) / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return '1d ago';
  if (diffDays < 14) return `${diffDays}d ago`;
  if (diffDays < 60) {
    const wks = diffDays / 7;
    return `${Number.isInteger(Math.round(wks * 10) / 10) ? Math.round(wks) : (wks).toFixed(1)}wk ago`;
  }
  if (diffDays < 365) {
    const mos = diffDays / 30.44;
    return `${mos >= 10 ? Math.round(mos) : mos.toFixed(1)}M ago`;
  }
  const yrs = diffDays / 365.25;
  return `${yrs >= 10 ? Math.round(yrs) : yrs.toFixed(1)}yr ago`;
}

/**
 * Relative distance between two dates, from the perspective of the reference.
 * Returns strings like "3 weeks before", "2 months after", "same day".
 * @param {string} dateStr - The date to describe
 * @param {string} referenceDateStr - The anchor date (e.g. the current activity's date)
 */
export function formatRelativeTo(dateStr, referenceDateStr) {
  if (!dateStr || !referenceDateStr) return formatRelativeAge(dateStr);
  const d = parseLocalDate(dateStr);
  const ref = parseLocalDate(referenceDateStr);
  if (isNaN(d.getTime()) || isNaN(ref.getTime())) return formatRelativeAge(dateStr);

  const dDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const rDay = new Date(ref.getFullYear(), ref.getMonth(), ref.getDate());
  const diffDays = Math.round((dDay - rDay) / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'same day';

  const abs = Math.abs(diffDays);
  const dir = diffDays < 0 ? 'before' : 'after';

  if (abs < 14) return `${abs}d ${dir}`;
  if (abs < 60) {
    const wks = Math.round(abs / 7);
    return `${wks}wk ${dir}`;
  }
  if (abs < 365) {
    const mos = Math.round(abs / 30.44);
    return `${mos}mo ${dir}`;
  }
  const yrs = (abs / 365.25).toFixed(1);
  return `${yrs}yr ${dir}`;
}

/** Format activity name with date to avoid duplicates */
export function formatActivityName(act) {
  if (!act) return '';
  const d = parseLocalDate(act.date);
  const dateStr = d.toLocaleDateString('en-US', { month: 'numeric', day: 'numeric', year: '2-digit' });
  return `${act.name} - ${dateStr}`;
}


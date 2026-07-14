/**
 * Shared presentation config for daily health metrics (BIO-7/8).
 * Slugs match backend health_metrics_service.KNOWN_METRICS.
 */

// goodDirection: 'up' | 'down' | null (deviation-neutral — direction isn't
// inherently good or bad, e.g. respiratory rate or body mass).
export const METRIC_CONFIG = {
  resting_heartrate: { accent: '#f472b6', goodDirection: 'down' },
  hrv_sdnn:          { accent: '#a78bfa', goodDirection: 'up' },
  vo2max:            { accent: '#26c6f9', goodDirection: 'up' },
  respiratory_rate:  { accent: '#4ade80', goodDirection: null },
  blood_oxygen:      { accent: '#fbbf24', goodDirection: 'up' },
  steps:             { accent: '#fb923c', goodDirection: 'up' },
  active_energy:     { accent: '#fb923c', goodDirection: 'up' },
  body_mass:         { accent: '#2dd4bf', goodDirection: null },
  sleep_asleep:      { accent: '#818cf8', goodDirection: 'up' },
  sleep_in_bed:      { accent: '#818cf8', goodDirection: null },
};

// Sleep values format as "7h 32m" — the unit is baked into the string.
export function metricUnit(metric, unit) {
  return metric === 'sleep_asleep' || metric === 'sleep_in_bed' ? '' : unit;
}

export function formatMetricValue(metric, value) {
  if (value == null) return '—';
  if (metric === 'steps' || metric === 'active_energy') {
    return Math.round(value).toLocaleString();
  }
  if (metric === 'sleep_asleep' || metric === 'sleep_in_bed') {
    const h = Math.floor(value);
    const m = Math.round((value - h) * 60);
    return `${h}h ${String(m).padStart(2, '0')}m`;
  }
  return (Math.round(value * 10) / 10).toLocaleString();
}

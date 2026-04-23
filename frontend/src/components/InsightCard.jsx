/**
 * InsightCard — post-workout analysis panel.
 *
 * Fetches GET /api/activities/:id/insights and renders a structured
 * breakdown of what was notable about this workout:
 *   - Headline (most notable finding)
 *   - PR badge (if applicable)
 *   - Segment ranking ("3rd fastest 10K")
 *   - HR efficiency vs similar-pace workouts
 *   - Split quality (negative / positive / even split)
 *   - Pace trend vs 8-week rolling average
 *   - Volume context (longest / shortest recently)
 *
 * Each section degrades gracefully — null sections are simply not shown.
 */
import { useQuery } from '@tanstack/react-query';
import { getActivityInsights } from '../utils/api';

function Chip({ color = '#38bdf8', label, value, sub }) {
  return (
    <div style={{
      background: `${color}10`,
      border: `1px solid ${color}30`,
      borderRadius: 10,
      padding: '10px 14px',
      flex: '1 1 160px',
      minWidth: 0,
    }}>
      <div style={{ fontSize: '0.62rem', color: `${color}bb`, textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4, fontWeight: 600 }}>
        {label}
      </div>
      <div style={{ fontSize: '0.9rem', fontWeight: 700, color, fontFamily: 'var(--font-mono)', lineHeight: 1.2 }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 3 }}>
          {sub}
        </div>
      )}
    </div>
  );
}

export default function InsightCard({ activityId }) {
  const { data, isLoading } = useQuery({
    queryKey: ['insights', activityId],
    queryFn: () => getActivityInsights(activityId),
    enabled: Boolean(activityId),
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="glass-card" style={{ padding: 'var(--space-md)', marginBottom: 'var(--space-xl)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-muted)', fontSize: '0.8rem' }}>
          <div className="loading-spinner" style={{ width: 16, height: 16 }} />
          Analyzing workout…
        </div>
      </div>
    );
  }

  if (!data) return null;

  const {
    headline, pr, segment_ranking, hr_efficiency,
    split_quality, pace_trend, volume_context,
  } = data;

  // If there's truly nothing to show, render nothing
  const hasAnyInsight = headline || pr || segment_ranking || hr_efficiency
    || split_quality || pace_trend || volume_context;
  if (!hasAnyInsight) return null;

  const chips = [];

  // PR chip
  if (pr) {
    chips.push(
      <Chip
        key="pr"
        color="#fbbf24"
        label={pr.is_first_effort ? `First ${pr.distance_label}` : `PR · ${pr.distance_label}`}
        value={pr.time_str}
        sub={pr.improvement || pr.pace_str}
      />
    );
  }

  // Segment ranking
  if (segment_ranking && !pr) {
    const rankColor = segment_ranking.rank === 1 ? '#fbbf24'
      : segment_ranking.rank <= 3 ? '#fb923c'
      : segment_ranking.rank <= 10 ? '#38bdf8' : '#94a3b8';
    chips.push(
      <Chip
        key="rank"
        color={rankColor}
        label={segment_ranking.distance_label}
        value={`${segment_ranking.ordinal} fastest`}
        sub={`of ${segment_ranking.total} efforts · ${segment_ranking.time_str}`}
      />
    );
  }

  // HR efficiency
  if (hr_efficiency) {
    const hrColor = hr_efficiency.better ? '#4ade80' : '#fb923c';
    const sign    = hr_efficiency.better ? '↓' : '↑';
    chips.push(
      <Chip
        key="hr"
        color={hrColor}
        label="HR Efficiency"
        value={`${sign} ${Math.abs(hr_efficiency.delta_bpm).toFixed(0)} bpm`}
        sub={`vs ${hr_efficiency.sample_size} similar-pace workouts at ${hr_efficiency.pace_str}`}
      />
    );
  }

  // Split quality
  if (split_quality && split_quality.split_type !== 'even') {
    const splitColor = split_quality.split_type === 'negative' ? '#4ade80' : '#fb923c';
    const splitLabel = split_quality.split_type === 'negative' ? 'Negative Split' : 'Positive Split';
    const splitDesc  = split_quality.split_type === 'negative'
      ? `${split_quality.first_pace_str} → ${split_quality.second_pace_str}`
      : `${split_quality.first_pace_str} → ${split_quality.second_pace_str}`;
    chips.push(
      <Chip
        key="split"
        color={splitColor}
        label={splitLabel}
        value={`${split_quality.delta_str} diff`}
        sub={splitDesc}
      />
    );
  } else if (split_quality && split_quality.split_type === 'even') {
    chips.push(
      <Chip
        key="split"
        color="#38bdf8"
        label="Even Split"
        value="Well paced"
        sub={`${split_quality.first_pace_str} · ${split_quality.total_splits / 10}mi analyzed`}
      />
    );
  }

  // Pace trend
  if (pace_trend) {
    const trendColor = pace_trend.faster ? '#4ade80' : '#fb923c';
    const trendSign  = pace_trend.faster ? '↑' : '↓';
    chips.push(
      <Chip
        key="trend"
        color={trendColor}
        label={`${pace_trend.window_weeks}-week Trend`}
        value={`${trendSign} ${pace_trend.delta_str}`}
        sub={`You: ${pace_trend.my_pace_str} · Avg: ${pace_trend.avg_pace_str}`}
      />
    );
  }

  // Volume context
  if (volume_context) {
    const volColor = volume_context.context === 'longest' ? '#a78bfa' : '#94a3b8';
    chips.push(
      <Chip
        key="vol"
        color={volColor}
        label={`${volume_context.context === 'longest' ? 'Longest' : 'Shortest'} in ${volume_context.window_weeks}w`}
        value={`${volume_context.distance} mi`}
        sub={`vs recent ${volume_context.window_weeks} weeks`}
      />
    );
  }

  return (
    <div className="glass-card" style={{ padding: 'var(--space-md)', marginBottom: 'var(--space-xl)' }}>
      {/* Section label */}
      <div style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>
        Workout Analysis
      </div>

      {/* Headline */}
      {headline && (
        <div style={{
          fontSize: '0.92rem',
          fontWeight: 600,
          color: 'var(--text-primary)',
          marginBottom: chips.length ? 14 : 0,
          lineHeight: 1.4,
        }}>
          {headline}
        </div>
      )}

      {/* Insight chips grid */}
      {chips.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {chips}
        </div>
      )}
    </div>
  );
}

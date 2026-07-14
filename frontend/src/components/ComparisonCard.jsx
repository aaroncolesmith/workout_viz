/**
 * ComparisonCard (CMP-4) — the post-workout verdict, zero configuration.
 *
 * Renders GET /activities/{id}/comparison: rank badge, verdict sentence,
 * pace/HR/effort deltas vs the auto-selected cohort (route → similar →
 * distance band), and a history sparkline of every attempt with this one
 * highlighted.  Hidden entirely when the backend has nothing to say.
 */
import { useQuery } from '@tanstack/react-query';
import { getActivityComparison } from '../utils/api';

const EFFICIENCY_COLOR = {
  breakthrough: '#4ade80',
  easier:       '#4ade80',
  pushed:       '#26c6f9',
  faster:       '#26c6f9',
  consistent:   '#38bdf8',
  easy_day:     '#8a8a96',
  slower:       '#8a8a96',
  strained:     '#fb923c',
  tough:        '#fb923c',
};

function ordinal(n) {
  const mod100 = n % 100;
  if (mod100 >= 10 && mod100 <= 20) return `${n}th`;
  return `${n}${['st', 'nd', 'rd'][(n % 10) - 1] || 'th'}`;
}

function fmtDelta(v, unit, invert = false) {
  if (v == null) return null;
  const better = invert ? v < 0 : v > 0;
  const word = v === 0 ? 'even' : better ? (invert ? 'faster' : 'higher') : (invert ? 'slower' : 'lower');
  return { text: `${Math.abs(Math.round(v))}${unit}`, word, positive: better };
}

function HistorySpark({ history, rankMetric, color, width = 150, height = 44 }) {
  const key = rankMetric === 'time' ? 'time_seconds' : 'pace';
  const pts = history.filter(h => h[key] != null);
  if (pts.length < 2) return null;
  const vals = pts.map(p => p[key]);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  // Lower time/pace is better → plot inverted so "up" = faster
  const coords = pts.map((p, i) => ({
    x: (i / (pts.length - 1)) * (width - 10) + 5,
    y: 6 + ((p[key] - min) / span) * (height - 12),
    current: p.is_current,
  }));
  return (
    <svg width={width} height={height} aria-hidden="true" style={{ flexShrink: 0 }}>
      <polyline
        points={coords.map(c => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ')}
        fill="none" stroke={color} strokeWidth="1.5" opacity="0.5"
        strokeLinejoin="round" strokeLinecap="round"
      />
      {coords.map((c, i) => (
        <circle
          key={i} cx={c.x} cy={c.y}
          r={c.current ? 4.5 : 2.5}
          fill={c.current ? color : `${color}55`}
          stroke={c.current ? '#0d0d0f' : 'none'} strokeWidth={c.current ? 1.5 : 0}
        />
      ))}
    </svg>
  );
}

export default function ComparisonCard({ activityId }) {
  const { data, isLoading } = useQuery({
    queryKey: ['comparison', activityId],
    queryFn: () => getActivityComparison(activityId),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  if (isLoading || !data || !data.verdict) return null;

  const color = EFFICIENCY_COLOR[data.efficiency] || '#38bdf8';
  const pace = fmtDelta(data.deltas?.pace_vs_avg_sec_mi, 's/mi', true);
  const hr = fmtDelta(data.deltas?.hr_vs_avg_bpm, ' bpm');

  const stats = [
    pace && { label: 'pace vs avg', value: pace.text, word: pace.word, good: pace.positive },
    hr && { label: 'HR vs avg', value: hr.text, word: hr.word, good: !hr.positive },
    data.effort && {
      label: 'effort (90d)', value: `${Math.round(data.effort.percentile)}`,
      word: 'percentile', good: null,
    },
  ].filter(Boolean);

  return (
    <div style={{
      background: `${color}0d`,
      border: `1px solid ${color}33`,
      borderRadius: 'var(--radius-lg)',
      padding: '16px 20px',
      marginBottom: 'var(--space-xl)',
      display: 'flex',
      alignItems: 'center',
      gap: 18,
      flexWrap: 'wrap',
    }}>
      {/* Rank badge */}
      {data.rank && data.rank_of ? (
        <div style={{ textAlign: 'center', flexShrink: 0 }}>
          <div style={{
            fontSize: '1.7rem', fontWeight: 800, color, lineHeight: 1,
            fontFamily: 'var(--font-display)', letterSpacing: '-0.02em',
          }}>
            {ordinal(data.rank)}
          </div>
          <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 3 }}>
            of {data.rank_of}
          </div>
        </div>
      ) : data.effort && (
        <div style={{ textAlign: 'center', flexShrink: 0 }}>
          <div style={{ fontSize: '1.7rem', fontWeight: 800, color, lineHeight: 1, fontFamily: 'var(--font-display)' }}>
            {Math.round(data.effort.percentile)}
          </div>
          <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 3 }}>
            effort pctl
          </div>
        </div>
      )}

      <div style={{ width: 1, alignSelf: 'stretch', background: `${color}26`, flexShrink: 0 }} />

      {/* Verdict */}
      <div style={{ flex: 1, minWidth: 200 }}>
        <div style={{
          fontSize: '0.62rem', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: '0.14em', color, marginBottom: 4,
        }}>
          How this compares{data.cohort ? ` · ${data.cohort.label}` : ''}
        </div>
        <div style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.45 }}>
          {data.verdict}
        </div>
      </div>

      {/* Delta stats */}
      {stats.length > 0 && (
        <div style={{ display: 'flex', gap: 18, flexShrink: 0 }}>
          {stats.map(s => (
            <div key={s.label} style={{ textAlign: 'center' }}>
              <div style={{
                fontSize: '1.05rem', fontWeight: 700, fontFamily: 'var(--font-display)',
                color: s.good == null ? 'var(--text-primary)' : s.good ? '#4ade80' : '#fb923c',
              }}>
                {s.value}
              </div>
              <div style={{ fontSize: '0.58rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginTop: 2 }}>
                {s.word} · {s.label}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Attempt history — up = faster */}
      {data.history?.length > 1 && (
        <div style={{ flexShrink: 0, textAlign: 'center' }}>
          <HistorySpark history={data.history} rankMetric={data.rank_metric} color={color} />
          <div style={{ fontSize: '0.55rem', color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            attempts · up = faster
          </div>
        </div>
      )}
    </div>
  );
}

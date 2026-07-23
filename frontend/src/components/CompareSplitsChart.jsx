import { useQueries } from '@tanstack/react-query';
import { ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import SafeResponsiveContainer from './SafeResponsiveContainer';
import ChartTooltip from './ChartTooltip';
import { CHART_MARGIN, GRID_PROPS, AXIS_TICK, SCRUB_CURSOR } from '../utils/chartkit';
import { getActivitySplits } from '../utils/api';
import { buildMileSplits } from '../utils/splits';
import { formatPace, formatHR, formatDate } from '../utils/format';

const PALETTE = ['#38bdf8', '#fb7185', '#34d399', '#f59e0b', '#a78bfa', '#f472b6'];

function MileChart({ title, unit, series, maxMile, valueKey, formatValue, reversed }) {
  const yDomain = (() => {
    const vals = series.flatMap(s => s.rows.map(r => r[valueKey]).filter(v => v != null));
    if (!vals.length) return ['auto', 'auto'];
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const pad = (max - min || 1) * 0.15;
    return [Math.max(0, min - pad), max + pad];
  })();

  return (
    <div className="glass-card chart-container" style={{ minWidth: 0, minHeight: 300, padding: 'var(--space-lg)', marginBottom: 'var(--space-lg)' }}>
      <div className="section-header" style={{ marginBottom: 12 }}>
        <span className="section-title">{title}</span>
        <span className="section-subtitle">by mile</span>
      </div>
      <SafeResponsiveContainer height={240}>
        <ComposedChart margin={CHART_MARGIN}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis
            dataKey="mile"
            type="number"
            domain={[1, Math.max(maxMile, 1)]}
            allowDecimals={false}
            tick={AXIS_TICK}
            tickFormatter={v => `${v}mi`}
          />
          <YAxis domain={yDomain} tick={AXIS_TICK} width={46}
                 reversed={reversed} tickFormatter={v => formatValue(v)} />
          <Tooltip
            cursor={SCRUB_CURSOR}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              return (
                <ChartTooltip title={`Mile ${label}`}>
                  {payload.map(p => (
                    <div key={p.dataKey + (p.name || '')} style={{ color: p.color }}>
                      {p.name}: <strong>{formatValue(p.value)}{unit}</strong>
                    </div>
                  ))}
                </ChartTooltip>
              );
            }}
          />
          {series.map(s => (
            <Line
              key={s.id}
              name={s.label}
              data={s.rows.filter(r => !r.partial && r[valueKey] != null)}
              dataKey={valueKey}
              type="monotone"
              stroke={s.color}
              strokeWidth={s.isBase ? 3 : 1.75}
              strokeOpacity={s.isBase ? 1 : 0.85}
              dot={false}
              isAnimationActive={false}
              activeDot={{ r: 4, fill: s.color, stroke: '#0d0d0f', strokeWidth: 2 }}
            />
          ))}
        </ComposedChart>
      </SafeResponsiveContainer>
    </div>
  );
}

export default function CompareSplitsChart({ baseActivity, comparisonActivities }) {
  const activities = [
    { ...baseActivity, isBase: true },
    ...comparisonActivities.map(a => ({ ...a, isBase: false })),
  ].slice(0, 6);

  const results = useQueries({
    queries: activities.map(a => ({
      queryKey: ['activity-splits-compare', a.id],
      queryFn: () => getActivitySplits(a.id),
      staleTime: 5 * 60 * 1000,
    })),
  });

  const loading = results.some(r => r.isLoading);

  const series = activities.map((a, i) => ({
    id: a.id,
    label: a.isBase ? 'This workout' : formatDate(a.date),
    color: PALETTE[i % PALETTE.length],
    isBase: a.isBase,
    rows: buildMileSplits(results[i]?.data?.splits || []),
  }));

  const maxMile = Math.max(0, ...series.map(s =>
    s.rows.filter(r => !r.partial).reduce((max, r) => Math.max(max, r.mile), 0)
  ));

  if (loading) {
    return (
      <div className="glass-card" style={{ padding: 'var(--space-xl)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
        Loading comparison…
      </div>
    );
  }

  if (maxMile === 0) {
    return (
      <div className="glass-card" style={{ padding: 'var(--space-xl)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
        No mile-split data available for these workouts yet.
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, marginBottom: 'var(--space-md)' }}>
        {series.map(s => (
          <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: s.color }} />
            {s.label}
          </div>
        ))}
      </div>
      <MileChart
        title="Pace" unit="/mi" series={series} maxMile={maxMile}
        valueKey="pace_per_mile" formatValue={formatPace} reversed
      />
      <MileChart
        title="Heart Rate" unit=" bpm" series={series} maxMile={maxMile}
        valueKey="avg_hr" formatValue={formatHR}
      />
    </div>
  );
}

/**
 * Body — daily health metrics dashboard (BIO-7/BIO-8).
 *
 * Tile grid: today's snapshot of every synced metric with rolling-average
 * deltas.  Selecting a tile opens the detail chart: raw daily values,
 * 7d/30d rolling means, and the "normal range" baseline band, with a
 * plain-language interpretation line.
 */
import { Fragment, useState, useMemo, useRef, useCallback, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceArea,
} from 'recharts';
import { getHealthSummary, getHealthMetric } from '../utils/api';
import { formatShortDate, formatDate } from '../utils/format';
import { METRIC_CONFIG, formatMetricValue, metricUnit } from '../utils/metrics';
import MetricTile from '../components/MetricTile';
import { CHART_MARGIN, GRID_PROPS, AXIS_TICK, SCRUB_CURSOR } from '../utils/chartkit';
import ChartTooltip from '../components/ChartTooltip';
import SafeResponsiveContainer from '../components/SafeResponsiveContainer';

const RANGES = [
  { label: '30D', days: 30 },
  { label: '90D', days: 90 },
  { label: '1Y',  days: 365 },
  { label: 'All', days: 3650 },
];

function interpretation(c) {
  const unit = metricUnit(c.metric, c.unit);
  const val = (v) => `${formatMetricValue(c.metric, Math.abs(v))}${unit ? ` ${unit}` : ''}`;
  if (c.baseline_band && c.out_of_band) {
    const side = c.today > c.baseline_band.upper ? 'above' : 'below';
    return `Today's ${c.label.toLowerCase()} is ${side} your typical range `
      + `(${formatMetricValue(c.metric, c.baseline_band.lower)}–${val(c.baseline_band.upper)}).`;
  }
  if (c.vs_30d_avg == null) {
    return 'Not enough history yet — keep syncing to build your baseline.';
  }
  if (Math.abs(c.vs_30d_avg) < 1e-9) {
    return `Exactly on your 30-day average.`;
  }
  const dir = c.vs_30d_avg > 0 ? 'above' : 'below';
  return `${val(c.vs_30d_avg)} ${dir} your 30-day average — within your normal range.`;
}

function ComparisonStats({ c }) {
  const items = [
    { label: 'vs yesterday', v: c.vs_yesterday },
    { label: 'vs 7-day avg', v: c.vs_7d_avg },
    { label: 'vs 30-day avg', v: c.vs_30d_avg },
    { label: 'vs 1-year avg', v: c.vs_365d_avg },
  ];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: 10 }}>
      {items.map(({ label, v }) => (
        <div key={label} style={{
          background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: 8, padding: '8px 12px', textAlign: 'center',
        }}>
          <div style={{
            fontSize: '1rem', fontWeight: 700, fontFamily: 'var(--font-display)',
            color: v == null ? 'var(--text-muted)' : 'var(--text-primary)',
          }}>
            {v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${formatMetricValue(c.metric, Math.abs(v))}`}
          </div>
          <div style={{ fontSize: '0.58rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 2 }}>
            {label}
          </div>
        </div>
      ))}
    </div>
  );
}

function LegendRow({ accent, hasBand }) {
  const items = [
    { swatch: <span style={{ width: 8, height: 8, borderRadius: '50%', background: accent, opacity: 0.45 }} />, label: 'daily' },
    { swatch: <span style={{ width: 14, height: 2, background: accent, borderRadius: 1 }} />, label: '7-day avg' },
    { swatch: <span style={{ width: 14, height: 0, borderTop: '2px dashed var(--text-secondary)' }} />, label: '30-day avg' },
    ...(hasBand ? [{ swatch: <span style={{ width: 12, height: 8, background: `${accent}18`, border: `1px solid ${accent}30`, borderRadius: 2 }} />, label: 'normal range' }] : []),
  ];
  return (
    <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: '0.62rem', color: 'var(--text-secondary)' }}>
      {items.map(({ swatch, label }) => (
        <span key={label} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
          {swatch}{label}
        </span>
      ))}
    </div>
  );
}

function MetricDetail({ metric }) {
  const [days, setDays] = useState(90);
  const { data, isLoading } = useQuery({
    queryKey: ['health-metric', metric, days],
    queryFn: () => getHealthMetric(metric, days),
    staleTime: 2 * 60 * 1000,
  });

  const cfg = METRIC_CONFIG[metric] || { accent: 'var(--text-accent)' };
  const points = useMemo(() => data?.points || [], [data]);
  const band = data?.comparison?.baseline_band || null;

  // Recharts has no prop to dismiss an active tooltip on its own — on touch
  // devices a tap pins it open with nothing to "mouse out" of. Remounting
  // the chart (via key) resets its internal hover state; animations are
  // already off so the remount is invisible except for the tooltip closing.
  const [chartKey, setChartKey] = useState(0);
  const fadeTimer = useRef(null);
  const resetFadeTimer = useCallback(() => {
    if (fadeTimer.current) clearTimeout(fadeTimer.current);
    fadeTimer.current = setTimeout(() => setChartKey(k => k + 1), 3000);
  }, []);
  useEffect(() => () => {
    if (fadeTimer.current) clearTimeout(fadeTimer.current);
  }, []);

  const yDomain = useMemo(() => {
    const vals = points.map(p => p.value).filter(v => v != null);
    if (band) vals.push(band.lower, band.upper);
    if (!vals.length) return ['auto', 'auto'];
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const pad = (max - min || Math.abs(max) || 1) * 0.12;
    return [Math.max(0, min - pad), max + pad];
  }, [points, band]);

  if (isLoading || !data) {
    return <div className="loading-state" style={{ minHeight: 200 }}><div className="loading-spinner" /></div>;
  }

  return (
    <div className="glass-card chart-container" style={{ padding: 'var(--space-lg)' }}>
      <div className="section-header" style={{ flexWrap: 'wrap', gap: 8 }}>
        <span className="section-title">{data.label}</span>
        <div style={{ display: 'flex', gap: 6 }}>
          {RANGES.map(r => {
            const active = days === r.days;
            return (
              <button
                key={r.label}
                onClick={() => setDays(r.days)}
                style={{
                  padding: '3px 10px', borderRadius: 20, fontSize: '12px',
                  fontWeight: active ? 700 : 500, cursor: 'pointer',
                  border: `1px solid ${active ? cfg.accent : '#2a2a32'}`,
                  background: active ? cfg.accent : 'transparent',
                  color: active ? '#000' : 'var(--text-secondary)',
                  fontFamily: 'var(--font-body)', transition: 'all 0.15s',
                }}
              >
                {r.label}
              </button>
            );
          })}
        </div>
      </div>

      {data.comparison && (
        <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', margin: '2px 0 14px' }}>
          {interpretation(data.comparison)}
        </div>
      )}

      <div style={{ marginBottom: 8 }}>
        <LegendRow accent={cfg.accent} hasBand={!!band} />
      </div>

      <SafeResponsiveContainer
        height={260}
        onMouseMove={resetFadeTimer}
        onMouseDown={resetFadeTimer}
        onTouchStart={resetFadeTimer}
        onTouchMove={resetFadeTimer}
      >
        <ComposedChart key={chartKey} data={points} margin={CHART_MARGIN}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis
            dataKey="date"
            tick={AXIS_TICK}
            tickFormatter={v => formatShortDate(v)}
            minTickGap={28}
          />
          <YAxis domain={yDomain} tick={AXIS_TICK} width={54}
                 tickFormatter={v => (Math.round(v * 10) / 10).toLocaleString()} />
          {band && (
            <ReferenceArea
              y1={band.lower} y2={band.upper}
              fill={cfg.accent} fillOpacity={0.07}
              stroke={cfg.accent} strokeOpacity={0.18}
            />
          )}
          <Tooltip
            cursor={SCRUB_CURSOR}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0]?.payload;
              if (!d) return null;
              return (
                <ChartTooltip title={formatDate(d.date)}>
                  <div style={{ color: cfg.accent, fontFamily: 'var(--font-display)' }}>
                    {formatMetricValue(metric, d.value)} {metricUnit(metric, data.unit)}
                  </div>
                  {d.rolling_7d != null && (
                    <div style={{ color: cfg.accent, opacity: 0.7, marginTop: 2 }}>
                      7-day avg: {formatMetricValue(metric, d.rolling_7d)} {metricUnit(metric, data.unit)}
                    </div>
                  )}
                  {d.rolling_30d != null && (
                    <div style={{ color: 'var(--text-secondary)', marginTop: 2 }}>
                      30-day avg: {formatMetricValue(metric, d.rolling_30d)} {metricUnit(metric, data.unit)}
                    </div>
                  )}
                </ChartTooltip>
              );
            }}
          />
          {/* Rendered as a dot-only Line (not Scatter) so the hover marker —
              Recharts' activeDot — highlights the actual raw value, not a
              smoothed average. */}
          <Line type="monotone" dataKey="value" stroke="none" isAnimationActive={false}
                dot={{ r: 2.5, fill: cfg.accent, fillOpacity: 0.35, strokeWidth: 0 }}
                activeDot={{ r: 5, fill: cfg.accent, stroke: '#0d0d0f', strokeWidth: 2 }} />
          <Line type="monotone" dataKey="rolling_7d" stroke={cfg.accent} strokeWidth={2}
                dot={false} activeDot={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="rolling_30d" stroke="var(--text-secondary)" strokeWidth={1.5}
                strokeDasharray="5 4" dot={false} activeDot={false} isAnimationActive={false} />
        </ComposedChart>
      </SafeResponsiveContainer>

      <div style={{ marginTop: 14 }}>
        {data.comparison && <ComparisonStats c={data.comparison} />}
      </div>
    </div>
  );
}

export default function Body() {
  const { data, isLoading } = useQuery({
    queryKey: ['health-summary'],
    queryFn: getHealthSummary,
    staleTime: 2 * 60 * 1000,
  });
  const metrics = data?.metrics || [];
  const [selected, setSelected] = useState(null);

  if (isLoading) {
    return (
      <div className="loading-state">
        <div className="loading-spinner" />
        <span>Loading your health data...</span>
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 'var(--space-xl)' }}>
        <div style={{
          fontSize: '11px', fontWeight: 700, letterSpacing: '0.1em',
          textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 4,
        }}>
          Daily Health Metrics
        </div>
        <div className="hero-title">Body</div>
      </div>

      {metrics.length === 0 ? (
        <div className="glass-card" style={{ padding: 'var(--space-xl)', textAlign: 'center' }}>
          <div style={{ fontSize: '1rem', fontWeight: 600, marginBottom: 8 }}>No health metrics yet</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', maxWidth: 420, margin: '0 auto' }}>
            Open the Volken iOS app and allow Health access — resting heart rate,
            HRV, sleep, and more will sync automatically and show up here with
            trends against your own baselines.
          </div>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))',
          gap: 12,
        }}>
          {metrics.map(m => {
            const isOpen = m.metric === selected;
            return (
              <Fragment key={m.metric}>
                <MetricTile
                  data={m}
                  selected={isOpen}
                  onClick={() => setSelected(isOpen ? null : m.metric)}
                />
                {isOpen && (
                  <div style={{ gridColumn: '1 / -1' }}>
                    <MetricDetail metric={m.metric} />
                  </div>
                )}
              </Fragment>
            );
          })}
        </div>
      )}
    </div>
  );
}

import React, { useMemo } from 'react';
import { ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import SafeResponsiveContainer from './SafeResponsiveContainer';
import { CHART_MARGIN, GRID_PROPS, AXIS_TICK, SCRUB_CURSOR } from '../utils/chartkit';
import ChartTooltip from './ChartTooltip';
import { formatTime, formatPace } from '../utils/format';

const ACCENT = '#26c6f9';

export default function SplitPaceChart({
  splitChartData,
  xAxisType,
  handleSetXAxisType,
  handleFetchDetails,
  syncingDetails,
}) {
  const yDomain = useMemo(() => {
    const vals = splitChartData.map(d => d.pace_smooth).filter(v => v != null);
    if (!vals.length) return ['auto', 'auto'];
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const pad = (max - min || 1) * 0.15;
    return [Math.max(0, min - pad), max + pad];
  }, [splitChartData]);

  return (
    <div className="glass-card chart-container" style={{ minWidth: 0, minHeight: 350, padding: 'var(--space-lg)' }}>
      <div className="section-header" style={{ marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <div>
          <span className="section-title">Pace</span>
          <span className="section-subtitle">smoothed trend, per split</span>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {[{ key: 'distance', label: 'Distance' }, { key: 'time', label: 'Time' }].map(o => {
            const active = xAxisType === o.key;
            return (
              <button
                key={o.key}
                onClick={() => handleSetXAxisType(o.key)}
                style={{
                  padding: '3px 10px', borderRadius: 20, fontSize: '12px',
                  fontWeight: active ? 700 : 500, cursor: 'pointer',
                  border: `1px solid ${active ? ACCENT : '#2a2a32'}`,
                  background: active ? ACCENT : 'transparent',
                  color: active ? '#000' : 'var(--text-secondary)',
                  fontFamily: 'var(--font-body)', transition: 'all 0.15s',
                }}
              >
                {o.label}
              </button>
            );
          })}
        </div>
      </div>

      {splitChartData.length > 0 ? (
        <>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: '0.62rem', color: 'var(--text-secondary)', marginBottom: 8 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: ACCENT, opacity: 0.4 }} />
              per-split
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 14, height: 2, background: ACCENT, borderRadius: 1 }} />
              trend
            </span>
          </div>
          <SafeResponsiveContainer height={250}>
            <ComposedChart data={splitChartData} margin={CHART_MARGIN}>
              <CartesianGrid {...GRID_PROPS} />
              <XAxis
                dataKey={xAxisType === 'distance' ? 'mile' : 'time'}
                type={xAxisType === 'distance' ? 'category' : 'number'}
                tick={AXIS_TICK}
                tickFormatter={v => xAxisType === 'distance' ? `${v}mi` : formatTime(v)}
                minTickGap={28}
              />
              <YAxis domain={yDomain} tick={AXIS_TICK} width={46}
                     reversed tickFormatter={v => formatPace(v)} />
              <Tooltip
                cursor={SCRUB_CURSOR}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0]?.payload;
                  if (!d) return null;
                  return (
                    <ChartTooltip title={xAxisType === 'distance' ? `Mile ${d.mile}` : formatTime(d.time)}>
                      {d.pace_per_mile != null && (
                        <div style={{ color: ACCENT, fontFamily: 'var(--font-display)' }}>
                          {formatPace(d.pace_per_mile)} /mi
                        </div>
                      )}
                      {d.pace_smooth != null && (
                        <div style={{ color: ACCENT, opacity: 0.7, marginTop: 2 }}>
                          trend: {formatPace(d.pace_smooth)} /mi
                        </div>
                      )}
                    </ChartTooltip>
                  );
                }}
              />
              <Line type="monotone" dataKey="pace_per_mile" stroke="none" isAnimationActive={false}
                    dot={{ r: 2, fill: ACCENT, fillOpacity: 0.4, strokeWidth: 0 }} activeDot={false} />
              <Line type="monotone" dataKey="pace_smooth" stroke={ACCENT} strokeWidth={2.5}
                    dot={false} isAnimationActive={false}
                    activeDot={{ r: 5, fill: ACCENT, stroke: '#0d0d0f', strokeWidth: 2 }} />
            </ComposedChart>
          </SafeResponsiveContainer>
        </>
      ) : (
        <div style={{ height: 250, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 15, border: '1px dashed var(--border-medium)', borderRadius: 12 }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Granular split data not yet synced for this activity</span>
          <button
            className="filter-chip"
            onClick={handleFetchDetails}
            disabled={syncingDetails}
            style={{ fontSize: '0.7rem' }}
          >
            {syncingDetails ? 'Syncing...' : 'Fetch Granular Data'}
          </button>
        </div>
      )}
    </div>
  );
}

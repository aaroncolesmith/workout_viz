import React from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceArea, Line } from 'recharts';
import SafeResponsiveContainer from './SafeResponsiveContainer';
import { formatTime, formatHR, formatActivityName } from '../utils/format';

export default function SplitHRChart({
  activity,
  comparisonActivities,
  splitChartData,
  chartColors,
  xAxisType,
  handleSetXAxisType,
  handleFetchDetails,
  syncingDetails,
  hrZoom,
}) {
  return (
    <div className="glass-card chart-container" style={{ minWidth: 0, minHeight: 350 }}>
      <div className="section-header" style={{ marginBottom: 20 }}>
        <div>
          <span className="section-title">Heart Rate Detail</span>
          <span className="section-subtitle">per split</span>
        </div>
        <div className="filter-bar" style={{ margin: 0 }}>
          <button 
            className={`filter-chip ${xAxisType === 'distance' ? 'active' : ''}`}
            onClick={() => handleSetXAxisType('distance')}
            style={{ fontSize: '0.65rem', padding: '2px 10px' }}
          >
            Distance
          </button>
          <button 
            className={`filter-chip ${xAxisType === 'time' ? 'active' : ''}`}
            onClick={() => handleSetXAxisType('time')}
            style={{ fontSize: '0.65rem', padding: '2px 10px' }}
          >
            Time
          </button>
        </div>
      </div>

      {splitChartData.length > 0 ? (
        <div style={{ position: 'relative' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8, marginBottom: 4, minHeight: 22 }}>
            {hrZoom.isZoomed ? (
              <button 
                className="filter-chip"
                onClick={hrZoom.reset}
                style={{ fontSize: '0.6rem', padding: '2px 10px', background: 'rgba(244, 114, 182, 0.2)', color: '#f472b6', borderColor: 'rgba(244, 114, 182, 0.4)' }}
              >
                ↺ Reset Zoom
              </button>
            ) : (
              <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)', opacity: 0.5, fontStyle: 'italic' }}>drag to zoom</span>
            )}
          </div>
          <SafeResponsiveContainer height={250}>
            <AreaChart 
              data={hrZoom.filteredData.length ? hrZoom.filteredData : splitChartData}
              style={{ cursor: hrZoom.drag ? 'col-resize' : 'crosshair' }}
              onMouseDown={hrZoom.onMouseDown}
              onMouseMove={hrZoom.onMouseMove}
              onMouseUp={hrZoom.onMouseUp}
              onMouseLeave={hrZoom.onMouseLeave}
            >
              <defs>
                <linearGradient id="hrGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
                </linearGradient>
              </defs>

              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis 
                dataKey={xAxisType === 'distance' ? 'mile' : 'time'} 
                type={xAxisType === 'distance' ? 'category' : 'number'}
                tick={{ fontSize: 10 }}
                tickFormatter={v => xAxisType === 'distance' ? `${v}mi` : formatTime(v)}
              />
              <YAxis tick={{ fontSize: 10 }} domain={['auto', 'auto']} />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0]?.payload;
                  return (
                    <div style={{ background: 'rgba(19,19,19,0.95)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>
                        {xAxisType === 'distance' ? `Distance: ${d.mile} mi` : `Time: ${formatTime(d.time)}`}
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 20, color: '#38bdf8', marginBottom: 2 }}>
                        <span>{formatActivityName(activity)}:</span>
                        <span>{formatHR(d.avg_hr)} bpm</span>
                      </div>
                      {comparisonActivities.map((ca, idx) => (
                        <div key={ca.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 20, color: chartColors[idx % chartColors.length] }}>
                          <span>{formatActivityName(ca)}:</span>
                          <span>{d[`comp_${ca.id}_hr`] ? formatHR(d[`comp_${ca.id}_hr`]) : '—'} bpm</span>
                        </div>
                      ))}
                    </div>
                  );
                }}
              />
              <Area
                name={formatActivityName(activity)}
                type="monotone"
                dataKey="avg_hr"
                stroke="#38bdf8"
                fill="url(#hrGrad)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: '#38bdf8' }}
                connectNulls
              />

              {comparisonActivities.map((ca, idx) => (
                <Line
                  key={ca.id}
                  name={formatActivityName(ca)}
                  type="monotone"
                  dataKey={`comp_${ca.id}_hr`}
                  stroke={chartColors[idx % chartColors.length]}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
              ))}
              <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: 10, color: 'var(--text-muted)' }} />
              {hrZoom.referenceAreaProps && (
                <ReferenceArea 
                  x1={hrZoom.referenceAreaProps.x1}
                  x2={hrZoom.referenceAreaProps.x2}
                  fill="rgba(244, 114, 182, 0.2)"
                />
              )}
            </AreaChart>
          </SafeResponsiveContainer>
        </div>
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

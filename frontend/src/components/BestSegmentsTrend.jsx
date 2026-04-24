import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ScatterChart, Scatter, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Cell, ReferenceArea
} from 'recharts';
import { useQuery } from '@tanstack/react-query';
import { getBestSegmentsTrend } from '../utils/api';
import { formatPace, formatTime, formatDate, formatActivityName, formatShortDate } from '../utils/format';
import SafeResponsiveContainer from './SafeResponsiveContainer';
import { useChartZoom } from '../hooks/useChartZoom';

const SEGMENTS = [
  { label: '1mi', distance: 1.0 },
  { label: '2mi', distance: 2.0 },
  { label: '5k', distance: 3.107 },
  { label: '5mi', distance: 5.0 },
  { label: '10k', distance: 6.214 },
  { label: '10mi', distance: 10.0 },
  { label: 'Half', distance: 13.1 },
  { label: 'Full', distance: 26.2 },
];

export default function BestSegmentsTrend({ type: typeProp, date_from }) {
  const navigate = useNavigate();
  const [selectedSegment, setSelectedSegment] = useState(SEGMENTS[0]);
  const [internalSelectedType, setInternalSelectedType] = useState('Run');

  // React to prop changes
  const selectedType = typeProp || internalSelectedType;

  const { data: trendData, isLoading } = useQuery({
    queryKey: ['best-segments', selectedType, selectedSegment.distance, date_from],
    queryFn: () => getBestSegmentsTrend({ 
      type: selectedType, 
      distance: selectedSegment.distance,
      date_from 
    }),
  });

  const rawData = useMemo(() => {
    return (trendData?.data || []).map(d => ({
      ...d,
      timestamp: new Date(d.date + 'T12:00:00').getTime()
    }));
  }, [trendData]);

  // Identify top 3 and top 10
  const { top10, top3Ids } = useMemo(() => {
    const sorted = [...rawData].sort((a, b) => a.time_seconds - b.time_seconds);
    const t10 = sorted.slice(0, 10).map((d, i) => ({
      ...d,
      rank: i + 1,
      // Short label for bar chart
      label: formatShortDate(d.date)
    }));
    const t3Ids = new Set(t10.slice(0, 3).map(d => d.activity_id));
    return { top10: t10, top3Ids: t3Ids };
  }, [rawData]);

  // Zoom hook
  const zoom = useChartZoom({
    data: rawData,
    xKey: 'timestamp',
    yKey: 'time_seconds',
    mode: 'numeric'
  });

  // Explicit x-axis ticks to prevent Recharts from generating one tick per data point,
  // which causes duplicate key warnings when multiple activities share the same date.
  const xAxisTicks = useMemo(() => {
    if (!rawData.length) return [];
    const ts = rawData.map(d => d.timestamp);
    const [lo, hi] = zoom.xDomain ?? [Math.min(...ts), Math.max(...ts)];
    if (lo >= hi) return [lo];
    return [0, 1, 2, 3, 4].map(i => lo + Math.round(i * (hi - lo) / 4));
  }, [rawData, zoom.xDomain]);

  const chartColor = '#10b981'; // Emerald/Green for best results
  const highlightColor = '#fbbf24'; // Amber for top 3

  const TooltipContent = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    const d = payload[0]?.payload;
    const isTop3 = top3Ids.has(d.activity_id);
    return (
      <div
        className="custom-tooltip"
        style={{
          background: 'rgba(19,19,19,0.95)',
          border: `1px solid ${isTop3 ? highlightColor : 'rgba(255,255,255,0.15)'}`,
          borderRadius: 12, 
          padding: '12px', 
          fontSize: 12,
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 10px 10px -5px rgba(0, 0, 0, 0.4)',
          pointerEvents: 'auto', // Keep the content interactive
          minWidth: 180,
          zIndex: 1000
        }}
        onClick={(e) => {
          e.stopPropagation();
          navigate(`/activity/${d.activity_id}`);
        }}
      >
        <div style={{ fontWeight: 600, marginBottom: 4, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: 8 }}>
          {isTop3 && <span style={{ color: highlightColor }}>★</span>}
          {d.activity_name}
        </div>
        <div style={{ color: '#94a3b8', marginBottom: 8 }}>{formatDate(d.date)}</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'auto auto', gap: '4px 12px', marginBottom: 10 }}>
          <span style={{ color: '#94a3b8' }}>Time:</span>
          <span style={{ color: isTop3 ? highlightColor : chartColor, fontWeight: 700, fontFamily: 'Manrope' }}>{d.time_str}</span>
          <span style={{ color: '#94a3b8' }}>Pace:</span>
          <span style={{ color: '#38bdf8', fontWeight: 700, fontFamily: 'Manrope' }}>{d.pace_str}</span>
        </div>
        <div style={{ 
          textAlign: 'center', 
          padding: '4px', 
          background: 'rgba(255,255,255,0.05)', 
          borderRadius: 4, 
          fontSize: '0.65rem',
          color: '#38bdf8',
          cursor: 'pointer',
          fontWeight: 600
        }}>
          Click point or here to view activity →
        </div>
      </div>
    );
  };

  return (
    <div className="glass-card chart-container" style={{ minWidth: 0, minHeight: 450 }}>
      <div className="section-header chart-header-stack" style={{ marginBottom: 15 }}>
        <div>
          <span className="section-title">Best Benchmarks</span>
          <span className="section-subtitle">Fastest efforts for {selectedSegment.label}</span>
        </div>

        <div className="chart-header-controls" style={{ flexWrap: 'wrap' }}>
             {!typeProp && (
               <select 
                  value={selectedType}
                  onChange={(e) => setInternalSelectedType(e.target.value)}
                  style={{
                    background: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 6,
                    color: 'var(--text-main)',
                    fontSize: '0.75rem',
                    padding: '2px 8px',
                    outline: 'none'
                  }}
                >
                  <option value="Run">Run</option>
                  <option value="Ride">Ride</option>
                  <option value="Hike">Hike</option>
                </select>
             )}
          <div className="filter-bar" style={{ margin: 0 }}>
            {SEGMENTS.map(seg => (
              <button
                key={seg.label}
                className={`filter-chip ${selectedSegment.label === seg.label ? 'active' : ''}`}
                onClick={() => setSelectedSegment(seg)}
                style={{ fontSize: '0.65rem', padding: '2px 8px' }}
              >
                {seg.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {rawData.length > 0 ? (
        <div className="benchmarks-grid">
          {/* Main Scatter Chart */}
          <div style={{ position: 'relative', minWidth: 0, zIndex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8, marginBottom: 8, minHeight: 22 }}>
              {zoom.isZoomed ? (
                <button 
                  className="filter-chip"
                  onClick={zoom.reset}
                  style={{ fontSize: '0.6rem', padding: '2px 10px', background: 'rgba(56, 189, 248, 0.2)', color: '#38bdf8', borderColor: 'rgba(56, 189, 248, 0.4)' }}
                >
                  ↺ Reset Zoom
                </button>
              ) : (
                <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)', opacity: 0.5, fontStyle: 'italic' }}>drag to zoom</span>
              )}
            </div>

            <SafeResponsiveContainer height={280}>
              <ScatterChart
                margin={{ left: 10, right: 10, top: 10, bottom: 0 }}
                style={{ cursor: zoom.isDragging ? 'col-resize' : 'crosshair' }}
                onMouseDown={zoom.onMouseDown}
                onMouseMove={zoom.onMouseMove}
                onMouseUp={zoom.onMouseUp}
                onMouseLeave={zoom.onMouseLeave}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis
                  dataKey="timestamp"
                  type="number"
                  scale="time"
                  ticks={xAxisTicks}
                  tick={{ fontSize: 10, fill: '#64748b' }}
                  tickFormatter={v => formatShortDate(new Date(v).toISOString().split('T')[0])}
                  domain={zoom.xDomain || ['auto', 'auto']}
                  allowDataOverflow={zoom.isZoomed}
                />
                <YAxis 
                  dataKey="time_seconds"
                  tick={{ fontSize: 10, fill: '#64748b' }}
                  tickFormatter={v => formatTime(v)}
                  domain={zoom.yDomain || ['auto', 'auto']}
                  allowDataOverflow={zoom.isZoomed}
                  reversed
                />
                <Tooltip 
                  content={<TooltipContent />} 
                  wrapperStyle={{ pointerEvents: 'none', zIndex: 1000 }} 
                />
                <Scatter 
                  data={rawData} 
                  fill={chartColor}
                  onClick={(d) => navigate(`/activity/${d.activity_id}`)}
                >
                  {rawData.map((d, i) => (
                    <Cell 
                      key={i} 
                      fill={top3Ids.has(d.activity_id) ? highlightColor : chartColor}
                      fillOpacity={top3Ids.has(d.activity_id) ? 1 : 0.6}
                      stroke={top3Ids.has(d.activity_id) ? '#fff' : 'none'}
                      strokeWidth={1}
                      r={top3Ids.has(d.activity_id) ? 6 : 4}
                      style={{ cursor: 'pointer' }}
                    />
                  ))}
                </Scatter>
                {zoom.referenceAreaProps && (
                  <ReferenceArea {...zoom.referenceAreaProps} fill="rgba(56, 189, 248, 0.1)" />
                )}
              </ScatterChart>
            </SafeResponsiveContainer>
          </div>

          {/* Top 10 Bar Chart */}
          <div style={{ paddingLeft: 10, borderLeft: '1px solid rgba(255,255,255,0.05)', position: 'relative', minWidth: 0, zIndex: 1 }}>
            <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginBottom: 25, textTransform: 'uppercase', fontWeight: 600, letterSpacing: '0.05em', textAlign: 'center' }}>
              All-Time Top 10
            </div>
            <SafeResponsiveContainer height={280}>
              <BarChart data={top10} layout="vertical" margin={{ left: 0, right: 10 }}>
                <XAxis type="number" hide domain={[0, 'dataMax']} />
                <YAxis 
                  dataKey="label" 
                  type="category" 
                  tick={{ fontSize: 9, fill: '#64748b' }} 
                  width={45}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip 
                  cursor={{ fill: 'rgba(255,255,255,0.05)' }}
                  content={<TooltipContent />}
                  wrapperStyle={{ pointerEvents: 'none', zIndex: 1000 }}
                />
                <Bar 
                  dataKey="time_seconds" 
                  radius={[0, 4, 4, 0]}
                  onClick={(d) => navigate(`/activity/${d.activity_id}`)}
                  barSize={18}
                >
                  {top10.map((d, i) => (
                    <Cell 
                      key={i} 
                      fill={d.rank <= 3 ? highlightColor : chartColor} 
                      fillOpacity={0.9 - (i * 0.06)}
                      style={{ cursor: 'pointer' }}
                    />
                  ))}
                </Bar>
              </BarChart>
            </SafeResponsiveContainer>
          </div>
        </div>
      ) : (
        <div style={{ height: 300, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', opacity: 0.5 }}>
          {isLoading ? (
            <div className="loading-spinner" />
          ) : (
            <>
              <div style={{ fontSize: '0.8rem' }}>No benchmark data for this distance yet.</div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

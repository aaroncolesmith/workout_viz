import React, { useMemo } from 'react';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis,
  PolarRadiusAxis, Tooltip
} from 'recharts';
import { formatPace, formatDistance, formatDuration, formatHR, formatElevation, formatActivityName } from '../utils/format';
import SafeResponsiveContainer from './SafeResponsiveContainer';

/**
 * Radar chart for comparing workout profiles.
 */
export default function WorkoutRadar({ 
  activities = [], 
  width = '100%', 
  height = 350, 
  showLabels = true, 
  showGrid = true 
}) {
  if (!activities || activities.length === 0) return null;

  const AXES = [
    { key: 'pace', label: 'Pace', invert: true, format: formatPace, unit: '/mi' },
    { key: 'distance_miles', label: 'Distance', format: formatDistance, unit: 'mi' },
    { key: 'average_heartrate', label: 'Heart Rate', format: formatHR, unit: 'bpm' },
    { key: 'total_elevation_gain', label: 'Elevation', format: formatElevation, unit: 'ft' },
    { key: 'average_cadence', label: 'Cadence', format: (v) => Math.round(v), unit: 'spm' },
    { key: 'moving_time_min', label: 'Duration', format: formatDuration, unit: 'min' },
  ];

  const data = useMemo(() => {
    const bounds = {};
    AXES.forEach(axis => {
      const vals = activities.map(a => a[axis.key] || 0).filter(v => v > 0);
      let max = Math.max(...vals, 1);
      if (axis.key === 'distance_miles') max = Math.max(max, 10);
      if (axis.key === 'average_heartrate') max = Math.max(max, 180);
      if (axis.key === 'total_elevation_gain') max = Math.max(max, 500);
      if (axis.key === 'average_cadence') max = Math.max(max, 180);
      if (axis.key === 'moving_time_min') max = Math.max(max, 60);
      if (axis.key === 'pace') max = Math.max(max, 12);
      bounds[axis.key] = max;
    });

    return AXES.map(axis => {
      const row = { subject: axis.label, fullMark: 100 };
      activities.forEach((act, i) => {
        let val = act[axis.key] || 0;
        let score = 0;
        if (val > 0) {
          if (axis.invert) {
            const slowLimit = bounds[axis.key] * 1.2;
            const fastLimit = 4;
            score = Math.max(5, 100 - ((val - fastLimit) / (slowLimit - fastLimit) * 100));
          } else {
            score = Math.min(100, (val / bounds[axis.key]) * 100);
          }
        }
        row[`act_${i}`] = score;
        row[`raw_${i}`] = val;
      });
      return row;
    });
  }, [activities]);

  const colors = ['#38bdf8', '#fb7185', '#34d399', '#facc15', '#a78bfa'];

  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      return (
        <div className="glass-card" style={{ padding: '10px', fontSize: '0.8rem', border: '1px solid var(--border-subtle)', background: 'rgba(19,19,19,0.95)' }}>
          <div style={{ fontWeight: 600, marginBottom: 5, color: 'var(--text-muted)' }}>{payload[0].payload.subject}</div>
          {activities.map((act, i) => {
            const axis = AXES.find(a => a.label === payload[0].payload.subject);
            const raw = payload[0].payload[`raw_${i}`];
            return (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 20, color: colors[i] }}>
                <span style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {formatActivityName(act)}
                </span>
                <span style={{ fontWeight: 600 }}>
                  {raw !== null && raw !== undefined ? `${axis.format(raw)}${axis.unit}` : '--'}
                </span>
              </div>
            );
          })}
        </div>
      );
    }
    return null;
  };

  const chart = (
    <RadarChart 
      cx="50%" 
      cy="50%" 
      outerRadius="70%" 
      data={data}
      width={typeof width === 'number' ? width : undefined}
      height={typeof height === 'number' ? height : undefined}
    >
      {showGrid && <PolarGrid stroke="var(--border-subtle)" />}
      {showLabels && (
        <PolarAngleAxis 
          dataKey="subject" 
          tick={{ fill: 'var(--text-muted)', fontSize: 11, fontWeight: 500 }}
        />
      )}
      <PolarRadiusAxis 
        angle={30} 
        domain={[0, 100]} 
        tick={false} 
        axisLine={false} 
      />
      
      {activities.map((act, i) => (
        <Radar
          key={act.id}
          name={act.name}
          dataKey={`act_${i}`}
          stroke={colors[i]}
          fill={colors[i]}
          fillOpacity={0.3}
          strokeWidth={2}
        />
      ))}
      <Tooltip content={<CustomTooltip />} />
    </RadarChart>
  );

  return (
    <div style={{ width, height, position: 'relative', minWidth: 0 }}>
      {typeof width === 'number' && typeof height === 'number' ? (
        chart
      ) : (
        <SafeResponsiveContainer height={height}>
          {chart}
        </SafeResponsiveContainer>
      )}
    </div>
  );
}

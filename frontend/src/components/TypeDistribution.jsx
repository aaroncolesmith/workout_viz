import React from 'react';
import { PieChart, Pie, Cell, Tooltip } from 'recharts';
import { activityColor } from '../utils/format';
import SafeResponsiveContainer from './SafeResponsiveContainer';

const COLORS = {
  Run: '#38bdf8',
  Ride: '#818cf8',
  Hike: '#34d399',
  Walk: '#fbbf24',
  Workout: '#f472b6',
  WeightTraining: '#a78bfa',
  Soccer: '#fb923c',
  AlpineSki: '#67e8f9',
  Swim: '#2dd4bf',
};

function getColor(type) {
  return COLORS[type] || activityColor(type) || '#64748b';
}

export default function TypeDistribution({ typeCounts = {} }) {
  const data = Object.entries(typeCounts)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);

  const total = data.reduce((sum, d) => sum + d.value, 0);

  if (!data.length) return null;

  const topType = data[0];
  const topPct = total > 0 ? Math.round((topType.value / total) * 100) : 0;

  return (
    <div className="glass-card chart-container">
      <div className="section-header">
        <span className="section-title">Activity Breakdown</span>
        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontFamily: "'Inter', sans-serif" }}>
          {total.toLocaleString()} total
        </span>
      </div>

      {/* Donut with center label */}
      <div style={{ position: 'relative', width: '100%', height: 200 }}>
        <SafeResponsiveContainer height={200}>
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={62}
              outerRadius={88}
              paddingAngle={2}
              dataKey="value"
              stroke="none"
              animationDuration={800}
              animationEasing="ease-out"
            >
              {data.map((entry, i) => (
                <Cell key={i} fill={getColor(entry.name)} />
              ))}
            </Pie>
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const d = payload[0];
                const pct = ((d.value / total) * 100).toFixed(1);
                return (
                  <div style={{
                    background: 'rgba(19,19,19,0.95)',
                    border: '1px solid rgba(255,255,255,0.15)',
                    borderRadius: 8, padding: '8px 12px', fontSize: 12,
                  }}>
                    <div style={{ fontWeight: 700, color: getColor(d.name), marginBottom: 2 }}>{d.name}</div>
                    <div style={{ color: 'var(--text-secondary)', fontFamily: 'Manrope' }}>
                      {d.value.toLocaleString()} &nbsp;
                      <span style={{ color: getColor(d.name) }}>{pct}%</span>
                    </div>
                  </div>
                );
              }}
            />
          </PieChart>
        </SafeResponsiveContainer>

        {/* Center label — primary type % */}
        <div style={{
          position: 'absolute',
          top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)',
          textAlign: 'center',
          pointerEvents: 'none',
        }}>
          <div style={{
            fontFamily: 'Manrope, sans-serif',
            fontSize: '1.5rem',
            fontWeight: 700,
            letterSpacing: '-0.03em',
            color: getColor(topType.name),
            lineHeight: 1,
          }}>
            {topPct}%
          </div>
          <div style={{
            fontSize: '0.55rem',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
            color: 'var(--text-muted)',
            marginTop: 3,
          }}>
            {topType.name}
          </div>
        </div>
      </div>

      {/* Legend — compact dot rows */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 'var(--space-sm)' }}>
        {data.map((d) => {
          const pct = ((d.value / total) * 100).toFixed(1);
          return (
            <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                background: getColor(d.name),
              }} />
              <span style={{
                flex: 1, fontSize: '0.75rem', color: 'var(--text-secondary)',
                fontFamily: "'Inter', sans-serif", fontWeight: 500,
              }}>
                {d.name}
              </span>
              <span style={{
                fontSize: '0.72rem', color: 'var(--text-muted)',
                fontFamily: 'Manrope, sans-serif', marginRight: 8,
              }}>
                {d.value.toLocaleString()}
              </span>
              <span style={{
                fontSize: '0.72rem', fontWeight: 700,
                color: getColor(d.name),
                fontFamily: 'Manrope, sans-serif',
                minWidth: 38, textAlign: 'right',
              }}>
                {pct}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

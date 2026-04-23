import React from 'react';
import { formatActivityName } from '../utils/format';

export default function PerformanceDelta({ comparisonActivities, deltas }) {
  if (comparisonActivities.length === 0 || !deltas) return null;

  return (
    <div style={{ marginBottom: 'var(--space-xl)' }}>
      <div className="section-header">
        <span className="section-title">Performance Delta</span>
        <span className="section-subtitle">Comparing to {formatActivityName(comparisonActivities[0])}</span>
      </div>
      <div className="glass-card" style={{ padding: '24px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 'var(--space-lg)' }}>
          {[
            { label: 'Pace', val: deltas.pace, unit: 's/mi', format: (d) => `${d > 0 ? '+' : ''}${Math.round(d)}s` },
            { label: 'Avg HR', val: deltas.hr, unit: 'bpm', format: (d) => `${d > 0 ? '+' : ''}${Math.round(d)}` },
            { label: 'Cadence', val: deltas.cadence, unit: 'spm', format: (d) => `${d > 0 ? '+' : ''}${Math.round(d * 2)}` },
            { label: 'Distance', val: deltas.distance, unit: 'mi', format: (d) => `${d > 0 ? '+' : ''}${d.toFixed(2)}` },
            { label: 'Elevation', val: deltas.elevation, unit: 'ft', format: (d) => `${d > 0 ? '+' : ''}${Math.round(d)}` },
          ].map((item, i) => (
            <div key={i} style={{ textAlign: 'center' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>{item.label}</div>
              {item.val ? (
                <>
                  <div style={{ 
                    fontSize: '1.2rem', 
                    fontWeight: 700, 
                    color: item.val.improved ? '#34d399' : '#fb7185',
                    fontFamily: 'Manrope'
                  }}>
                    {item.format(item.val.diff)}
                  </div>
                  <div style={{ fontSize: '0.7rem', opacity: 0.6, marginTop: 4 }}>
                    {item.val.pct > 0 ? '+' : ''}{item.val.pct.toFixed(1)}%
                  </div>
                </>
              ) : (
                <div style={{ fontSize: '1.2rem', opacity: 0.2 }}>—</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

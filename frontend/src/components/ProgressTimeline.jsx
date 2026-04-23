import React, { useMemo, useState } from 'react';
import WorkoutRadar from './WorkoutRadar';
import { formatDate, formatRelativeTo, formatPace } from '../utils/format';

/**
 * ProgressTimeline — Displays a chronological sequence of radar charts for similar activities.
 * Useful for seeing evolution on a specific route.
 */
export default function ProgressTimeline({ currentActivity, similarActivities = [], onSelect, selectedIds = [] }) {
  // Combine and sort by date
  const cluster = useMemo(() => {
    const list = [
      { activity: currentActivity, similarity_score: 1.0, is_current: true },
      ...similarActivities
    ];
    // Filter for high quality matches (likely same route or very similar)
    // and sort by date ascending
    return list
      .filter(s => s.similarity_score > 0.7)
      .sort((a, b) => new Date(a.activity.date) - new Date(b.activity.date));
  }, [currentActivity, similarActivities]);

  // Calculate Progress Score: Current vs Oldest
  const progressScore = useMemo(() => {
    if (cluster.length < 2) return null;
    
    // Find oldest and newest (current might not be the literal newest in time if user is viewing history)
    const oldest = cluster[0].activity;
    const current = currentActivity;
    
    if (oldest.id === current.id) return null; // Can't compare to itself as "progress"

    // Factor 1: Pace (Lower is better)
    const paceDiff = oldest.pace - current.pace;
    const paceImprovement = (paceDiff / oldest.pace) * 100;
    
    // Factor 2: Efficiency (Pace/HR Ratio) - How fast can I go for how much effort?
    // Using simple Pace * HR as a "strain" metric (Lower is better)
    const getStrain = (a) => (a.pace || 10) * (a.average_heartrate || 140);
    const oldestStrain = getStrain(oldest);
    const currentStrain = getStrain(current);
    const efficiencyImprovement = ((oldestStrain - currentStrain) / oldestStrain) * 100;

    // Weighted Score (0-10 scale)
    const rawScore = (paceImprovement * 0.5) + (efficiencyImprovement * 0.5);
    const scaledScore = Math.min(10, Math.max(-10, rawScore / 2));
    
    return {
      value: scaledScore.toFixed(1),
      pace: paceImprovement.toFixed(1),
      efficiency: efficiencyImprovement.toFixed(1),
      isImprovement: scaledScore > 0
    };
  }, [cluster, currentActivity]);

  if (cluster.length < 2) return null;

  return (
    <div className="progress-timeline-container" style={{ marginTop: 'var(--space-xl)' }}>
      <div className="section-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-md)' }}>
          <span className="section-title">Route History & Progress</span>
          {progressScore && (
            <div 
              style={{ 
                background: progressScore.isImprovement ? 'rgba(52, 211, 153, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                color: progressScore.isImprovement ? '#34d399' : '#ef4444',
                padding: '4px 12px',
                borderRadius: 'full',
                fontSize: '0.75rem',
                fontWeight: 700,
                border: `1px solid ${progressScore.isImprovement ? 'rgba(52, 211, 153, 0.2)' : 'rgba(239, 68, 68, 0.2)'}`,
                display: 'flex',
                alignItems: 'center',
                gap: 6
              }}
            >
              <span>{progressScore.isImprovement ? '+' : '−'} Performance Score: {progressScore.value > 0 ? '+' : ''}{progressScore.value}</span>
              <span style={{ opacity: 0.6, fontWeight: 400 }}>vs baseline</span>
            </div>
          )}
        </div>
        <span className="section-subtitle">Chronological evolution on this route</span>
      </div>
      
      <div className="glass-card" style={{ padding: '24px', overflowX: 'auto' }}>
        <div style={{ display: 'flex', gap: 'var(--space-lg)', minWidth: 'min-content', paddingBottom: 10 }}>
          {cluster.map((item, i) => (
            <div 
              key={item.activity.id}
              onClick={() => onSelect(item.activity.id)}
              className={`timeline-item ${item.is_current ? 'active' : ''} ${selectedIds.includes(item.activity.id) ? 'selected' : ''}`}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                width: 140,
                flexShrink: 0,
                cursor: 'pointer',
                padding: '12px',
                borderRadius: '12px',
                background: item.is_current ? 'rgba(56, 189, 248, 0.1)' : selectedIds.includes(item.activity.id) ? 'rgba(251, 113, 133, 0.1)' : 'transparent',
                border: item.is_current ? '1px solid rgba(56, 189, 248, 0.3)' : selectedIds.includes(item.activity.id) ? '1px solid rgba(251, 113, 133, 0.3)' : '1px solid transparent',
                transition: 'all 0.2s ease'
              }}
            >
              <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginBottom: 2, fontWeight: 600, textAlign: 'center' }}>
                {item.is_current ? 'This run' : formatRelativeTo(item.activity.date, currentActivity.date)}
              </div>
              <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginBottom: 6, opacity: 0.6, textAlign: 'center' }}>
                {formatDate(item.activity.date)}
              </div>

              <div style={{ width: 100, height: 100, position: 'relative', minWidth: 0 }}>
                <WorkoutRadar
                  activities={[item.activity]}
                  height={100}
                  width={100}
                  showLabels={false}
                  showGrid={false}
                />
              </div>

              <div style={{ marginTop: 8, textAlign: 'center' }}>
                <div style={{ fontSize: '0.65rem', color: item.is_current ? '#38bdf8' : 'var(--text-muted)' }}>
                  {item.activity.distance_miles.toFixed(2)} mi
                </div>
                <div style={{ fontSize: '0.65rem', color: item.is_current ? '#38bdf8' : '#94a3b8', opacity: 0.85 }}>
                  {formatPace(item.activity.pace)} /mi
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

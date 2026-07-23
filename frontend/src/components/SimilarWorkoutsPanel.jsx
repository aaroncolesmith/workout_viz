import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import SportBadge from './SportBadge';
import {
  formatActivityName, formatDate, formatRelativeTo, formatDistance, formatPace, formatHR
} from '../utils/format';

const DATE_PRESETS = [
  { label: 'All Time', months: null },
  { label: '2 Years',  months: 24 },
  { label: '1 Year',   months: 12 },
  { label: '6 Months', months: 6 },
  { label: '3 Months', months: 3 },
];

export default function SimilarWorkoutsPanel({ activity, similar, comparisonIds, setComparisonIds, toggleComparisonId }) {
  const navigate = useNavigate();
  const [dateFilter, setDateFilter] = useState(null); // null = all time

  const filteredSimilar = useMemo(() => {
    if (!dateFilter) return similar;
    const cutoff = new Date();
    cutoff.setMonth(cutoff.getMonth() - dateFilter);
    const cutoffStr = cutoff.toISOString().slice(0, 10);
    return similar.filter(s => (s.activity.date || '') >= cutoffStr);
  }, [similar, dateFilter]);

  if (similar.length === 0) return null;

  return (
    <div className="similar-panel">
      <div className="section-header">
        <span className="section-title">Similar Workouts</span>
        <span className="section-subtitle">based on cluster profile and feature similarity</span>
      </div>

      {/* Date Filter */}
      <div className="filter-bar" style={{ marginBottom: 'var(--space-md)' }}>
        {DATE_PRESETS.map(p => (
          <button
            key={p.label}
            className={`filter-chip ${dateFilter === p.months ? 'active' : ''}`}
            onClick={() => setDateFilter(p.months)}
            style={{ fontSize: '0.72rem' }}
          >
            {p.label}
          </button>
        ))}
        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: 6 }}>
          {filteredSimilar.length} of {similar.length} runs
        </span>
      </div>

      <div className="similar-list">
        {filteredSimilar.length === 0 ? (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            No similar workouts found in this date range.
          </div>
        ) : filteredSimilar.map(s => {
          const score = s.similarity_score;
          const tier = score >= 0.9 ? 'high' : score >= 0.7 ? 'medium' : score >= 0.5 ? 'low' : 'none';
          
          const isComparing = comparisonIds.includes(s.activity.id);
          const diffBadge = (() => {
            if (s.similarity_score > 0.96) return null;
            const comps = [
              { name: 'Pace', score: s.components.pace },
              { name: 'Dist', score: s.components.distance },
              { name: 'HR', score: s.components.heartrate },
              { name: 'Time', score: s.components.duration }
            ].filter(c => c.score > 0).sort((a, b) => a.score - b.score);
            if (comps.length === 0) return null;
            return comps[0];
          })();

          return (
            <div
              key={s.activity.id}
              className={`similar-item ${isComparing ? 'active' : ''}`}
              onClick={() => navigate(`/activity/${s.activity.id}`)}
            >
              <div className="similar-item-top">
                <SportBadge type={s.activity.type} size={36} />
                <div className="similar-item-info">
                  <div className="similar-item-name-row">
                    <span className="similar-item-name">{formatActivityName(s.activity)}</span>
                    {diffBadge && (
                      <span style={{ fontSize: '9px', background: 'rgba(255,255,255,0.05)', color: 'var(--text-muted)', padding: '2px 6px', borderRadius: '4px', border: '1px solid var(--border-subtle)', flexShrink: 0 }}>
                        {diffBadge.name} Diff
                      </span>
                    )}
                  </div>
                  <div className="similar-item-meta">
                    <span title={formatDate(s.activity.date)}>{formatRelativeTo(s.activity.date, activity.date)}</span>
                    {' · '}{formatDistance(s.activity.distance_miles)} mi · {formatPace(s.activity.pace)} /mi
                  </div>

                  {/* Match Breakdown */}
                  <div className="match-breakdown">
                    <div className="breakdown-pill">
                      <span className="breakdown-label">Pace</span>
                      <span className="breakdown-val">{Math.round(s.components.pace * 100)}%</span>
                    </div>
                    <div className="breakdown-pill">
                      <span className="breakdown-label">Dist</span>
                      <span className="breakdown-val">{Math.round(s.components.distance * 100)}%</span>
                    </div>
                    {s.components.heartrate > 0 && (
                      <div className="breakdown-pill">
                        <span className="breakdown-label">HR</span>
                        <span className="breakdown-val">{Math.round(s.components.heartrate * 100)}%</span>
                      </div>
                    )}
                    {!activity.trainer && s.components.route > 0 && (
                      <div className="breakdown-pill">
                        <span className="breakdown-label">Route</span>
                        <span className="breakdown-val">{Math.round(s.components.route * 100)}%</span>
                      </div>
                    )}
                  </div>
                </div>
                <span className={`similarity-badge ${tier}`}>
                  {Math.round(s.similarity_score * 100)}%
                </span>
              </div>

              <div className="similar-item-actions">
                {s.activity.average_heartrate ? (
                  <span style={{ fontFamily: 'Manrope', fontSize: '0.8rem', color: '#f472b6', opacity: 0.7 }}>
                    {formatHR(s.activity.average_heartrate)} bpm
                  </span>
                ) : <span />}
                <button
                  className={`filter-chip ${isComparing ? 'active' : ''}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (toggleComparisonId) {
                      toggleComparisonId(s.activity.id);
                      return;
                    }
                    setComparisonIds(prev =>
                      prev.includes(s.activity.id)
                        ? prev.filter(id => id !== s.activity.id)
                        : [...prev, s.activity.id].slice(-5)
                    );
                  }}
                  style={{ fontSize: '0.72rem', padding: '5px 14px' }}
                >
                  {isComparing ? '✓ Comparing' : '+ Compare'}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

import React from 'react';
import { formatRelativeTo, formatDate } from '../utils/format';

const CHART_COLORS = ['#fb7185', '#fb923c', '#facc15', '#4ade80', '#2dd4bf'];

function formatPaceDiff(primarySec, compSec, distMiles) {
  if (!primarySec || !compSec || !distMiles) return null;
  const primaryPace = primarySec / distMiles;
  const compPace = compSec / distMiles;
  const diffSec = compPace - primaryPace;
  const abs = Math.abs(diffSec);
  const sign = diffSec < 0 ? '-' : '+';
  const m = Math.floor(abs / 60);
  const s = Math.round(abs % 60);
  return { sign, str: `${sign}${m}:${s.toString().padStart(2, '0')}/mi`, faster: diffSec < 0 };
}

export default function FastestSegments({ activity, segments, comparisonActivities, comparisonFastestMap, handleFetchDetails, syncingDetails }) {
  if (!segments || segments.length === 0) return null;

  const hasComparisons = comparisonActivities && comparisonActivities.length > 0;

  // Build a lookup: compId -> { label -> segment }
  const compMaps = {};
  (comparisonActivities || []).forEach(ca => {
    const segs = comparisonFastestMap?.[ca.id] || [];
    const byLabel = {};
    segs.forEach(s => { byLabel[s.label] = s; });
    compMaps[ca.id] = byLabel;
  });

  return (
    <div style={{ marginBottom: 'var(--space-xl)' }}>
      <div className="section-header">
        <span className="section-title">Fastest Segments</span>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          Best rolling window from 0.1mi splits
        </span>
      </div>

      {/* Alert for comparison activities with no segments */}
      {hasComparisons && comparisonActivities.map((ca, ci) => {
        const segs = comparisonFastestMap?.[ca.id];
        if (!segs || segs.length > 0) return null;
        return (
          <div key={ca.id} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            background: `${CHART_COLORS[ci]}10`, border: `1px solid ${CHART_COLORS[ci]}30`,
            borderRadius: 8, padding: '10px 16px', marginBottom: 10, fontSize: '0.8rem',
          }}>
            <span style={{ color: 'var(--text-muted)' }}>
              <span style={{ color: CHART_COLORS[ci], fontWeight: 600 }}>{ca.name}</span>
              {' '}has no splits synced — no segment comparison available.
            </span>
            {handleFetchDetails && (
              <button
                onClick={() => handleFetchDetails(ca.id)}
                disabled={syncingDetails}
                style={{ background: 'none', border: 'none', color: CHART_COLORS[ci], cursor: 'pointer', textDecoration: 'underline', fontSize: '0.78rem', whiteSpace: 'nowrap', marginLeft: 12 }}
              >
                {syncingDetails ? 'Fetching…' : 'Fetch splits'}
              </button>
            )}
          </div>
        );
      })}

      <div className="glass-card" style={{ overflow: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', minWidth: 480 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
              <th style={thStyle('left')}>Distance</th>
              <th style={thStyle('right')}>Time</th>
              <th style={thStyle('right')}>Pace</th>
              <th style={thStyle('right')}>Avg HR</th>
              <th style={thStyle('right')}>Segment</th>
              {hasComparisons && comparisonActivities.map((ca, ci) => (
                <th key={ca.id} style={thStyle('right', CHART_COLORS[ci])}>
                  <div>{ca.name || ca.date}</div>
                  <div style={{ fontSize: '0.65rem', fontWeight: 400, color: 'var(--text-muted)', marginTop: 2 }}>
                    {formatRelativeTo(ca.date, activity.date)}
                    {' · '}{formatDate(ca.date)}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {segments.map((seg, i) => (
              <tr key={seg.label} style={{
                borderBottom: i < segments.length - 1 ? '1px solid var(--border-subtle)' : 'none',
              }}>
                {/* Distance label */}
                <td style={{ padding: '10px 16px', fontWeight: 700, color: 'var(--text-primary)' }}>
                  {seg.label}
                </td>

                {/* Primary time */}
                <td style={{ padding: '10px 16px', textAlign: 'right', fontFamily: 'Manrope, sans-serif', color: '#38bdf8', fontWeight: 600 }}>
                  {seg.time_str}
                </td>

                {/* Pace */}
                <td style={{ padding: '10px 16px', textAlign: 'right', fontFamily: 'Manrope, sans-serif', color: 'var(--text-secondary)' }}>
                  {seg.pace_str}
                </td>

                {/* Heart rate */}
                <td style={{ padding: '10px 16px', textAlign: 'right', fontFamily: 'Manrope, sans-serif', color: '#f472b6' }}>
                  {seg.avg_hr ? `${Math.round(seg.avg_hr)} bpm` : '—'}
                </td>

                {/* Segment range */}
                <td style={{ padding: '10px 16px', textAlign: 'right', color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                  mi {seg.start_mile}–{seg.end_mile}
                </td>

                {/* Comparison columns */}
                {hasComparisons && comparisonActivities.map((ca, ci) => {
                  const compSeg = compMaps[ca.id]?.[seg.label];
                  if (!compSeg) return (
                    <td key={ca.id} style={{ padding: '10px 16px', textAlign: 'right', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                      —
                    </td>
                  );
                  const diff = formatPaceDiff(seg.time_seconds, compSeg.time_seconds, seg.distance_miles);
                  return (
                    <td key={ca.id} style={{ padding: '10px 16px', textAlign: 'right' }}>
                      <div style={{ fontFamily: 'Manrope, sans-serif', color: CHART_COLORS[ci], fontWeight: 600, fontSize: '0.85rem' }}>
                        {compSeg.time_str}
                      </div>
                      {diff && (
                        <div style={{
                          fontSize: '0.72rem',
                          color: diff.faster ? '#4ade80' : '#fb7185',
                          marginTop: 2,
                          fontFamily: 'Manrope, sans-serif',
                        }}>
                          {diff.str}
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function thStyle(align = 'left', color = null) {
  return {
    padding: '10px 16px',
    textAlign: align,
    color: color || 'var(--text-muted)',
    fontWeight: 600,
    fontSize: '0.72rem',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    whiteSpace: 'nowrap',
  };
}

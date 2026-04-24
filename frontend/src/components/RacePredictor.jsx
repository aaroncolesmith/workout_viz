/**
 * RacePredictor — Riegel-formula race time predictions.
 *
 * Shows 5K / 10K / Half / Full cards with predicted time, pace, confidence
 * band, and attribution ("based on your 10K on Mar 26").
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getRacePredictions } from '../utils/api';
import { formatDate } from '../utils/format';

const WINDOW_OPTIONS = [
  { label: '30 days', days: 30 },
  { label: '60 days', days: 60 },
  { label: '90 days', days: 90 },
  { label: '6 months', days: 180 },
];

const DISTANCE_META = {
  '5K':             { color: '#38bdf8' },
  '10K':            { color: '#818cf8' },
  'Half Marathon':  { color: '#fb923c' },
  'Marathon':       { color: '#a78bfa' },
};

const CONFIDENCE_META = {
  high:   { label: 'High confidence',   color: '#34d399' },
  medium: { label: 'Medium confidence', color: '#fbbf24' },
  low:    { label: 'Low confidence',    color: '#94a3b8' },
};

export default function RacePredictor() {
  const navigate = useNavigate();
  const [days, setDays] = useState(90);

  const { data, isLoading } = useQuery({
    queryKey: ['race-predictions', days],
    queryFn: () => getRacePredictions({ type: 'Run', days }),
    staleTime: 5 * 60_000,
  });

  const predictions = data?.predictions || [];

  return (
    <div style={{ marginBottom: 'var(--space-xl)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-md)' }}>
        <div className="section-title" style={{ fontSize: '0.72rem' }}>Race Predictor</div>
        <div style={{ display: 'flex', gap: 4 }}>
          {WINDOW_OPTIONS.map(opt => (
            <button
              key={opt.days}
              onClick={() => setDays(opt.days)}
              className={`filter-chip ${days === opt.days ? 'active' : ''}`}
              style={{ fontSize: '0.65rem', padding: '3px 8px' }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading && (
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
          <div className="loading-spinner" style={{ width: 14, height: 14 }} />
          Computing predictions…
        </div>
      )}

      {!isLoading && predictions.length === 0 && (
        <div className="glass-card" style={{ padding: 'var(--space-xl)', textAlign: 'center' }}>
          <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>No data in this window</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Sync splits for recent runs to unlock predictions.
          </div>
        </div>
      )}

      {predictions.length > 0 && (
        <div className="race-predictor-grid">
          {predictions.map(p => <PredictionCard key={p.target_label} pred={p} navigate={navigate} />)}
        </div>
      )}

      {predictions.length > 0 && (
        <div style={{ marginTop: 8, fontSize: '0.6rem', color: 'var(--text-muted)', opacity: 0.5 }}>
          Riegel formula T₂ = T₁ × (D₂/D₁)^1.06
        </div>
      )}
    </div>
  );
}

function PredictionCard({ pred, navigate }) {
  const meta = DISTANCE_META[pred.target_label] || { color: '#38bdf8' };

  return (
    <div
      className="kinetica-stat-card"
      style={{ cursor: 'pointer' }}
      onClick={() => navigate(`/activity/${pred.source.activity_id}`)}
    >
      <div style={{
        fontSize: '0.58rem', fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.16em', color: 'var(--text-muted)', marginBottom: 10,
      }}>
        {pred.target_label}
      </div>
      <div className="race-predictor-time">
        {pred.predicted_time_str}
      </div>
      <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 6, fontFamily: "'Inter', sans-serif" }}>
        {pred.predicted_pace_str}
      </div>
      <div className="kinetica-stat-bar" style={{ '--bar-color': meta.color, '--bar-width': '50%' }} />
    </div>
  );
}

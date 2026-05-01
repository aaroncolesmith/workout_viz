import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getActivities, getOverview } from '../utils/api';
import {
  formatPace, formatDistance, formatDuration, formatHR,
  activityClass, formatDate, formatRelativeDate, formatActivityName,
} from '../utils/format';
import SportBadge from '../components/SportBadge';

const TYPE_ALL = 'All';
const PAGE_SIZE = 100;

export default function Activities() {
  const navigate = useNavigate();
  const [selectedType, setSelectedType] = useState(TYPE_ALL);
  const [page, setPage] = useState(0);

  const overviewQuery = useQuery({
    queryKey: ['overview'],
    queryFn: getOverview,
  });
  const overview = overviewQuery.data;

  const types = useMemo(() => {
    if (!overview?.activity_types) return [TYPE_ALL];
    return [TYPE_ALL, ...Object.keys(overview.activity_types)];
  }, [overview]);

  const params = useMemo(() => {
    const p = { limit: PAGE_SIZE, offset: page * PAGE_SIZE };
    if (selectedType !== TYPE_ALL) p.type = selectedType;
    return p;
  }, [page, selectedType]);

  const activitiesQuery = useQuery({
    queryKey: ['activities', params],
    queryFn: () => getActivities(params),
  });
  const activities = activitiesQuery.data?.activities || [];
  const total = activitiesQuery.data?.total || 0;
  const loading = activitiesQuery.isLoading;

  return (
    <div>
      <div style={{ marginBottom: 'var(--space-lg)' }}>
        <div style={{
          fontSize: '11px', fontWeight: 700, letterSpacing: '0.1em',
          textTransform: 'uppercase', color: 'var(--text-muted)',
          marginBottom: 4,
        }}>
          Activities
        </div>
        <div style={{
          fontSize: '2rem', fontWeight: 800, letterSpacing: '-0.03em',
          color: 'var(--text-primary)', lineHeight: 1.1,
        }}>
          {total.toLocaleString()}
          <span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-secondary)', marginLeft: 8 }}>
            total
          </span>
        </div>
      </div>

      {/* Type filter chips */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-xs)', marginBottom: 'var(--space-lg)' }}>
        {types.map(t => (
          <button
            key={t}
            className={`filter-chip ${selectedType === t ? 'active' : ''}`}
            onClick={() => { setSelectedType(t); setPage(0); }}
          >
            {t}
            {t !== TYPE_ALL && overview?.activity_types?.[t] != null && (
              <span style={{ opacity: 0.6, marginLeft: 4 }}>{overview.activity_types[t]}</span>
            )}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading-state"><div className="loading-spinner" /></div>
      ) : (
        <>
          <div className="activity-list">
            {activities.map(a => (
              <div
                key={a.id}
                className={`activity-row ${activityClass(a.type)}`}
                onClick={() => navigate(`/activity/${a.id}`)}
              >
                <SportBadge type={a.type} size={36} />
                <div className="activity-info">
                  <div className="activity-name">{formatActivityName(a)}</div>
                  <div className="activity-date">{formatRelativeDate(a.date)} · {formatDate(a.date)}</div>
                </div>
                <div className="activity-metric">
                  <div className="metric-value">{formatDistance(a.distance_miles)}</div>
                  <div className="metric-label">miles</div>
                </div>
                <div className="activity-metric">
                  <div className="metric-value">{formatDuration(a.moving_time_min)}</div>
                  <div className="metric-label">time</div>
                </div>
                <div className="activity-metric">
                  <div className="metric-value">{formatPace(a.pace)}</div>
                  <div className="metric-label">pace</div>
                </div>
                <div className="activity-metric">
                  <div className="metric-value" style={{ color: a.average_heartrate ? '#f472b6' : 'inherit' }}>
                    {formatHR(a.average_heartrate)}
                  </div>
                  <div className="metric-label">avg hr</div>
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', justifyContent: 'center', gap: 'var(--space-md)', marginTop: 'var(--space-lg)' }}>
            <button
              className="filter-chip"
              disabled={page === 0}
              onClick={() => setPage(p => p - 1)}
              style={{ opacity: page === 0 ? 0.3 : 1 }}
            >
              ← Previous
            </button>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', padding: '6px 0' }}>
              {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total}
            </span>
            <button
              className="filter-chip"
              disabled={(page + 1) * PAGE_SIZE >= total}
              onClick={() => setPage(p => p + 1)}
              style={{ opacity: (page + 1) * PAGE_SIZE >= total ? 0.3 : 1 }}
            >
              Next →
            </button>
          </div>
        </>
      )}
    </div>
  );
}

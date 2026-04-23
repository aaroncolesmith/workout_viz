import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getActivity, getActivitySplits, getActivitySummary, getActivityFastestSegments, getSimilarActivities, getPcaData } from '../utils/api';

import { formatTime, isStrengthType } from '../utils/format';
import StrengthOverview from '../components/StrengthOverview';
import RouteMap from '../components/RouteMap';
import WorkoutRadar from '../components/WorkoutRadar';
import ProgressTimeline from '../components/ProgressTimeline';
import ActivityHeader from '../components/ActivityHeader';
import PerformanceDelta from '../components/PerformanceDelta';
import SplitPaceChart from '../components/SplitPaceChart';
import SplitHRChart from '../components/SplitHRChart';
import FastestSegments from '../components/FastestSegments';
import SimilarWorkoutsPanel from '../components/SimilarWorkoutsPanel';
import InsightCard from '../components/InsightCard';
import { useComparisonState } from '../hooks/useComparisonState';
import { useZoomState } from '../hooks/useZoomState';

const TABS = [
  { key: 'overview',  label: 'Overview'  },
  { key: 'splits',    label: 'Splits'    },
  { key: 'compare',   label: 'Compare'   },
  { key: 'segments',  label: 'Segments'  },
];

function TabBar({ activeTab, onSelect, visibleTabs }) {
  return (
    <div style={{
      display: 'flex',
      gap: 2,
      borderBottom: '1px solid rgba(255,255,255,0.15)',
      marginBottom: 'var(--space-xl)',
    }}>
      {TABS.filter(t => visibleTabs.has(t.key)).map(tab => {
        const active = activeTab === tab.key;
        return (
          <button
            key={tab.key}
            onClick={() => onSelect(tab.key)}
            style={{
              background: 'none',
              border: 'none',
              borderBottom: active ? '2px solid #38bdf8' : '2px solid transparent',
              color: active ? '#ffffff' : 'var(--text-muted)',
              fontFamily: "'Inter', sans-serif",
              fontWeight: active ? 600 : 400,
              fontSize: '0.85rem',
              padding: '10px 20px',
              cursor: 'pointer',
              transition: 'color 0.15s, border-color 0.15s',
              marginBottom: -1,
              letterSpacing: active ? '0.01em' : '0',
            }}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

export default function ActivityDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'overview';
  const setTab = (key) => {
    // Preserve all existing params (especially `compare`) — only update `tab`
    const next = new URLSearchParams(searchParams);
    next.set('tab', key);
    setSearchParams(next, { replace: true });
  };
  const queryClient = useQueryClient();
  const [comparisonSplitsMap, setComparisonSplitsMap] = useState({});
  const [xAxisType, setXAxisType] = useState('distance'); // 'distance' or 'time'
  const [syncingDetails, setSyncingDetails] = useState(false);
  const [missingDataIds, setMissingDataIds] = useState([]);
  const [comparisonFastestMap, setComparisonFastestMap] = useState({});
  const {
    comparisonIds,
    setComparisonIds,
    clearComparisonIds,
    toggleComparisonId,
  } = useComparisonState(id);
  const detailQuery = useQuery({
    queryKey: ['activity-detail', id],
    enabled: Boolean(id),
    queryFn: async () => {
      const [activity, splitsResponse, summaryResponse, similarResponse, fastestResponse] = await Promise.all([
        getActivity(id),
        getActivitySplits(id),
        getActivitySummary(id),
        getSimilarActivities(id, 20),
        getActivityFastestSegments(id),
      ]);
      // Skip PCA for strength/non-standard types — not enough data points
      const PCA_TYPES = new Set(['Run', 'Ride', 'Hike', 'Walk', 'VirtualRun', 'TrailRun', 'VirtualRide']);
      const pcaData = PCA_TYPES.has(activity.type) ? await getPcaData(activity.type) : null;
      return {
        activity,
        splits: splitsResponse.splits || [],
        summary: summaryResponse.segments || [],
        similar: similarResponse.similar || [],
        fastestSegments: fastestResponse.segments || [],
        pcaData,
      };
    },
  });
  const activity = detailQuery.data?.activity || null;
  const splits = detailQuery.data?.splits || [];
  const similar = detailQuery.data?.similar || [];
  const fastestSegments = detailQuery.data?.fastestSegments || [];
  const pcaData = detailQuery.data?.pcaData || null;

  // Reset zoom when axis type changes — stale zoom bounds don't apply across axes
  const handleSetXAxisType = (type) => {
    setXAxisType(type);
  };

  useEffect(() => {
    setComparisonSplitsMap({});
    setComparisonFastestMap({});

  }, [id]);

  // Load comparison splits when comparisonIds changes
  useEffect(() => {
    comparisonIds.forEach(cid => {
      if (!comparisonSplitsMap[cid]) {
        getActivitySplits(cid)
          .then(data => {
            setComparisonSplitsMap(prev => ({
              ...prev,
              [cid]: data.splits || []
            }));
            if (!data.splits || data.splits.length === 0) {
              setMissingDataIds(prev => Array.from(new Set([...prev, cid])));
            } else {
              setMissingDataIds(prev => prev.filter(id => id !== cid));
            }
          })
          .catch(console.error);
      }
      // Fetch fastest segments for comparison
      if (!comparisonFastestMap[cid]) {
        getActivityFastestSegments(cid)
          .then(data => {
            setComparisonFastestMap(prev => ({ ...prev, [cid]: data.segments || [] }));
          })
          .catch(console.error);
      }

    });
    // Remove old splits that are no longer selected
    setComparisonSplitsMap(prev => {
      const keysToRemove = Object.keys(prev).filter(key => !comparisonIds.includes(Number(key)));
      if (keysToRemove.length === 0) return prev;
      const next = { ...prev };
      keysToRemove.forEach(key => delete next[key]);
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [comparisonIds]);

  const comparisonActivities = useMemo(() => {
    return similar
      .filter(s => comparisonIds.includes(s.activity.id))
      .map(s => s.activity);
  }, [comparisonIds, similar]);

  const radarActivities = useMemo(() => {
    return [activity, ...comparisonActivities];
  }, [activity, comparisonActivities]);

  const deltas = useMemo(() => {
    if (!activity || comparisonActivities.length === 0) return null;
    const comp = comparisonActivities[0]; // Compare against the first selected

    const computeDelta = (curr, comp, invert = false) => {
      if (curr === null || comp === null || curr === undefined || comp === undefined) return null;
      const diff = curr - comp;
      const pct = (diff / comp) * 100;
      // Invert logic: for Pace, lower is better. 
      // If curr is 8:00 (480s) and comp is 8:10 (490s), diff is -10 (improvement).
      const improved = invert ? diff < 0 : diff > 0;
      return { diff, pct, improved };
    };

    return {
      pace: computeDelta(activity.pace * 60, comp.pace * 60, true),
      hr: computeDelta(activity.average_heartrate, comp.average_heartrate, true),
      cadence: computeDelta(activity.average_cadence, comp.average_cadence, false),
      distance: computeDelta(activity.distance_miles, comp.distance_miles, false),
      elevation: computeDelta(activity.total_elevation_gain, comp.total_elevation_gain, false),
    };
  }, [activity, comparisonActivities]);

  const splitChartData = useMemo(() => {
    const allSplits = [splits, ...Object.values(comparisonSplitsMap)];
    const maxLen = Math.max(0, ...allSplits.map(s => s.length));
    if (maxLen === 0) return [];
    
    const data = [];
    
    // Track cumulative time for each activity series
    const cumTimes = {
      primary: 0,
      ...Object.fromEntries(comparisonActivities.map(ca => [ca.id, 0]))
    };
    
    for (let i = 0; i < maxLen; i++) {
      const s = splits[i];
      if (s) cumTimes.primary += (s.time_seconds || 0);
      
      const row = {
        index: i,
        mile: ((i + 1) * 0.1).toFixed(1),
        time: cumTimes.primary,
        time_formatted: formatTime(cumTimes.primary),
        pace_seconds: s?.time_seconds,
        pace_per_mile: s?.time_seconds > 0 ? (s.time_seconds / 60) * 10 : null,
        avg_hr: s?.avg_heartrate,
        max_hr: s?.max_heartrate,
      };
      
      comparisonActivities.forEach(ca => {
        const cs = comparisonSplitsMap[ca.id]?.[i];
        if (cs) cumTimes[ca.id] = (cumTimes[ca.id] || 0) + (cs.time_seconds || 0);
        
        row[`comp_${ca.id}_pace`] = cs?.time_seconds > 0 ? (cs.time_seconds / 60) * 10 : null;
        row[`comp_${ca.id}_hr`] = cs?.avg_heartrate;
        row[`comp_${ca.id}_time`] = cumTimes[ca.id];
      });
      
      data.push(row);
    }
    return data;
  }, [splits, comparisonSplitsMap, comparisonActivities]);
  const paceZoom = useZoomState({ data: splitChartData, xAxisType });
  const hrZoom = useZoomState({ data: splitChartData, xAxisType });

  const handleFetchDetails = async (targetId) => {
    // If targetId is an event (e.g. from onClick), use the current activity id
    const idToSync = (targetId && typeof targetId === 'number') ? targetId : Number(id);
    try {
      setSyncingDetails(true);
      const res = await fetch(`/api/activities/${idToSync}/sync_details`, { method: 'POST' });
      const data = await res.json();
      if (data.status === 'success') {
        // Reload splits for this specific activity
        const spl = await getActivitySplits(idToSync);
        if (idToSync === Number(id)) {
          await queryClient.invalidateQueries({ queryKey: ['activity-detail', id] });
        } else {
          setComparisonSplitsMap(prev => ({ ...prev, [idToSync]: spl.splits || [] }));
          if (spl.splits?.length > 0) {
            setMissingDataIds(prev => prev.filter(mid => mid !== idToSync));
          }
        }
      }
    } catch (err) {
      console.error('Failed to sync details:', err);
    } finally {
      setSyncingDetails(false);
    }
  };

  const handleFetchAllMissing = async () => {
    const idsToSync = [...(splits.length === 0 ? [id] : []), ...missingDataIds];
    for (const sid of idsToSync) {
      await handleFetchDetails(Number(sid));
    }
  };

  const chartColors = ['#fb7185', '#fb923c', '#facc15', '#4ade80', '#2dd4bf'];

  if (detailQuery.isLoading) {
    return (
      <div className="loading-state">
        <div className="loading-spinner" />
        <span>Loading activity...</span>
      </div>
    );
  }

  if (!activity) {
    return (
      <div className="empty-state">
        <span>Activity not found</span>
        <button className="filter-chip" onClick={() => navigate('/')}>← Back to Dashboard</button>
      </div>
    );
  }

  const isStrength = isStrengthType(activity.type);
  const RUN_TYPES = new Set(['Run', 'VirtualRun', 'TrailRun']);
  const hasSegments = RUN_TYPES.has(activity.type) || fastestSegments.length > 0;
  const hasComparisons = comparisonActivities.length > 0;

  // Determine which tabs are relevant for this activity type
  const visibleTabs = new Set(['overview', 'compare']);
  if (!isStrength) visibleTabs.add('splits');
  if (!isStrength && hasSegments) visibleTabs.add('segments');

  return (
    <div>
      <button className="back-btn" onClick={() => navigate('/')}>
        ← Back to Dashboard
      </button>

      {/* ── Header (always visible) ── */}
      <ActivityHeader activity={activity} />

      {/* ── Tab bar ── */}
      <TabBar activeTab={activeTab} onSelect={setTab} visibleTabs={visibleTabs} />

      {/* ══════════════════════════════════════════════════════
          TAB: Overview — map + profile + progress timeline
          ══════════════════════════════════════════════════════ */}
      {activeTab === 'overview' && (
        <div>
          {isStrength ? (
            /* ── Strength / indoor workout overview ── */
            <div style={{ marginBottom: 'var(--space-xl)' }}>
              <StrengthOverview activity={activity} />
            </div>
          ) : (
            /* ── GPS activity overview: map + radar ── */
            <div style={{
              display: 'grid',
              gridTemplateColumns: activity.map_polyline ? 'minmax(0, 1fr) 350px' : '1fr',
              gap: 'var(--space-xl)',
              marginBottom: 'var(--space-xl)',
              minWidth: 0,
            }}>
              {activity.map_polyline && (
                <div className="glass-card" style={{ height: 400, padding: 0, overflow: 'hidden', minWidth: 0 }}>
                  <RouteMap
                    encodedPolyline={activity.map_polyline}
                    activityType={activity.type}
                    height={400}
                    comparisonActivities={[]}
                  />
                </div>
              )}
              <div className="glass-card" style={{ height: 400, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                <div style={{ padding: '20px 20px 0 20px', fontWeight: 600, fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Activity Profile
                </div>
                <WorkoutRadar activities={[activity]} height={350} />
              </div>
            </div>
          )}

          {/* Workout Analysis (all types) */}
          <InsightCard activityId={Number(id)} />

          {/* Progress Timeline (all types) */}
          <ProgressTimeline
            currentActivity={activity}
            similarActivities={similar}
            onSelect={(cid) => { toggleComparisonId(cid); setTab('compare'); }}
            selectedIds={comparisonIds}
          />
        </div>
      )}

      {/* ══════════════════════════════════════════════════════
          TAB: Splits — pace + HR split charts
          ══════════════════════════════════════════════════════ */}
      {activeTab === 'splits' && (
        <div className="detail-charts-grid" style={{ minWidth: 0 }}>
          <SplitPaceChart
            activity={activity}
            comparisonActivities={comparisonActivities}
            splitChartData={splitChartData}
            chartColors={chartColors}
            xAxisType={xAxisType}
            handleSetXAxisType={handleSetXAxisType}
            splits={splits}
            missingDataIds={missingDataIds}
            handleFetchAllMissing={handleFetchAllMissing}
            handleFetchDetails={handleFetchDetails}
            syncingDetails={syncingDetails}
            paceZoom={paceZoom}
          />
          <SplitHRChart
            activity={activity}
            comparisonActivities={comparisonActivities}
            splitChartData={splitChartData}
            chartColors={chartColors}
            xAxisType={xAxisType}
            handleSetXAxisType={handleSetXAxisType}
            splits={splits}
            missingDataIds={missingDataIds}
            handleFetchAllMissing={handleFetchAllMissing}
            handleFetchDetails={handleFetchDetails}
            syncingDetails={syncingDetails}
            hrZoom={hrZoom}
          />
          {splits.length === 0 && (
            <div style={{ gridColumn: '1 / -1', padding: 'var(--space-xl)', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              No split data yet.{' '}
              <button
                onClick={() => handleFetchDetails(Number(id))}
                disabled={syncingDetails}
                style={{ background: 'none', border: 'none', color: '#38bdf8', cursor: 'pointer', textDecoration: 'underline' }}
              >
                {syncingDetails ? 'Fetching…' : 'Fetch splits from Strava'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════
          TAB: Compare — radar with overlays + delta + similar
          ══════════════════════════════════════════════════════ */}
      {activeTab === 'compare' && (
        <div>
          {/* Radar with comparison overlays */}
          <div style={{ display: 'grid', gridTemplateColumns: '350px 1fr', gap: 'var(--space-xl)', marginBottom: 'var(--space-xl)', minWidth: 0 }}>
            <div className="glass-card" style={{ height: 400, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
              <div style={{ padding: '20px 20px 0 20px', fontWeight: 600, fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Activity Profile
              </div>
              <WorkoutRadar activities={radarActivities} height={330} />
              {hasComparisons && (
                <div style={{ padding: '0 20px 16px 20px', fontSize: '0.75rem', textAlign: 'center', marginTop: 'auto' }}>
                  Comparing{' '}
                  <span style={{ color: '#fb7185', fontWeight: 600 }}>
                    {comparisonActivities.length} session{comparisonActivities.length > 1 ? 's' : ''}
                  </span>
                  <button
                    onClick={() => { clearComparisonIds(); setComparisonSplitsMap({}); }}
                    style={{ marginLeft: 10, background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', textDecoration: 'underline' }}
                  >
                    Clear All
                  </button>
                </div>
              )}
              {!hasComparisons && (
                <div style={{ padding: '0 20px 16px 20px', fontSize: '0.72rem', color: 'var(--text-muted)', textAlign: 'center', marginTop: 'auto' }}>
                  Select workouts below to compare
                </div>
              )}
            </div>

            {/* Delta table fills right column when comparisons are active */}
            <div style={{ minWidth: 0 }}>
              <PerformanceDelta comparisonActivities={comparisonActivities} deltas={deltas} />
              {!hasComparisons && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                  Performance delta will appear here once you select a comparison workout.
                </div>
              )}
            </div>
          </div>

          {/* Map with comparison routes (only when comparisons active) */}
          {(activity.map_polyline || comparisonActivities.some(ca => ca.map_polyline)) && hasComparisons && (
            <div className="glass-card" style={{ height: 360, padding: 0, overflow: 'hidden', minWidth: 0, marginBottom: 'var(--space-xl)' }}>
              <RouteMap
                encodedPolyline={activity.map_polyline}
                activityType={activity.type}
                height={360}
                comparisonActivities={comparisonActivities}
              />
            </div>
          )}

          {/* Similar Workouts Panel */}
          <SimilarWorkoutsPanel
            activity={activity}
            similar={similar}
            pcaData={pcaData}
            comparisonIds={comparisonIds}
            setComparisonIds={setComparisonIds}
            toggleComparisonId={toggleComparisonId}
          />
        </div>
      )}

      {/* ══════════════════════════════════════════════════════
          TAB: Segments — fastest efforts table (runs only)
          ══════════════════════════════════════════════════════ */}
      {activeTab === 'segments' && hasSegments && (
        fastestSegments.length > 0 ? (
          <FastestSegments
            activity={activity}
            segments={fastestSegments}
            comparisonActivities={comparisonActivities}
            comparisonFastestMap={comparisonFastestMap}
            handleFetchDetails={handleFetchDetails}
            syncingDetails={syncingDetails}
          />
        ) : (
          <div className="glass-card" style={{ padding: 'var(--space-xl)', textAlign: 'center' }}>
            <div style={{ fontSize: '1rem', marginBottom: 'var(--space-md)', color: 'var(--text-muted)' }}>—</div>
            <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>No segment data yet</div>
            <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: 'var(--space-lg)' }}>
              Fetch splits from Strava to unlock fastest efforts for 1K, 1 mi, 5K, 10K, and more.
            </div>
            <button
              onClick={() => handleFetchDetails(Number(id))}
              disabled={syncingDetails}
              className="filter-chip active"
              style={{ fontSize: '0.82rem', padding: '8px 20px' }}
            >
              {syncingDetails ? 'Fetching splits…' : 'Fetch splits from Strava'}
            </button>
          </div>
        )
      )}
    </div>
  );
}

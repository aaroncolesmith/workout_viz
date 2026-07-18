import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getActivity, getActivitySplits, getActivitySummary, getActivityFastestSegments, getSimilarActivities, getPcaData, getSwimLaps, getActivities } from '../utils/api';

import { formatTime, isStrengthType, activityColor } from '../utils/format';
import StrengthOverview from '../components/StrengthOverview';
import RouteMap from '../components/RouteMap';
import WorkoutRadar from '../components/WorkoutRadar';
import ProgressTimeline from '../components/ProgressTimeline';
import ActivityHeader from '../components/ActivityHeader';
import PerformanceDelta from '../components/PerformanceDelta';
import SplitPaceChart from '../components/SplitPaceChart';
import SplitHRChart from '../components/SplitHRChart';
import MileSplitsView from '../components/MileSplitsView';
import FastestSegments from '../components/FastestSegments';
import SimilarWorkoutsPanel from '../components/SimilarWorkoutsPanel';
import InsightCard from '../components/InsightCard';
import ComparisonCard from '../components/ComparisonCard';
import SwimLapChart from '../components/SwimLapChart';
import { useComparisonState } from '../hooks/useComparisonState';

const TABS = [
  { key: 'overview',  label: 'Overview'  },
  { key: 'pace',      label: 'Pace'      },
  { key: 'splits',    label: 'Splits'    },
  { key: 'compare',   label: 'Compare'   },
  { key: 'segments',  label: 'Segments'  },
];

function TabBar({ activeTab, onSelect, visibleTabs, accentColor = '#26c6f9' }) {
  return (
    <div
      className="scroll-tabs"
      style={{
        gap: 2,
        borderBottom: '1px solid #2a2a32',
        marginBottom: 'var(--space-xl)',
      }}
    >
      {TABS.filter(t => visibleTabs.has(t.key)).map(tab => {
        const active = activeTab === tab.key;
        return (
          <button
            key={tab.key}
            onClick={() => onSelect(tab.key)}
            style={{
              background: 'none',
              border: 'none',
              borderBottom: active ? `2px solid ${accentColor}` : '2px solid transparent',
              color: active ? 'var(--text-primary)' : 'var(--text-muted)',
              fontFamily: 'var(--font-body)',
              fontWeight: active ? 700 : 500,
              fontSize: '0.85rem',
              padding: '10px 16px',
              whiteSpace: 'nowrap',
              cursor: 'pointer',
              transition: 'color 0.15s, border-color 0.15s',
              marginBottom: -1,
              letterSpacing: '0.01em',
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
  const [xAxisType, setXAxisType] = useState('distance'); // 'distance' or 'time'
  const [syncingDetails, setSyncingDetails] = useState(false);
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

  const swimQuery = useQuery({
    queryKey: ['swim-laps', id],
    enabled: Boolean(id) && detailQuery.data?.activity?.type === 'Swim',
    queryFn: () => getSwimLaps(id),
  });

  const [compareSwimId, setCompareSwimId] = useState(null);
  const swimActivitiesQuery = useQuery({
    queryKey: ['swim-activities'],
    enabled: detailQuery.data?.activity?.type === 'Swim',
    queryFn: () => getActivities({ type: 'Swim', limit: 50 }),
    staleTime: 5 * 60 * 1000,
  });
  const compareSwimQuery = useQuery({
    queryKey: ['swim-laps', compareSwimId],
    enabled: Boolean(compareSwimId),
    queryFn: () => getSwimLaps(compareSwimId),
  });
  // Swim activities excluding the current one, sorted newest first
  const otherSwims = useMemo(() => {
    const acts = swimActivitiesQuery.data?.activities || [];
    return acts.filter(a => String(a.id) !== String(id));
  }, [swimActivitiesQuery.data, id]);

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
    setComparisonFastestMap({});
  }, [id]);

  // Load comparison fastest-segments when comparisonIds changes (used by the
  // Segments tab's comparison columns).
  useEffect(() => {
    comparisonIds.forEach(cid => {
      if (!comparisonFastestMap[cid]) {
        getActivityFastestSegments(cid)
          .then(data => {
            setComparisonFastestMap(prev => ({ ...prev, [cid]: data.segments || [] }));
          })
          .catch(console.error);
      }
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
    // `total_distance_miles` is the cumulative mark at each row; grain (the
    // width of that bucket) varies — legacy synced activities are 0.1 mi,
    // newer ones 0.05 mi — so it's derived per-row, never assumed.
    const splitMile = (s, fallback) => Number(s?.total_distance_miles) || fallback;

    const data = [];
    let cumPrimary = 0;
    let prevMile = 0;

    for (const s of splits) {
      const mile = splitMile(s, prevMile + 0.1);
      const grain = Math.max(mile - prevMile, 0.001);
      cumPrimary += (s.time_seconds || 0);
      data.push({
        index: data.length,
        mile: mile.toFixed(2),
        time: cumPrimary,
        time_formatted: formatTime(cumPrimary),
        pace_seconds: s.time_seconds,
        pace_per_mile: s.time_seconds > 0 ? (s.time_seconds / 60) / grain : null,
        avg_hr: s.avg_heartrate,
        max_hr: s.max_heartrate,
      });
      prevMile = mile;
    }

    // Centered rolling average (window of 5 buckets, ~0.25mi) — the raw
    // per-bucket pace/HR is sawtooth-noisy (GPS jitter, stride variation,
    // brief walk breaks); smoothing makes the actual trend legible without
    // a handful of spikes dominating the chart's visual range.
    const WINDOW = 5;
    const half = Math.floor(WINDOW / 2);
    const smoothed = (key) => (i) => {
      const lo = Math.max(0, i - half);
      const hi = Math.min(data.length - 1, i + half);
      let sum = 0, n = 0;
      for (let j = lo; j <= hi; j++) {
        const v = data[j][key];
        if (v != null) { sum += v; n++; }
      }
      return n ? sum / n : null;
    };
    data.forEach((row, i) => {
      row.pace_smooth = smoothed('pace_per_mile')(i);
      row.hr_smooth = smoothed('avg_hr')(i);
    });

    return data;
  }, [splits]);

  // Sequential whole-mile aggregation (mile 1, mile 2, …) for the Splits
  // tab — distinct from splitChartData's fine-grained bucket grain above.
  // No backend equivalent exists; built here from the same raw splits.
  const mileSplits = useMemo(() => {
    if (!splits.length) return [];
    const rows = [];
    let mileIdx = 1;
    let timeAcc = 0;
    let hrWeighted = 0;
    let hrTimeAcc = 0;
    let prevMile = 0;

    for (const s of splits) {
      const mile = Number(s.total_distance_miles) || (prevMile + 0.05);
      const dt = s.time_seconds || 0;
      timeAcc += dt;
      if (s.avg_heartrate) { hrWeighted += s.avg_heartrate * dt; hrTimeAcc += dt; }

      if (mile >= mileIdx) {
        rows.push({
          mile: mileIdx,
          time_seconds: timeAcc,
          avg_hr: hrTimeAcc > 0 ? hrWeighted / hrTimeAcc : null,
          partial: false,
        });
        mileIdx += 1;
        timeAcc = 0; hrWeighted = 0; hrTimeAcc = 0;
      }
      prevMile = mile;
    }
    if (timeAcc > 0) {
      rows.push({
        mile: Math.round(prevMile * 100) / 100,
        time_seconds: timeAcc,
        avg_hr: hrTimeAcc > 0 ? hrWeighted / hrTimeAcc : null,
        partial: true,
      });
    }
    return rows;
  }, [splits]);

  const handleFetchDetails = async (targetId) => {
    // If targetId is an event (e.g. from onClick), use the current activity id
    const idToSync = (targetId && typeof targetId === 'number') ? targetId : Number(id);
    try {
      setSyncingDetails(true);
      const res = await fetch(`/api/activities/${idToSync}/sync_details`, { method: 'POST' });
      const data = await res.json();
      if (data.status === 'success') {
        if (idToSync === Number(id)) {
          await queryClient.invalidateQueries({ queryKey: ['activity-detail', id] });
        } else {
          // Comparison activity — refresh its fastest-segments for the Segments tab.
          const fresh = await getActivityFastestSegments(idToSync);
          setComparisonFastestMap(prev => ({ ...prev, [idToSync]: fresh.segments || [] }));
        }
      }
    } catch (err) {
      console.error('Failed to sync details:', err);
    } finally {
      setSyncingDetails(false);
    }
  };


  if (detailQuery.isLoading) {
    return (
      <div className="loading-state">
        <div className="loading-spinner" />
        <span>Loading activity...</span>
      </div>
    );
  }

  if (!activity) {
    const errMsg = detailQuery.error?.message || 'Activity not found';
    return (
      <div className="empty-state">
        <span>{errMsg}</span>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 8, fontFamily: 'monospace' }}>
          id: {id}
        </div>
        <button className="filter-chip" onClick={() => navigate('/activities')} style={{ marginTop: 12 }}>← Back to Activities</button>
      </div>
    );
  }

  const isStrength = isStrengthType(activity.type);
  const RUN_TYPES = new Set(['Run', 'VirtualRun', 'TrailRun']);
  const hasSegments = RUN_TYPES.has(activity.type) || fastestSegments.length > 0;
  const hasComparisons = comparisonActivities.length > 0;

  // Determine which tabs are relevant for this activity type
  const visibleTabs = new Set(['overview', 'compare']);
  if (!isStrength) { visibleTabs.add('pace'); visibleTabs.add('splits'); }
  if (!isStrength && hasSegments) visibleTabs.add('segments');

  const accentColor = activity ? activityColor(activity.type) : '#26c6f9';

  return (
    <div>
      <button
        className="back-btn"
        onClick={() => navigate('/activities')}
        style={{ color: accentColor }}
      >
        ← Activities
      </button>

      {/* ── Header (always visible) ── */}
      <ActivityHeader activity={activity} />

      {/* ── Tab bar ── */}
      <TabBar activeTab={activeTab} onSelect={setTab} visibleTabs={visibleTabs} accentColor={accentColor} />

      {/* ══════════════════════════════════════════════════════
          TAB: Overview — map + profile + progress timeline
          ══════════════════════════════════════════════════════ */}
      {activeTab === 'overview' && (
        <div>
          {/* The post-workout verdict — auto-selected comparison (CMP-4) */}
          <ComparisonCard activityId={Number(id)} />

          {isStrength ? (
            /* ── Strength / indoor workout overview ── */
            <div style={{ marginBottom: 'var(--space-xl)' }}>
              <StrengthOverview activity={activity} />
            </div>
          ) : activity.type === 'Swim' ? (
            /* ── Swim overview: lap chart + radar ── */
            <div>
              <SwimLapChart
                swimData={swimQuery.data}
                compareSwimData={compareSwimQuery.data}
                swimActivities={otherSwims}
                compareId={compareSwimId}
                onSelectCompare={setCompareSwimId}
              />
              <div className="glass-card" style={{ height: 380, display: 'flex', flexDirection: 'column', minWidth: 0, marginTop: 'var(--space-xl)', overflow: 'hidden' }}>
                <div style={{ padding: '20px 20px 0 20px', fontWeight: 600, fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Activity Profile
                </div>
                <WorkoutRadar activities={[activity]} height={330} />
              </div>
            </div>
          ) : (
            /* ── GPS activity overview: map + radar ── */
            <div className={`activity-overview-grid ${activity.map_polyline ? 'activity-overview-grid--map' : 'activity-overview-grid--no-map'}`}>
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
              <div className="glass-card" style={{ height: 400, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
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
          TAB: Pace — pace + HR trend charts (fine-grained buckets)
          ══════════════════════════════════════════════════════ */}
      {activeTab === 'pace' && (
        <div className="detail-charts-grid" style={{ minWidth: 0 }}>
          <SplitPaceChart
            splitChartData={splitChartData}
            xAxisType={xAxisType}
            handleSetXAxisType={handleSetXAxisType}
            handleFetchDetails={handleFetchDetails}
            syncingDetails={syncingDetails}
          />
          <SplitHRChart
            splitChartData={splitChartData}
            xAxisType={xAxisType}
            handleSetXAxisType={handleSetXAxisType}
            handleFetchDetails={handleFetchDetails}
            syncingDetails={syncingDetails}
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
          TAB: Splits — time + heart rate per whole mile
          ══════════════════════════════════════════════════════ */}
      {activeTab === 'splits' && (
        <MileSplitsView
          mileSplits={mileSplits}
          handleFetchDetails={handleFetchDetails}
          syncingDetails={syncingDetails}
          activityId={Number(id)}
        />
      )}

      {/* ══════════════════════════════════════════════════════
          TAB: Compare — radar with overlays + delta + similar
          ══════════════════════════════════════════════════════ */}
      {activeTab === 'compare' && (
        <div>
          {/* Radar with comparison overlays */}
          <div className="activity-compare-grid">
            <div className="glass-card" style={{ height: 400, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
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
                    onClick={clearComparisonIds}
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

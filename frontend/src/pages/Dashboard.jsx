import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  BarChart, Bar, Cell, ReferenceArea,
} from 'recharts';
import { useQuery } from '@tanstack/react-query';
import { getOverview, getTrends, getBestPRs } from '../utils/api';
import {
  formatPace, formatDistance, formatHR, activityColor, formatShortDate, formatActivityName,
} from '../utils/format';
import ActivityCalendar from '../components/ActivityCalendar';
import TypeDistribution from '../components/TypeDistribution';
import BestSegmentsTrend from '../components/BestSegmentsTrend';
import FitnessChart from '../components/FitnessChart';
import ReadinessCard from '../components/ReadinessCard';
import RacePredictor from '../components/RacePredictor';
import SafeResponsiveContainer from '../components/SafeResponsiveContainer';
import { useChartZoom } from '../hooks/useChartZoom';

const TYPE_ALL = 'All';

const PR_SPORT_GROUPS = [
  {
    label: 'Run',
    accent: '#26c6f9',
    matchesType: (t) => ['Run', 'VirtualRun', 'TrailRun'].includes(t),
    distances: ['1 Mile', '2 Miles', '5K', 'Half Marathon', 'Marathon'],
  },
  {
    label: 'Bike',
    accent: '#a78bfa',
    matchesType: (t) => ['Ride', 'VirtualRide'].includes(t),
    distances: ['5 Miles', '10 Miles', '25 Miles', '50 Miles'],
  },
  {
    label: 'Swim',
    accent: '#22d3ee',
    matchesType: (t) => t === 'Swim',
    distances: ['1/4 Mile', '1/2 Mile', '1 Mile'],
  },
];

function PRSportGroup({ label, accent, distances, bestPRs, matchesType, onSelect }) {
  const lookup = {};
  for (const pr of bestPRs) {
    if (!matchesType(pr.activity_type)) continue;
    const existing = lookup[pr.distance_label];
    if (!existing || pr.time_seconds < existing.time_seconds) {
      lookup[pr.distance_label] = pr;
    }
  }
  const cards = distances.map(d => ({ distance: d, pr: lookup[d] || null }));
  const hasAny = cards.some(c => c.pr);
  if (!hasAny) return null;

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{
        fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.14em', color: accent, marginBottom: 8,
      }}>
        {label}
      </div>
      <div className="pr-card-grid">
        {cards.map(({ distance, pr }) => (
          <button
            key={distance}
            onClick={pr ? () => onSelect(pr.activity_id) : undefined}
            disabled={!pr}
            style={{
              background: pr ? `${accent}14` : 'rgba(255,255,255,0.02)',
              border: `1px solid ${pr ? `${accent}40` : 'rgba(255,255,255,0.06)'}`,
              borderRadius: 8,
              padding: '10px 12px',
              cursor: pr ? 'pointer' : 'default',
              textAlign: 'left',
              opacity: pr ? 1 : 0.35,
            }}
          >
            <div style={{ fontSize: '0.6rem', color: pr ? `${accent}cc` : 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.04em', marginBottom: 4 }}>
              {distance}
            </div>
            <div style={{ fontSize: '1.1rem', fontWeight: 700, color: pr ? accent : 'var(--text-muted)', fontFamily: 'var(--font-display)', letterSpacing: '-0.02em', lineHeight: 1 }}>
              {pr ? pr.time_str : '—'}
            </div>
            {pr && (
              <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginTop: 4 }}>
                {pr.pace_str} · {pr.date}
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

// Shared zoom badge component — keeps JSX DRY
function ZoomHint({ isZoomed, onReset, color = '#26c6f9' }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', minHeight: 20, marginBottom: 4 }}>
      {isZoomed ? (
        <button
          onClick={onReset}
          style={{
            fontSize: '0.6rem', padding: '2px 10px',
            borderRadius: 20, border: `1px solid ${color}55`,
            background: `${color}18`, color, cursor: 'pointer',
          }}
        >
          ↺ Reset Zoom <span style={{ opacity: 0.6 }}>(Esc)</span>
        </button>
      ) : (
        <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)', opacity: 0.45, fontStyle: 'italic' }}>drag to zoom</span>
      )}
    </div>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [selectedType, setSelectedType] = useState(TYPE_ALL);
  const [selectedMonths, setSelectedMonths] = useState(12);
  const dateCutoff = useMemo(() => {
    if (!selectedMonths) return null;
    const cutoff = new Date();
    cutoff.setMonth(cutoff.getMonth() - selectedMonths);
    return cutoff.toISOString().slice(0, 10);
  }, [selectedMonths]);

  const trendParams = useMemo(() => {
    const params = {};
    if (selectedType !== TYPE_ALL) params.type = selectedType;
    if (dateCutoff) params.date_from = dateCutoff;
    return params;
  }, [selectedType, dateCutoff]);
  const overviewQuery = useQuery({
    queryKey: ['overview'],
    queryFn: getOverview,
  });
  const prsQuery = useQuery({
    queryKey: ['best-prs'],
    queryFn: getBestPRs,
    staleTime: 5 * 60 * 1000,
  });
  const bestPRs = prsQuery.data?.prs || [];
  const trendsQuery = useQuery({
    queryKey: ['trends', trendParams],
    queryFn: () => getTrends(trendParams),
  });
  const overview = overviewQuery.data;
  const trends = trendsQuery.data?.data || [];

  const types = useMemo(() => {
    if (!overview?.activity_types) return [TYPE_ALL];
    return [TYPE_ALL, ...Object.keys(overview.activity_types)];
  }, [overview]);

  // Trends are already filtered server-side by type + dateCutoff above.
  const filteredTrends = trends;


  // Dynamic stats based on filtered trends (which include full filtered history, unlike activities)
  const dynamicStats = useMemo(() => {
    if (!filteredTrends.length) return null;
    let totalMiles = 0;
    let totalSecs = 0;
    let runPaceSum = 0;
    let runCount = 0;
    let hrSum = 0;
    let hrCount = 0;
    const typeCounts = {};
    
    filteredTrends.forEach(t => {
      totalMiles += (t.distance_miles || 0);
      totalSecs += (t.moving_time_min || 0) * 60;
      if (t.type === 'Run' && t.pace > 0) {
        runPaceSum += t.pace;
        runCount++;
      }
      if (t.average_heartrate > 0) {
        hrSum += t.average_heartrate;
        hrCount++;
      }
      typeCounts[t.type] = (typeCounts[t.type] || 0) + 1;
    });
    
    return {
      totalAct: filteredTrends.length,
      totalMiles: totalMiles,
      totalHours: totalSecs / 3600,
      avgPace: runCount > 0 ? formatPace(runPaceSum / runCount) : '—',
      avgHr: hrCount > 0 ? hrSum / hrCount : null,
      typeCounts
    };
  }, [filteredTrends]);



  // Weekly mileage aggregation
  const weeklyMiles = useMemo(() => {
    if (!filteredTrends.length) return [];
    const weeks = {};
    filteredTrends.forEach(t => {
      if (!t.date || t.date === 'NaT' || !t.distance_miles) return;
      const d = new Date(t.date);
      if (isNaN(d.getTime())) return;
      
      const weekStart = new Date(d);
      weekStart.setDate(d.getDate() - d.getDay());
      const key = weekStart.toISOString().slice(0, 10);
      if (!weeks[key]) weeks[key] = { week: key, miles: 0, count: 0 };
      weeks[key].miles += t.distance_miles;
      weeks[key].count += 1;
    });
    return Object.values(weeks).sort((a, b) => a.week.localeCompare(b.week)).slice(-26);
  }, [filteredTrends]);

  // ── per-chart zoom instances (after data is defined) ─────────────────────────
  // ScatterCharts use axis-domain clamping (not data filtering).
  // BarChart (weeklyMiles) uses data filtering via filteredData.
  const paceZoom = useChartZoom({ data: filteredTrends, xKey: 'date', yKey: 'pace',              mode: 'numeric' });
  const hrZoom   = useChartZoom({ data: filteredTrends, xKey: 'date', yKey: 'average_heartrate', mode: 'numeric' });
  const pvhrZoom = useChartZoom({ data: filteredTrends, xKey: 'pace', yKey: 'average_heartrate', mode: 'numeric' });
  const weekZoom = useChartZoom({ data: weeklyMiles, xKey: 'week',          mode: 'category' });


  if (overviewQuery.isLoading) {
    return (
      <div className="loading-state">
        <div className="loading-spinner" />
        <span>Loading your workout data...</span>
      </div>
    );
  }

  if (!overview) return null;

  return (
    <div>
      {/* ── Dashboard Hero Header ── */}
      <div style={{ marginBottom: 'var(--space-xl)' }}>
        <div style={{
          fontSize: '11px', fontWeight: 700, letterSpacing: '0.1em',
          textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 4,
        }}>
          Performance Overview
        </div>
        <div className="hero-title" style={{ marginBottom: 12 }}>
          {selectedMonths === null ? 'All Time' :
           selectedMonths === 24  ? 'Last Two Years' :
           selectedMonths === 12  ? 'Last Year' :
           selectedMonths === 6   ? 'Past Six Months' :
                                    'Current Cycle'}
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {[{ label: 'All', m: null }, { label: '2Y', m: 24 }, { label: '1Y', m: 12 }, { label: '6M', m: 6 }, { label: '90D', m: 3 }].map(f => {
            const active = selectedMonths === f.m;
            return (
              <button
                key={f.label}
                onClick={() => setSelectedMonths(f.m)}
                style={{
                  padding: '5px 13px', borderRadius: 20,
                  fontSize: '13px', fontWeight: active ? 700 : 500,
                  border: `1px solid ${active ? '#26c6f9' : '#2a2a32'}`,
                  background: active ? '#26c6f9' : 'transparent',
                  color: active ? '#000' : 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-body)',
                  transition: 'all 0.15s',
                }}
              >
                {f.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Stat Cards Row ── */}
      <div className="stat-cards-row">
        <div className="kinetica-stat-card">
          <div className="kinetica-stat-label">Activities</div>
          <div className="kinetica-stat-value">
            {dynamicStats ? dynamicStats.totalAct.toLocaleString() : '—'}
          </div>
          <div className="kinetica-stat-bar" style={{ '--bar-color': '#4a4a56', '--bar-width': '65%' }} />
        </div>
        <div className="kinetica-stat-card">
          <div className="kinetica-stat-label">Distance</div>
          <div className="kinetica-stat-value">
            {dynamicStats ? Math.round(dynamicStats.totalMiles).toLocaleString() : '—'}
            <span className="kinetica-stat-unit">mi</span>
          </div>
          <div className="kinetica-stat-bar" style={{ '--bar-color': '#a78bfa', '--bar-width': '55%' }} />
        </div>
        <div className="kinetica-stat-card">
          <div className="kinetica-stat-label">Time</div>
          <div className="kinetica-stat-value">
            {dynamicStats ? `${Math.round(dynamicStats.totalHours)}` : '—'}
            <span className="kinetica-stat-unit">hrs</span>
          </div>
          <div className="kinetica-stat-bar" style={{ '--bar-color': '#22c55e', '--bar-width': '70%' }} />
        </div>
        <div className="kinetica-stat-card">
          <div className="kinetica-stat-label">Avg Pace</div>
          <div className="kinetica-stat-value">
            {dynamicStats ? dynamicStats.avgPace : '—'}
            <span className="kinetica-stat-unit">/mi</span>
          </div>
          <div className="kinetica-stat-bar" style={{ '--bar-color': '#26c6f9', '--bar-width': '48%' }} />
        </div>
        <div className="kinetica-stat-card">
          <div className="kinetica-stat-label">Avg HR</div>
          <div className="kinetica-stat-value" style={{ color: dynamicStats?.avgHr ? '#f472b6' : 'inherit' }}>
            {dynamicStats?.avgHr ? Math.round(dynamicStats.avgHr) : '—'}
            <span className="kinetica-stat-unit" style={{ color: '#f472b6' }}>bpm</span>
          </div>
          <div className="kinetica-stat-bar" style={{ '--bar-color': '#f472b6', '--bar-width': '75%' }} />
        </div>
      </div>

      {/* ── Readiness Banner ── */}
      <ReadinessCard />

      {/* ── Calendar Heatmap + Type Breakdown ── */}

      <div className="dashboard-split-grid" style={{ marginBottom: 'var(--space-xl)' }}>
        <ActivityCalendar />
        <TypeDistribution typeCounts={dynamicStats?.typeCounts || overview.activity_types || {}} />
      </div>

      {/* ── Fitness & Fatigue Chart ── */}
      <div className="glass-card chart-container" style={{ marginBottom: 'var(--space-xl)' }}>
        <FitnessChart />
      </div>

      {/* ── Race Predictor ── */}
      <div style={{ marginBottom: 'var(--space-xl)' }}>
        <RacePredictor />
      </div>


      {/* ── Personal Records, grouped by sport ── */}
      {bestPRs.length > 0 && (
        <div className="glass-card" style={{ marginBottom: 'var(--space-xl)', padding: 'var(--space-lg)' }}>
          <div style={{ fontSize: '0.6rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.18em', color: 'var(--text-muted)', marginBottom: 14 }}>
            Personal Records
          </div>
          {PR_SPORT_GROUPS.map(group => (
            <PRSportGroup
              key={group.label}
              label={group.label}
              accent={group.accent}
              distances={group.distances}
              bestPRs={bestPRs}
              matchesType={group.matchesType}
              onSelect={(id) => navigate(`/activity/${id}`)}
            />
          ))}
        </div>
      )}

      {/* ── Filter Bar ── */}
      <div className="filter-bar">
        {types.map(t => (
          <button
            key={t}
            className={`filter-chip ${selectedType === t ? 'active' : ''}`}
            onClick={() => setSelectedType(t)}
          >
            {t}
            {t !== TYPE_ALL && (dynamicStats?.typeCounts?.[t] || overview.activity_types[t]) && (
              <span style={{ marginLeft: 5, opacity: 0.5, fontSize: '0.75em' }}>
                {dynamicStats?.typeCounts?.[t] || overview.activity_types[t]}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Performance Benchmarks ── */}
      <div style={{ marginBottom: 'var(--space-xl)' }}>
        <BestSegmentsTrend 
          type={selectedType === 'All' ? 'Run' : selectedType} 
          date_from={dateCutoff}
        />
      </div>

      {/* ── Charts Grid ── */}
      <div className="dashboard-charts-grid" style={{ marginBottom: 'var(--space-xl)', minWidth: 0 }}>

        {/* Pace over time */}
        <div className="glass-card chart-container" style={{ minWidth: 0, minHeight: 300 }}>
          <div className="section-header">
            <span className="section-title">Pace Over Time</span>
          </div>
          <ZoomHint isZoomed={paceZoom.isZoomed} onReset={paceZoom.reset} color="#26c6f9" />
          <SafeResponsiveContainer height={240}>
            <ScatterChart
              style={{ cursor: paceZoom.isDragging ? 'col-resize' : 'crosshair' }}
              onMouseDown={paceZoom.onMouseDown}
              onMouseMove={paceZoom.onMouseMove}
              onMouseUp={paceZoom.onMouseUp}
              onMouseLeave={paceZoom.onMouseLeave}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis
                dataKey="date"
                type="category"
                tick={{ fontSize: 10 }}
                tickFormatter={v => formatShortDate(v)}
                domain={paceZoom.xDomain}
                allowDataOverflow={paceZoom.isZoomed}
              />
              <YAxis
                dataKey="pace"
                type="number"
                domain={paceZoom.yDomain ?? [5, 15]}
                reversed
                tick={{ fontSize: 10 }}
                tickFormatter={v => formatPace(v)}
                allowDataOverflow={paceZoom.isZoomed}
                label={{ value: 'Pace (min/mi)', angle: -90, position: 'insideLeft', style: { fill: '#64748b', fontSize: 11 } }}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0]?.payload;
                  if (!d) return null;
                  return (
                    <div style={{ background: '#0d0d0f', border: '1px solid #2a2a32', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>{formatActivityName(d)}</div>
                      <div style={{ color: '#94a3b8' }}>{d.date}</div>
                      <div style={{ color: '#26c6f9', fontFamily: "var(--font-display)" }}>
                        {formatPace(d.pace)} /mi · {formatDistance(d.distance_miles)} mi
                      </div>
                    </div>
                  );
                }}
              />
              <Scatter data={filteredTrends.filter(t => t.pace && t.pace > 0 && t.pace < 20)} fill="#26c6f9" fillOpacity={0.5} r={3}>
                {filteredTrends.filter(t => t.pace && t.pace > 0 && t.pace < 20).map((t, i) => (
                  <Cell key={i} fill={activityColor(t.type)} fillOpacity={0.6} />
                ))}
              </Scatter>

              {paceZoom.referenceAreaProps && <ReferenceArea {...paceZoom.referenceAreaProps} />}
            </ScatterChart>
          </SafeResponsiveContainer>
        </div>

        {/* Weekly mileage */}
        <div className="glass-card chart-container" style={{ minWidth: 0, minHeight: 300 }}>
          <div className="section-header">
            <span className="section-title">Weekly Mileage</span>
            <span className="section-subtitle">Last 6 months</span>
          </div>
          <ZoomHint isZoomed={weekZoom.isZoomed} onReset={weekZoom.reset} color="#a78bfa" />
          <SafeResponsiveContainer height={240}>
            <BarChart
              data={weekZoom.isZoomed ? weekZoom.filteredData : weeklyMiles}
              style={{ cursor: weekZoom.isDragging ? 'col-resize' : 'crosshair' }}
              onMouseDown={weekZoom.onMouseDown}
              onMouseMove={weekZoom.onMouseMove}
              onMouseUp={weekZoom.onMouseUp}
              onMouseLeave={weekZoom.onMouseLeave}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis
                dataKey="week"
                tick={{ fontSize: 10 }}
                tickFormatter={v => v ? v.slice(5) : ''}
              />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0]?.payload;
                  return (
                    <div style={{ background: '#0d0d0f', border: '1px solid #2a2a32', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
                      <div style={{ fontWeight: 600 }}>Week of {d.week}</div>
                      <div style={{ color: '#a78bfa', fontFamily: "var(--font-display)" }}>
                        {d.miles.toFixed(1)} mi · {d.count} activities
                      </div>
                    </div>
                  );
                }}
              />
              <Bar dataKey="miles" fill="#a78bfa" radius={[4, 4, 0, 0]} fillOpacity={0.7} />
              {weekZoom.referenceAreaProps && <ReferenceArea {...weekZoom.referenceAreaProps} />}
            </BarChart>
          </SafeResponsiveContainer>
        </div>

        {/* Heart rate trend */}
        <div className="glass-card chart-container" style={{ minWidth: 0, minHeight: 300 }}>
          <div className="section-header">
            <span className="section-title">Heart Rate Trend</span>
          </div>
          <ZoomHint isZoomed={hrZoom.isZoomed} onReset={hrZoom.reset} color="#f472b6" />
          <SafeResponsiveContainer height={240}>
            <ScatterChart
              style={{ cursor: hrZoom.isDragging ? 'col-resize' : 'crosshair' }}
              onMouseDown={hrZoom.onMouseDown}
              onMouseMove={hrZoom.onMouseMove}
              onMouseUp={hrZoom.onMouseUp}
              onMouseLeave={hrZoom.onMouseLeave}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis
                dataKey="date"
                type="category"
                tick={{ fontSize: 10 }}
                tickFormatter={v => formatShortDate(v)}
                domain={hrZoom.xDomain}
                allowDataOverflow={hrZoom.isZoomed}
              />
              <YAxis
                dataKey="average_heartrate"
                type="number"
                domain={hrZoom.yDomain ?? [80, 200]}
                tick={{ fontSize: 10 }}
                allowDataOverflow={hrZoom.isZoomed}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0]?.payload;
                  return (
                    <div style={{ background: '#0d0d0f', border: '1px solid #2a2a32', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
                      <div style={{ fontWeight: 600 }}>{formatActivityName(d)}</div>
                      <div style={{ color: '#94a3b8' }}>{d.date}</div>
                      <div style={{ color: '#f472b6', fontFamily: "var(--font-display)" }}>
                        Avg {formatHR(d.average_heartrate)} bpm · Max {formatHR(d.max_heartrate)} bpm
                      </div>
                    </div>
                  );
                }}
              />
              <Scatter data={filteredTrends.filter(t => t.average_heartrate)} fillOpacity={0.5} r={3}>
                {filteredTrends.filter(t => t.average_heartrate).map((t, i) => (
                  <Cell key={i} fill={activityColor(t.type)} fillOpacity={0.5} />
                ))}
              </Scatter>

              {hrZoom.referenceAreaProps && <ReferenceArea {...hrZoom.referenceAreaProps} />}
            </ScatterChart>
          </SafeResponsiveContainer>
        </div>

        {/* Pace vs HR scatter */}
        <div className="glass-card chart-container" style={{ minWidth: 0, minHeight: 300 }}>
          <div className="section-header">
            <span className="section-title">Pace vs Heart Rate</span>
            <span className="section-subtitle">Efficiency</span>
          </div>
          <ZoomHint isZoomed={pvhrZoom.isZoomed} onReset={pvhrZoom.reset} color="#a78bfa" />
          <SafeResponsiveContainer height={240}>
            <ScatterChart
              style={{ cursor: pvhrZoom.isDragging ? 'col-resize' : 'crosshair' }}
              onMouseDown={pvhrZoom.onMouseDown}
              onMouseMove={pvhrZoom.onMouseMove}
              onMouseUp={pvhrZoom.onMouseUp}
              onMouseLeave={pvhrZoom.onMouseLeave}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis
                dataKey="pace"
                type="number"
                domain={pvhrZoom.xDomain ?? [5, 15]}
                tick={{ fontSize: 10 }}
                tickFormatter={v => formatPace(v)}
                allowDataOverflow={pvhrZoom.isZoomed}
                label={{ value: 'Pace', position: 'insideBottom', offset: -5, style: { fill: '#64748b', fontSize: 11 } }}
              />
              <YAxis
                dataKey="average_heartrate"
                type="number"
                domain={pvhrZoom.yDomain ?? [100, 190]}
                tick={{ fontSize: 10 }}
                allowDataOverflow={pvhrZoom.isZoomed}
                label={{ value: 'Avg HR', angle: -90, position: 'insideLeft', style: { fill: '#64748b', fontSize: 11 } }}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0]?.payload;
                  return (
                    <div style={{ background: '#0d0d0f', border: '1px solid #2a2a32', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
                      <div style={{ fontWeight: 600 }}>{formatActivityName(d)}</div>
                      <div style={{ color: '#94a3b8' }}>{d.date}</div>
                      <div style={{ fontFamily: "var(--font-display)" }}>
                        <span style={{ color: '#26c6f9' }}>{formatPace(d.pace)} /mi</span>{' · '}
                        <span style={{ color: '#f472b6' }}>{formatHR(d.average_heartrate)} bpm</span>
                      </div>
                    </div>
                  );
                }}
              />
              <Scatter
                data={filteredTrends.filter(t => t.pace && t.pace > 4 && t.pace < 20 && t.average_heartrate)}
                fillOpacity={0.5}
                r={3}
              >
                {filteredTrends.filter(t => t.pace && t.pace > 4 && t.pace < 20 && t.average_heartrate).map((t, i) => (
                  <Cell key={i} fill={activityColor(t.type)} fillOpacity={0.5} />
                ))}
              </Scatter>

              {pvhrZoom.referenceAreaProps && <ReferenceArea {...pvhrZoom.referenceAreaProps} />}
            </ScatterChart>
          </SafeResponsiveContainer>
        </div>
      </div>


    </div>
  );
}

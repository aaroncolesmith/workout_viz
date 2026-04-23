import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { LineChart, Line, ResponsiveContainer, Tooltip, XAxis } from 'recharts';
import { MapContainer, TileLayer, Polyline } from 'react-leaflet';
import polyline from 'polyline';
import 'leaflet/dist/leaflet.css';
import { useNavigate } from 'react-router-dom';

import { getRoutes, getRoute, buildRoutes, renameRoute } from '../utils/api';
import { formatDate, formatRelativeAge } from '../utils/format';

const TYPES = ['Run', 'Ride', 'Hike'];
const TYPE_COLOR = { Run: '#38bdf8', Ride: '#818cf8', Hike: '#34d399' };

// ── Mini static map (no interaction) ─────────────────────────────────────────
function MiniMap({ encodedPolyline, color = '#38bdf8', height = 120, mapKey }) {
  if (!encodedPolyline) return (
    <div style={{ height, background: 'rgba(255,255,255,0.03)', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>No map</span>
    </div>
  );

  let positions = [];
  try { positions = polyline.decode(encodedPolyline); } catch { return null; }
  if (!positions.length) return null;

  return (
    <MapContainer
      key={mapKey}
      bounds={positions}
      boundsOptions={{ padding: [10, 10] }}
      style={{ height, width: '100%', borderRadius: 6, background: '#0a0e1a' }}
      scrollWheelZoom={false}
      zoomControl={false}
      dragging={false}
      doubleClickZoom={false}
      attributionControl={false}
    >
      <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
      <Polyline positions={positions} pathOptions={{ color, weight: 3, opacity: 0.9 }} />
      <Polyline positions={positions} pathOptions={{ color, weight: 10, opacity: 0.15 }} />
    </MapContainer>
  );
}

// ── Pace spark ────────────────────────────────────────────────────────────────
function PaceSpark({ data, color }) {
  if (!data || data.length < 2) return null;
  return (
    <ResponsiveContainer width="100%" height={32}>
      <LineChart data={data}>
        <Line type="monotone" dataKey="pace" stroke={color} strokeWidth={1.5} dot={false} />
        <Tooltip
          formatter={v => {
            const m = Math.floor(v); const s = Math.round((v - m) * 60);
            return [`${m}:${s.toString().padStart(2,'0')}/mi`, 'Pace'];
          }}
          contentStyle={{ background: '#0a0e1a', border: '1px solid rgba(255,255,255,0.1)', fontSize: '0.7rem' }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── Route card ────────────────────────────────────────────────────────────────
function RouteCard({ route, color, onClick, selected }) {
  const trend = route.pace_trend;
  return (
    <div
      className="glass-card"
      onClick={onClick}
      style={{
        cursor: 'pointer',
        padding: 0,
        overflow: 'hidden',
        border: selected ? `1px solid ${color}` : undefined,
        transition: 'border-color 0.15s',
      }}
    >
      <MiniMap encodedPolyline={route.representative_polyline} color={color} height={110} mapKey={`card-${route.id}`} />
      <div style={{ padding: '12px 14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
          <div style={{ fontWeight: 600, fontSize: '0.85rem', color: 'var(--text-primary)', marginRight: 8 }}>
            {route.name}
          </div>
          <span style={{ fontSize: '0.65rem', color, background: `${color}15`, border: `1px solid ${color}30`, padding: '1px 7px', borderRadius: 10, whiteSpace: 'nowrap' }}>
            {route.activity_count}×
          </span>
        </div>

        <div style={{ display: 'flex', gap: 12, fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: 8 }}>
          <span>{route.avg_distance_miles} mi</span>
          <span>{route.avg_pace_str}/mi avg</span>
          {route.avg_hr && <span>{Math.round(route.avg_hr)} bpm</span>}
        </div>

        {/* Pace spark */}
        {route.pace_spark?.length > 2 && (
          <PaceSpark data={route.pace_spark} color={color} />
        )}

        {/* Trend badge */}
        {trend && (
          <div style={{ marginTop: 6, fontSize: '0.65rem', display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ color: trend.improving ? '#34d399' : '#fb923c' }}>
              {trend.improving ? '↑ Getting faster' : '↓ Getting slower'}
            </span>
            <span style={{ color: 'var(--text-muted)', opacity: 0.6 }}>
              {Math.abs(trend.delta_sec_per_mi).toFixed(0)}s/mi over {route.activity_count} runs
            </span>
          </div>
        )}

        {route.last_run && (
          <div style={{ marginTop: 4, fontSize: '0.62rem', color: 'var(--text-muted)', opacity: 0.6 }}>
            Last: {formatRelativeAge(route.last_run)}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Route detail panel ────────────────────────────────────────────────────────
function RouteDetail({ routeId, color, onClose }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [nameInput, setNameInput] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['route', routeId],
    queryFn: () => getRoute(routeId),
    enabled: Boolean(routeId),
    staleTime: 60_000,
  });

  const route = data?.route;
  const activities = data?.activities || [];

  const handleRename = async () => {
    if (!nameInput.trim()) return;
    await renameRoute(routeId, nameInput.trim());
    qc.invalidateQueries({ queryKey: ['route', routeId] });
    qc.invalidateQueries({ queryKey: ['routes'] });
    setEditing(false);
  };

  if (isLoading) return (
    <div style={{ padding: 'var(--space-xl)', color: 'var(--text-muted)', display: 'flex', gap: 10, alignItems: 'center' }}>
      <div className="loading-spinner" style={{ width: 14, height: 14 }} />
      Loading route…
    </div>
  );

  if (!route) return null;

  const bestActivity = activities.reduce((best, a) => (!best || a.pace < best.pace) ? a : best, null);

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 'var(--space-lg)' }}>
        <div style={{ flex: 1 }}>
          {editing ? (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                autoFocus
                value={nameInput}
                onChange={e => setNameInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleRename(); if (e.key === 'Escape') setEditing(false); }}
                style={{ background: 'rgba(255,255,255,0.06)', border: `1px solid ${color}`, borderRadius: 6, padding: '5px 10px', color: 'var(--text-primary)', fontSize: '1rem', fontWeight: 700, width: 260 }}
              />
              <button onClick={handleRename} style={{ background: color, border: 'none', borderRadius: 6, padding: '5px 12px', color: '#0a0e1a', fontWeight: 700, cursor: 'pointer', fontSize: '0.8rem' }}>Save</button>
              <button onClick={() => setEditing(false)} style={{ background: 'transparent', border: '1px solid var(--border-subtle)', borderRadius: 6, padding: '5px 10px', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.8rem' }}>Cancel</button>
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)' }}>{route.name}</h2>
              <button onClick={() => { setNameInput(route.name); setEditing(true); }} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.75rem', padding: '2px 6px' }}>✎ Rename</button>
            </div>
          )}
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 4 }}>
            {route.avg_distance_miles} mi · {route.activity_count} runs · {route.first_run} → {route.last_run}
          </div>
        </div>
        <button onClick={onClose} style={{ background: 'none', border: '1px solid var(--border-subtle)', borderRadius: 6, padding: '4px 10px', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.8rem' }}>✕</button>
      </div>

      {/* Map + Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 'var(--space-lg)', marginBottom: 'var(--space-lg)' }}>
        <div style={{ borderRadius: 8, overflow: 'hidden' }}>
          <MiniMap encodedPolyline={route.representative_polyline} color={color} height={220} mapKey={`detail-${routeId}`} />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <StatBox label="Avg Pace" value={route.avg_pace_str + '/mi'} color={color} />
          <StatBox label="Best Pace" value={route.best_pace_str + '/mi'} color="#fbbf24" />
          {route.avg_hr && <StatBox label="Avg HR" value={`${Math.round(route.avg_hr)} bpm`} color="#f472b6" />}
          {route.pace_trend && (
            <div style={{ background: route.pace_trend.improving ? 'rgba(52,211,153,0.08)' : 'rgba(251,146,60,0.08)', border: `1px solid ${route.pace_trend.improving ? 'rgba(52,211,153,0.2)' : 'rgba(251,146,60,0.2)'}`, borderRadius: 8, padding: '10px 12px' }}>
              <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 4 }}>Trend</div>
              <div style={{ fontSize: '0.85rem', fontWeight: 700, color: route.pace_trend.improving ? '#34d399' : '#fb923c' }}>
                {route.pace_trend.improving ? '↑ Faster' : '↓ Slower'}
              </div>
              <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 2 }}>
                {formatPaceStr(route.pace_trend.early_pace)} → {formatPaceStr(route.pace_trend.recent_pace)}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Pace over time chart */}
      {route.pace_spark?.length > 2 && (
        <div className="glass-card" style={{ padding: 'var(--space-md)', marginBottom: 'var(--space-lg)' }}>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', marginBottom: 8 }}>Pace Over Time</div>
          <ResponsiveContainer width="100%" height={80}>
            <LineChart data={route.pace_spark}>
              <Line type="monotone" dataKey="pace" stroke={color} strokeWidth={2} dot={false} />
              <Tooltip
                formatter={v => {
                  const m = Math.floor(v); const s = Math.round((v - m) * 60);
                  return [`${m}:${s.toString().padStart(2,'0')}/mi`, 'Pace'];
                }}
                labelFormatter={(_l, payload) => payload?.[0]?.payload?.date ? formatDate(payload[0].payload.date) : ''}
                contentStyle={{ background: '#0a0e1a', border: '1px solid rgba(255,255,255,0.1)', fontSize: '0.7rem' }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Activity list */}
      <div>
        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', marginBottom: 8 }}>
          All Runs on This Route
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {activities.map(a => (
            <div
              key={a.id}
              onClick={() => navigate(`/activity/${a.id}`)}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '8px 12px', borderRadius: 6,
                background: a.id === bestActivity?.id ? `${color}10` : 'rgba(255,255,255,0.02)',
                border: `1px solid ${a.id === bestActivity?.id ? color + '30' : 'transparent'}`,
                cursor: 'pointer',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                {a.id === bestActivity?.id && <span style={{ fontSize: '0.65rem', color: '#fbbf24' }}>★</span>}
                <div>
                  <div style={{ fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-primary)' }}>{a.name}</div>
                  <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>{formatDate(a.date)} · {a.distance_miles} mi · {a.duration_str}</div>
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '0.82rem', fontFamily: 'Manrope, sans-serif', color, fontWeight: 600 }}>{a.pace_str}/mi</div>
                {a.average_heartrate && <div style={{ fontSize: '0.65rem', color: '#f472b6', opacity: 0.7 }}>{a.average_heartrate} bpm</div>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatBox({ label, value, color }) {
  return (
    <div style={{ background: `${color}08`, border: `1px solid ${color}20`, borderRadius: 8, padding: '8px 12px' }}>
      <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: '0.9rem', fontWeight: 700, color, fontFamily: 'Manrope, sans-serif' }}>{value}</div>
    </div>
  );
}

function formatPaceStr(p) {
  if (!p || p <= 0) return '—';
  const m = Math.floor(p); const s = Math.round((p - m) * 60);
  return `${m}:${s.toString().padStart(2, '0')}/mi`;
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function RoutesPage() {
  const qc = useQueryClient();
  const [activityType, setActivityType] = useState('Run');
  const [selectedRouteId, setSelectedRouteId] = useState(null);
  const [building, setBuilding] = useState(false);
  const [sortBy, setSortBy] = useState('count'); // count | recent | pace | trend

  const color = TYPE_COLOR[activityType] || '#38bdf8';

  const { data, isLoading } = useQuery({
    queryKey: ['routes', activityType],
    queryFn: () => getRoutes(activityType),
    staleTime: 60_000,
  });

  const routes = data?.routes || [];
  const built  = data?.built ?? false;

  const sorted = [...routes].sort((a, b) => {
    if (sortBy === 'count')  return b.activity_count - a.activity_count;
    if (sortBy === 'recent') return (b.last_run || '').localeCompare(a.last_run || '');
    if (sortBy === 'pace')   return (a.best_pace || 99) - (b.best_pace || 99);
    if (sortBy === 'trend')  return ((a.pace_trend?.delta_sec_per_mi ?? 0) - (b.pace_trend?.delta_sec_per_mi ?? 0));
    return 0;
  });

  const handleBuild = async () => {
    setBuilding(true);
    try {
      await buildRoutes(activityType);
      qc.invalidateQueries({ queryKey: ['routes', activityType] });
    } finally {
      setBuilding(false);
    }
  };

  return (
    <div>
      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-xl)' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 700 }}>Route Intelligence</h1>
          <p style={{ margin: '4px 0 0', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Auto-detected routes with performance trends
          </p>
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {/* Type selector */}
          <div style={{ display: 'flex', gap: 4 }}>
            {TYPES.map(t => (
              <button key={t} onClick={() => { setActivityType(t); setSelectedRouteId(null); }}
                className={`filter-chip ${activityType === t ? 'active' : ''}`}
                style={{ fontSize: '0.78rem' }}>
                {t}
              </button>
            ))}
          </div>

          <button
            onClick={handleBuild}
            disabled={building}
            style={{
              background: building ? 'rgba(56,189,248,0.1)' : `${color}20`,
              border: `1px solid ${color}40`,
              borderRadius: 8, padding: '7px 14px',
              color, fontWeight: 600, fontSize: '0.78rem',
              cursor: building ? 'not-allowed' : 'pointer',
              opacity: building ? 0.7 : 1,
            }}
          >
            {building ? 'Clustering…' : built ? 'Rebuild' : 'Detect Routes'}
          </button>
        </div>
      </div>

      {/* Sort bar */}
      {routes.length > 0 && (
        <div style={{ display: 'flex', gap: 6, marginBottom: 'var(--space-lg)', alignItems: 'center' }}>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginRight: 4 }}>Sort:</span>
          {[
            { key: 'count',  label: 'Most runs' },
            { key: 'recent', label: 'Recently run' },
            { key: 'pace',   label: 'Fastest' },
            { key: 'trend',  label: 'Most improved' },
          ].map(s => (
            <button key={s.key} onClick={() => setSortBy(s.key)}
              className={`filter-chip ${sortBy === s.key ? 'active' : ''}`}
              style={{ fontSize: '0.72rem', padding: '4px 10px' }}>
              {s.label}
            </button>
          ))}
          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginLeft: 4 }}>
            {routes.length} routes · {routes.reduce((s, r) => s + r.activity_count, 0)} activities
          </span>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !built && (
        <div className="glass-card" style={{ padding: 'var(--space-xl)', textAlign: 'center' }}>
          <div style={{ fontWeight: 600, fontSize: '1rem', marginBottom: 6 }}>No routes detected yet</div>
          <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: 'var(--space-lg)' }}>
            Click <strong>Detect Routes</strong> to cluster your {activityType.toLowerCase()}s by GPS course.
          </div>
          <button onClick={handleBuild} disabled={building}
            style={{ background: `${color}20`, border: `1px solid ${color}50`, borderRadius: 8, padding: '8px 20px', color, fontWeight: 600, fontSize: '0.82rem', cursor: 'pointer' }}>
            {building ? 'Clustering…' : 'Detect Routes'}
          </button>
        </div>
      )}

      {/* Two-column layout: grid | detail panel */}
      {routes.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: selectedRouteId ? '1fr 520px' : '1fr', gap: 'var(--space-xl)', alignItems: 'start' }}>
          {/* Route grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 'var(--space-md)' }}>
            {sorted.map(route => (
              <RouteCard
                key={route.id}
                route={route}
                color={color}
                selected={route.id === selectedRouteId}
                onClick={() => setSelectedRouteId(prev => prev === route.id ? null : route.id)}
              />
            ))}
          </div>

          {/* Detail panel */}
          {selectedRouteId && (
            <div className="glass-card" style={{ padding: 'var(--space-lg)', position: 'sticky', top: 80, maxHeight: 'calc(100vh - 120px)', overflowY: 'auto' }}>
              <RouteDetail
                routeId={selectedRouteId}
                color={color}
                onClose={() => setSelectedRouteId(null)}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

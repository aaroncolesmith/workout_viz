import React, { useMemo } from 'react';
import { MapContainer, TileLayer, Polyline, Marker, Popup, useMap } from 'react-leaflet';
import polyline from 'polyline';
import 'leaflet/dist/leaflet.css';

// Fix default marker icon (leaflet + bundler issue)
import L from 'leaflet';
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

/** Auto-fit map bounds to the route */
function FitBounds({ positions }) {
  const map = useMap();
  useMemo(() => {
    if (positions.length > 1) {
      const bounds = L.latLngBounds(positions);
      map.fitBounds(bounds, { padding: [30, 30] });
    }
  }, [positions, map]);
  return null;
}

/**
 * RouteMap — renders a decoded summary_polyline on a dark tile map.
 * Supports multiple polylines for comparison.
 */
export default function RouteMap({ 
  encodedPolyline, 
  activityType = 'Run', 
  height = 400,
  comparisonActivities = [] 
}) {
  // Main route positions
  const positions = useMemo(() => {
    if (!encodedPolyline) return [];
    try {
      return polyline.decode(encodedPolyline);
    } catch {
      return [];
    }
  }, [encodedPolyline]);

  // Comparison route positions
  const comparisonPaths = useMemo(() => {
    return comparisonActivities
      .map(ca => {
        if (!ca.map_polyline) return null;
        try {
          return {
            id: ca.id,
            positions: polyline.decode(ca.map_polyline),
            type: ca.type
          };
        } catch {
          return null;
        }
      })
      .filter(p => p && p.positions.length > 0);
  }, [comparisonActivities]);

  // All valid positions for bounds fitting
  const allPositions = useMemo(() => {
    let all = [...positions];
    comparisonPaths.forEach(cp => {
      all = all.concat(cp.positions);
    });
    return all;
  }, [positions, comparisonPaths]);

  if (!positions.length && !comparisonPaths.length) return null;

  const center = positions.length > 0 ? positions[Math.floor(positions.length / 2)] : 
                 comparisonPaths.length > 0 ? comparisonPaths[0].positions[Math.floor(comparisonPaths[0].positions.length / 2)] : 
                 [0, 0];
                 
  const start = positions.length > 0 ? positions[0] : 
                comparisonPaths.length > 0 ? comparisonPaths[0].positions[0] : null;

  const colorMap = {
    Run: '#38bdf8',
    Ride: '#818cf8',
    Hike: '#34d399',
    Walk: '#fbbf24',
  };
  
  const comparisonColors = ['#fb7185', '#34d399', '#facc15', '#a78bfa']; // Matching radar/chart colors
  const primaryColor = colorMap[activityType] || '#38bdf8';

  return (
    <div className="glass-card" style={{ overflow: 'hidden', borderRadius: 'var(--radius-lg)' }}>
      <MapContainer
        center={center}
        zoom={14}
        style={{ height, width: '100%', background: '#0a0e1a' }}
        scrollWheelZoom={false}
        zoomControl={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://carto.com/">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />
        
        {/* Draw comparisons first (back) */}
        {comparisonPaths.map((cp, idx) => (
          <React.Fragment key={cp.id}>
            <Polyline
              positions={cp.positions}
              pathOptions={{
                color: comparisonColors[idx % comparisonColors.length],
                weight: 3,
                opacity: 0.6,
                lineCap: 'round',
                lineJoin: 'round',
              }}
            />
          </React.Fragment>
        ))}

        {/* Draw primary route (front) */}
        {positions.length > 0 && (
          <>
            <Polyline
              positions={positions}
              pathOptions={{
                color: primaryColor,
                weight: 4,
                opacity: 0.9,
                lineCap: 'round',
                lineJoin: 'round',
              }}
            />
            {/* Glow */}
            <Polyline
              positions={positions}
              pathOptions={{
                color: primaryColor,
                weight: 12,
                opacity: 0.2,
                lineCap: 'round',
                lineJoin: 'round',
              }}
            />
          </>
        )}

        {start && (
          <Marker position={start}>
            <Popup>Start</Popup>
          </Marker>
        )}

        {positions.length > 0 && (() => {
          const end = positions[positions.length - 1];
          const isLoop = Math.abs(start[0] - end[0]) < 0.0005 && Math.abs(start[1] - end[1]) < 0.0005;
          return !isLoop && (
            <Marker position={end}>
              <Popup>Finish</Popup>
            </Marker>
          );
        })()}

        <FitBounds positions={allPositions} />
      </MapContainer>
    </div>
  );
}

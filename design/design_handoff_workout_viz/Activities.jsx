
// ── Mock activities data ──────────────────────────────────────────────────────
const ACTIVITIES_DATA = [
  { id: 1,  type: 'Walk',           name: 'Morning Walk',       date: 'Apr 27, 2026', relDate: 'Today',    miles: 1.15, time: '28m',    avgPace: '24:21', avgHR: 92,  maxHR: 108, elevation: 12  },
  { id: 2,  type: 'Ride',           name: 'Afternoon Ride',     date: 'Apr 26, 2026', relDate: 'Yesterday',miles: 2.25, time: '15m',    avgPace: '9:03',  avgHR: 115, maxHR: 138, elevation: 64  },
  { id: 3,  type: 'Ride',           name: 'Long Ride',          date: 'Apr 25, 2026', relDate: '2d ago',   miles: 22.0, time: '2h 5m',  avgPace: '9:05',  avgHR: 138, maxHR: 162, elevation: 820 },
  { id: 4,  type: 'Walk',           name: 'Evening Walk',       date: 'Apr 24, 2026', relDate: '3d ago',   miles: 1.52, time: '37m',    avgPace: '24:21', avgHR: 89,  maxHR: 102, elevation: 28  },
  { id: 5,  type: 'Run',            name: 'Morning Run',        date: 'Apr 23, 2026', relDate: '4d ago',   miles: 6.34, time: '52m',    avgPace: '8:12',  avgHR: 166, maxHR: 179, elevation: 499 },
  { id: 6,  type: 'WeightTraining', name: 'Strength Session',   date: 'Apr 22, 2026', relDate: '5d ago',   miles: 0,    time: '42m',    avgPace: null,    avgHR: 128, maxHR: 158, elevation: 0   },
  { id: 7,  type: 'Run',            name: 'Easy Run',           date: 'Apr 20, 2026', relDate: '7d ago',   miles: 4.20, time: '38m',    avgPace: '9:03',  avgHR: 148, maxHR: 165, elevation: 210 },
  { id: 8,  type: 'Hike',           name: 'Trail Hike',         date: 'Apr 18, 2026', relDate: '9d ago',   miles: 5.80, time: '1h 45m', avgPace: '18:06', avgHR: 132, maxHR: 156, elevation: 1240},
  { id: 9,  type: 'Run',            name: 'Tempo Run',          date: 'Apr 16, 2026', relDate: '11d ago',  miles: 7.10, time: '58m',    avgPace: '8:09',  avgHR: 172, maxHR: 183, elevation: 380 },
  { id: 10, type: 'Swim',           name: 'Pool Swim',          date: 'Apr 14, 2026', relDate: '13d ago',  miles: 1.0,  time: '40m',    avgPace: '40:00', avgHR: 142, maxHR: 162, elevation: 0   },
  { id: 11, type: 'WeightTraining', name: 'Upper Body',         date: 'Apr 13, 2026', relDate: '14d ago',  miles: 0,    time: '55m',    avgPace: null,    avgHR: 135, maxHR: 165, elevation: 0   },
  { id: 12, type: 'Run',            name: 'Long Run',           date: 'Apr 12, 2026', relDate: '15d ago',  miles: 13.1, time: '1h 58m', avgPace: '9:01',  avgHR: 158, maxHR: 174, elevation: 620 },
];

const FILTER_TYPES = [
  { key: 'All',           label: 'All',    count: null,  color: '#f0f0f4' },
  { key: 'Run',           label: 'Run',    count: 993,   color: '#26c6f9' },
  { key: 'Walk',          label: 'Walk',   count: 812,   color: '#f59e0b' },
  { key: 'Ride',          label: 'Ride',   count: 704,   color: '#a78bfa' },
  { key: 'WeightTraining',label: 'Weight', count: 331,   color: '#f472b6' },
  { key: 'Hike',          label: 'Hike',   count: 141,   color: '#34d399' },
  { key: 'HIIT',          label: 'HIIT',   count: 96,    color: '#fb923c' },
  { key: 'Swim',          label: 'Swim',   count: 19,    color: '#22d3ee' },
];

// ── Portland run route (approx 6.3 mi, downtown loop) ────────────────────────
const PORTLAND_ROUTE = [
  [45.5338, -122.6772],[45.5325, -122.6772],[45.5312, -122.6775],
  [45.5298, -122.6780],[45.5285, -122.6786],[45.5272, -122.6798],
  [45.5260, -122.6812],[45.5248, -122.6831],[45.5235, -122.6849],
  [45.5222, -122.6858],[45.5210, -122.6852],[45.5198, -122.6841],
  [45.5188, -122.6828],[45.5178, -122.6810],[45.5170, -122.6792],
  [45.5164, -122.6771],[45.5160, -122.6748],[45.5158, -122.6724],
  [45.5160, -122.6700],[45.5165, -122.6680],[45.5172, -122.6664],
  [45.5182, -122.6651],[45.5195, -122.6644],[45.5210, -122.6641],
  [45.5225, -122.6645],[45.5238, -122.6652],[45.5248, -122.6662],
  [45.5258, -122.6675],[45.5268, -122.6690],[45.5278, -122.6706],
  [45.5290, -122.6718],[45.5302, -122.6728],[45.5314, -122.6738],
  [45.5324, -122.6748],[45.5332, -122.6758],[45.5338, -122.6772],
];

// ── Generate HR curve ─────────────────────────────────────────────────────────
function generateHRData(n = 56) {
  return Array.from({ length: n }, (_, i) => {
    const t = i / n;
    let hr;
    if (t < 0.08) hr = 90 + t * 12 * 55;
    else if (t < 0.15) hr = 145 + (t - 0.08) * 14 * 20;
    else if (t < 0.75) hr = 158 + Math.sin(t * 14) * 9 + t * 14;
    else hr = 172 - (t - 0.75) * 30;
    const mins = Math.round(t * 52);
    return { hr: Math.max(85, Math.min(185, Math.round(hr + (Math.random() - 0.5) * 6))), label: `${mins}m` };
  });
}

// ── Leaflet map component ─────────────────────────────────────────────────────
function RouteMap({ color, height, mapKey }) {
  const containerRef = React.useRef(null);
  const mapRef = React.useRef(null);

  React.useEffect(() => {
    if (!window.L || !containerRef.current || mapRef.current) return;
    const timer = setTimeout(() => {
      if (!containerRef.current) return;
      const map = window.L.map(containerRef.current, {
        zoomControl: false, scrollWheelZoom: false,
        attributionControl: true, dragging: true, touchZoom: true,
      });
      window.L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '© CARTO', maxZoom: 16, subdomains: 'abcd',
      }).addTo(map);
      const poly = window.L.polyline(PORTLAND_ROUTE, {
        color, weight: 4, opacity: 0.95, lineCap: 'round', lineJoin: 'round',
      }).addTo(map);
      // Start dot
      window.L.circleMarker(PORTLAND_ROUTE[0], {
        radius: 8, fillColor: '#ffffff', color, weight: 2.5, fillOpacity: 1,
      }).addTo(map);
      map.fitBounds(poly.getBounds(), { padding: [28, 28] });
      mapRef.current = map;
    }, 80);
    return () => {
      clearTimeout(timer);
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; }
    };
  }, [mapKey]);

  // Invalidate size when height changes (fullscreen)
  React.useEffect(() => {
    if (mapRef.current) {
      setTimeout(() => mapRef.current && mapRef.current.invalidateSize(), 120);
    }
  }, [height]);

  return (
    <div ref={containerRef} style={{
      width: '100%', height,
      borderRadius: typeof height === 'number' ? 12 : 0,
      overflow: 'hidden', background: '#141418',
    }} />
  );
}

// ── HR line chart SVG ─────────────────────────────────────────────────────────
function HRLineChart({ data, color = COLORS.pink, height = 100 }) {
  if (!data || data.length < 2) return null;
  const vals = data.map(d => d.hr);
  const max = Math.max(...vals), min = Math.min(...vals);
  const range = max - min || 1;
  const w = 300, h = height - 18;
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 6) - 3;
    return { x, y, v };
  });
  const polyline = pts.map(p => `${p.x},${p.y}`).join(' ');
  const area = `M 0,${h} L ${polyline} L ${w},${h} Z`;
  const labelStep = Math.ceil(data.length / 7);
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="xMidYMid meet">
      <defs>
        <linearGradient id="hrGrad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75, 1].map(lvl => (
        <line key={lvl} x1={0} y1={h * lvl} x2={w} y2={h * lvl}
          stroke={COLORS.borderFaint} strokeWidth={0.8} strokeDasharray="4,4"/>
      ))}
      <path d={area} fill="url(#hrGrad)"/>
      <polyline points={polyline} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"/>
      {data.filter((_, i) => i % labelStep === 0).map((d, i) => {
        const idx = data.indexOf(d);
        const x = (idx / (data.length - 1)) * w;
        return (
          <text key={i} x={x} y={height - 3} textAnchor="middle"
            fill={COLORS.textMuted} style={{ fontSize: 8, fontFamily: 'inherit' }}>
            {d.label}
          </text>
        );
      })}
    </svg>
  );
}

// ── Fullscreen split view (portal) ────────────────────────────────────────────
function FullscreenView({ activity, paceData, hrData, onClose }) {
  const cfg = getActivityCfg(activity.type);

  React.useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, []);

  const content = (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 99999,
      background: '#09090c',
      display: 'flex', flexDirection: 'column',
      fontFamily: "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    }}>
      {/* Header */}
      <div style={{
        height: 56, display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', padding: '0 20px',
        borderBottom: `1px solid ${COLORS.border}`, flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <ActivityBadge type={activity.type} size={32}/>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: COLORS.textPrimary, letterSpacing: '-0.02em' }}>
              {activity.name}
            </div>
            <div style={{ fontSize: 12, color: COLORS.textMuted }}>{activity.date} · {activity.miles} mi · {activity.time}</div>
          </div>
        </div>
        <button onClick={onClose} style={{
          width: 32, height: 32, borderRadius: '50%',
          background: COLORS.card, border: `1px solid ${COLORS.border}`,
          color: COLORS.textSecondary, fontSize: 18, lineHeight: 1,
          cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>×</button>
      </div>

      {/* Body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* ── Left: map ── */}
        <div style={{ flex: '0 0 58%', position: 'relative' }}>
          <RouteMap color={cfg.color} height="100%" mapKey={`fs-${activity.id}`}/>
          {/* Floating stats on map */}
          <div style={{
            position: 'absolute', bottom: 20, left: 20,
            display: 'flex', gap: 10, zIndex: 1000,
          }}>
            {[
              { label: 'Pace', value: activity.avgPace, unit: '/mi' },
              { label: 'Avg HR', value: `${activity.avgHR}`, unit: 'bpm' },
              { label: 'Elev', value: `${activity.elevation}`, unit: 'ft' },
            ].map(s => s.value && (
              <div key={s.label} style={{
                background: '#000000bb', backdropFilter: 'blur(12px)',
                borderRadius: 10, padding: '8px 12px',
                border: `1px solid ${COLORS.border}`,
              }}>
                <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', color: COLORS.textMuted, textTransform: 'uppercase', marginBottom: 2 }}>{s.label}</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 2 }}>
                  <span style={{ fontSize: 16, fontWeight: 800, color: cfg.color, letterSpacing: '-0.03em' }}>{s.value}</span>
                  <span style={{ fontSize: 10, color: COLORS.textMuted }}>{s.unit}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ── Right: charts ── */}
        <div style={{
          flex: 1, display: 'flex', flexDirection: 'column',
          gap: 0, borderLeft: `1px solid ${COLORS.border}`, overflow: 'hidden',
        }}>
          {/* Pace chart */}
          <div style={{
            flex: 1, padding: '18px 20px',
            borderBottom: `1px solid ${COLORS.border}`,
            display: 'flex', flexDirection: 'column',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
              <div>
                <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', color: COLORS.textSecondary, textTransform: 'uppercase' }}>Pace</span>
                <span style={{ fontSize: 11, color: COLORS.textMuted }}> per 0.1 mi</span>
              </div>
              <span style={{ fontSize: 22, fontWeight: 800, color: cfg.color, letterSpacing: '-0.04em' }}>
                {activity.avgPace}<span style={{ fontSize: 12, fontWeight: 500, color: COLORS.textMuted }}>/mi avg</span>
              </span>
            </div>
            <div style={{ flex: 1, display: 'flex', alignItems: 'center' }}>
              <PaceLineChart data={paceData} color={cfg.color} height={120}/>
            </div>
          </div>

          {/* HR chart */}
          <div style={{
            flex: 1, padding: '18px 20px',
            display: 'flex', flexDirection: 'column',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
              <div>
                <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', color: COLORS.textSecondary, textTransform: 'uppercase' }}>Heart Rate</span>
              </div>
              <div style={{ display: 'flex', gap: 14 }}>
                <span style={{ fontSize: 12, color: COLORS.textMuted }}>
                  Avg <span style={{ color: COLORS.pink, fontWeight: 700 }}>{activity.avgHR}</span>
                </span>
                <span style={{ fontSize: 12, color: COLORS.textMuted }}>
                  Max <span style={{ color: COLORS.red, fontWeight: 700 }}>{activity.maxHR}</span>
                </span>
              </div>
            </div>
            <div style={{ flex: 1, display: 'flex', alignItems: 'center' }}>
              <HRLineChart data={hrData} height={120}/>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  return ReactDOM.createPortal(content, document.body);
}

// ── Activity Detail ────────────────────────────────────────────────────────────
function ActivityDetail({ activity, onBack }) {
  const [activeTab, setActiveTab] = React.useState('Overview');
  const [showFullscreen, setShowFullscreen] = React.useState(false);
  const cfg = getActivityCfg(activity.type);
  const tabs = ['Overview', 'Splits', 'Compare', 'Segments'];

  const paceData = React.useMemo(() => Array.from({ length: Math.max(14, Math.round(activity.miles * 2)) }, (_, i) => {
    const base = 495;
    return { pace: base + Math.sin(i * 0.9) * 28 + (Math.random() * 36 - 18), label: `${(i * 0.5).toFixed(1)}` };
  }), [activity.id]);

  const hrData = React.useMemo(() => generateHRData(56), [activity.id]);

  const radarData = [
    { label: 'Pace',     value: 0.82 },
    { label: 'Distance', value: 0.74 },
    { label: 'HR',       value: 0.91 },
    { label: 'Effort',   value: 0.68 },
    { label: 'Duration', value: 0.79 },
  ];

  const stats6 = [
    { label: 'Distance', value: activity.miles > 0 ? `${activity.miles}` : '—', unit: activity.miles > 0 ? 'mi' : '' },
    { label: 'Duration', value: activity.time },
    { label: 'Pace',     value: activity.avgPace || '—', unit: activity.avgPace ? '/mi' : '' },
    { label: 'Avg HR',   value: `${activity.avgHR}`, unit: 'bpm', color: COLORS.pink },
    { label: 'Max HR',   value: `${activity.maxHR}`, unit: 'bpm', color: COLORS.red },
    { label: 'Elevation',value: `${activity.elevation}`, unit: 'ft' },
  ];

  return (
    <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 82, overflowY: 'auto', overflowX: 'hidden', WebkitOverflowScrolling: 'touch' }}>
      {/* Hero */}
      <div style={{ padding: '12px 16px 0', background: COLORS.bg }}>
        <button onClick={onBack} style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: 'none', border: 'none', cursor: 'pointer',
          color: cfg.color, fontSize: 14, fontWeight: 500, padding: '4px 0', marginBottom: 14,
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="15 18 9 12 15 6"/></svg>
          Activities
        </button>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16 }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <ActivityBadge type={activity.type} size={34}/>
              <span style={{ fontSize: 12, fontWeight: 600, color: cfg.color, background: `${cfg.color}18`, padding: '3px 10px', borderRadius: 20, border: `1px solid ${cfg.color}30` }}>
                {activity.type.replace(/([A-Z])/g, ' $1').trim()}
              </span>
              <span style={{ fontSize: 11, color: COLORS.amber, background: '#f59e0b18', padding: '3px 8px', borderRadius: 20, border: '1px solid #f59e0b30' }}>Apple Health</span>
            </div>
            <h1 style={{ fontSize: 26, fontWeight: 800, color: COLORS.textPrimary, letterSpacing: '-0.04em', margin: '0 0 4px' }}>{activity.name}</h1>
            <div style={{ fontSize: 13, color: COLORS.textSecondary }}>{activity.date}</div>
          </div>
          {activity.miles > 0 && (
            <div style={{ textAlign: 'right', flexShrink: 0, paddingLeft: 12 }}>
              <div style={{ fontSize: 40, fontWeight: 900, color: cfg.color, letterSpacing: '-0.05em', lineHeight: 1 }}>{activity.miles}</div>
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', color: COLORS.textMuted, marginTop: 3 }}>TOTAL MILES</div>
            </div>
          )}
        </div>
      </div>

      {/* Stats grid */}
      <div style={{ padding: '0 16px 16px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 1, background: COLORS.border, borderRadius: 14, overflow: 'hidden', border: `1px solid ${COLORS.border}` }}>
          {stats6.map(s => (
            <div key={s.label} style={{ background: COLORS.card, padding: '12px 12px 10px', display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', color: COLORS.textMuted, textTransform: 'uppercase' }}>{s.label}</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 2 }}>
                <span style={{ fontSize: 18, fontWeight: 800, color: s.color || COLORS.textPrimary, letterSpacing: '-0.04em' }}>{s.value}</span>
                {s.unit && <span style={{ fontSize: 10, color: COLORS.textMuted }}>{s.unit}</span>}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', borderBottom: `1px solid ${COLORS.border}`, paddingLeft: 16, background: COLORS.bg, position: 'sticky', top: 0, zIndex: 10 }}>
        {tabs.map(tab => {
          const active = tab === activeTab;
          return (
            <button key={tab} onClick={() => setActiveTab(tab)} style={{
              padding: '12px 16px', background: 'none', border: 'none',
              color: active ? COLORS.textPrimary : COLORS.textMuted,
              fontSize: 14, fontWeight: active ? 700 : 400, cursor: 'pointer',
              borderBottom: active ? `2px solid ${cfg.color}` : '2px solid transparent', marginBottom: -1,
            }}>{tab}</button>
          );
        })}
      </div>

      {/* Tab content */}
      <div style={{ padding: 16 }}>
        {activeTab === 'Overview' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

            {/* Map card */}
            <Card style={{ overflow: 'hidden', position: 'relative' }}>
              <RouteMap color={cfg.color} height={210} mapKey={`card-${activity.id}`}/>
              {/* Expand button */}
              <button
                onClick={() => setShowFullscreen(true)}
                style={{
                  position: 'absolute', top: 10, right: 10, zIndex: 1000,
                  background: '#000000aa', backdropFilter: 'blur(8px)',
                  border: `1px solid ${COLORS.border}`, borderRadius: 8,
                  color: COLORS.textPrimary, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 5,
                  padding: '6px 10px', fontSize: 11, fontWeight: 600,
                }}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                  <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
                </svg>
                Expand
              </button>
            </Card>

            {/* Pace + HR side note */}
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 2px' }}>
              <div style={{ flex: 1, height: 1, background: COLORS.borderFaint }}/>
              <span style={{ fontSize: 11, color: COLORS.textMuted, flexShrink: 0 }}>Tap Expand for pace & HR alongside map</span>
              <div style={{ flex: 1, height: 1, background: COLORS.borderFaint }}/>
            </div>

            {/* Pace chart */}
            <Card style={{ padding: 16 }}>
              <SectionHeader label="Pace" right={`avg ${activity.avgPace}/mi`}/>
              <PaceLineChart data={paceData} color={cfg.color} height={110}/>
            </Card>

            {/* HR chart */}
            <Card style={{ padding: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', color: COLORS.textSecondary, textTransform: 'uppercase' }}>Heart Rate</span>
                <div style={{ display: 'flex', gap: 12 }}>
                  <span style={{ fontSize: 12, color: COLORS.textMuted }}>Avg <span style={{ color: COLORS.pink, fontWeight: 700 }}>{activity.avgHR}</span></span>
                  <span style={{ fontSize: 12, color: COLORS.textMuted }}>Max <span style={{ color: COLORS.red, fontWeight: 700 }}>{activity.maxHR}</span></span>
                </div>
              </div>
              <HRLineChart data={hrData} height={100}/>
            </Card>

            {/* Radar */}
            <Card style={{ padding: 16 }}>
              <SectionHeader label="Activity Profile"/>
              <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 8 }}>
                <RadarChart data={radarData} size={170} color={cfg.color}/>
              </div>
            </Card>
          </div>
        )}

        {activeTab === 'Splits' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <Card style={{ padding: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div>
                  <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', color: COLORS.textSecondary, textTransform: 'uppercase' }}>Pace Detail</span>
                  <span style={{ fontSize: 11, color: COLORS.textMuted }}> per 0.1 mi</span>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  {['Distance','Time'].map(opt => (
                    <button key={opt} style={{ padding: '4px 10px', borderRadius: 12, fontSize: 11, fontWeight: 600, background: opt==='Distance' ? cfg.color : 'transparent', border: `1px solid ${opt==='Distance' ? cfg.color : COLORS.border}`, color: opt==='Distance' ? '#000' : COLORS.textMuted, cursor: 'pointer' }}>{opt}</button>
                  ))}
                </div>
              </div>
              <PaceLineChart data={paceData} color={cfg.color} height={130}/>
            </Card>
            <Card style={{ padding: 16 }}>
              <SectionHeader label="Mile Splits"/>
              {Array.from({ length: Math.ceil(activity.miles) }, (_, i) => {
                const pace = 490 + Math.sin(i * 1.2) * 25 + Math.random() * 20;
                const mins = Math.floor(pace / 60), secs = Math.round(pace % 60).toString().padStart(2,'0');
                const hr = 155 + i * 3 + Math.round(Math.random() * 8);
                return (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', borderBottom: i < Math.ceil(activity.miles)-1 ? `1px solid ${COLORS.borderFaint}` : 'none' }}>
                    <span style={{ fontSize: 13, color: COLORS.textMuted, width: 24 }}>{i+1}</span>
                    <span style={{ flex: 1, fontSize: 14, fontWeight: 600, color: COLORS.textPrimary }}>{mins}:{secs}/mi</span>
                    <span style={{ fontSize: 13, color: COLORS.pink }}>{hr} bpm</span>
                  </div>
                );
              })}
            </Card>
          </div>
        )}

        {(activeTab === 'Compare' || activeTab === 'Segments') && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', paddingTop: 60, gap: 12 }}>
            <div style={{ fontSize: 36, opacity: 0.2 }}>{activeTab === 'Compare' ? '⚡' : '🏁'}</div>
            <div style={{ fontSize: 15, color: COLORS.textSecondary }}>{activeTab} data coming soon</div>
          </div>
        )}
      </div>

      {/* Fullscreen portal */}
      {showFullscreen && (
        <FullscreenView
          activity={activity}
          paceData={paceData}
          hrData={hrData}
          onClose={() => setShowFullscreen(false)}
        />
      )}
    </div>
  );
}

// ── Activities list ────────────────────────────────────────────────────────────
function Activities({ onSelectActivity }) {
  const [filter, setFilter] = React.useState('All');
  const filtered = filter === 'All' ? ACTIVITIES_DATA : ACTIVITIES_DATA.filter(a => a.type === filter);

  return (
    <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 82, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ padding: '16px 16px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 14 }}>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', color: COLORS.textMuted, textTransform: 'uppercase' }}>Activities</span>
          <span style={{ fontSize: 18, fontWeight: 800, color: COLORS.textPrimary, letterSpacing: '-0.04em' }}>3,568</span>
          <span style={{ fontSize: 13, color: COLORS.textMuted }}>total</span>
        </div>
        <div style={{ display: 'flex', gap: 7, overflowX: 'auto', paddingBottom: 14, scrollbarWidth: 'none', marginLeft: -16, marginRight: -16, paddingLeft: 16, paddingRight: 16 }}>
          {FILTER_TYPES.map(f => (
            <FilterChip key={f.key} label={f.label} count={f.key !== 'All' ? f.count : null} active={filter === f.key} color={f.color} onClick={() => setFilter(f.key)}/>
          ))}
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '0 16px 16px', WebkitOverflowScrolling: 'touch' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {filtered.map(activity => {
            const cfg = getActivityCfg(activity.type);
            return (
              <div key={activity.id} onClick={() => onSelectActivity(activity)} style={{
                background: COLORS.card, borderRadius: 14, border: `1px solid ${COLORS.border}`,
                borderLeft: `3px solid ${cfg.color}`, padding: '13px 14px',
                display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer',
              }}>
                <ActivityBadge type={activity.type} size={40}/>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 15, fontWeight: 700, color: COLORS.textPrimary, marginBottom: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{activity.name}</div>
                  <div style={{ fontSize: 12, color: COLORS.textMuted }}>
                    <span style={{ color: COLORS.textSecondary }}>{activity.relDate}</span> · {activity.date}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 16, flexShrink: 0, alignItems: 'flex-end' }}>
                  {activity.miles > 0 && (
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: 15, fontWeight: 700, color: COLORS.textPrimary, letterSpacing: '-0.03em' }}>{activity.miles}</div>
                      <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', color: COLORS.textMuted }}>MI</div>
                    </div>
                  )}
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 15, fontWeight: 700, color: COLORS.textPrimary, letterSpacing: '-0.02em' }}>{activity.time}</div>
                    <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', color: COLORS.textMuted }}>TIME</div>
                  </div>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={COLORS.textMuted} strokeWidth="2.5" strokeLinecap="round"><polyline points="9 18 15 12 9 6"/></svg>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

window.Activities = Activities;
window.ActivityDetail = ActivityDetail;
window.ACTIVITIES_DATA = ACTIVITIES_DATA;

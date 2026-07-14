
// ── Shared constants ──────────────────────────────────────────────────────────

const COLORS = {
  bg: '#0d0d0f',
  card: '#18181c',
  cardAlt: '#1e1e24',
  border: '#2a2a32',
  borderFaint: '#1f1f26',
  textPrimary: '#f0f0f4',
  textSecondary: '#8a8a96',
  textMuted: '#4a4a56',
  green: '#22c55e',
  cyan: '#26c6f9',
  amber: '#f59e0b',
  violet: '#a78bfa',
  pink: '#f472b6',
  emerald: '#34d399',
  teal: '#22d3ee',
  orange: '#fb923c',
  purple: '#c084fc',
  fuchsia: '#e879f9',
  red: '#f87171',
};

const ACTIVITY_CFG = {
  Run:                      { color: '#26c6f9', bg: '#0a2030', abbr: 'RN' },
  Walk:                     { color: '#f59e0b', bg: '#241a04', abbr: 'WK' },
  Ride:                     { color: '#a78bfa', bg: '#1a1030', abbr: 'RI' },
  WeightTraining:           { color: '#f472b6', bg: '#280a18', abbr: 'WT' },
  Hike:                     { color: '#34d399', bg: '#051a12', abbr: 'HK' },
  Swim:                     { color: '#22d3ee', bg: '#051820', abbr: 'SW' },
  HIIT:                     { color: '#fb923c', bg: '#221206', abbr: 'HI' },
  Workout:                  { color: '#c084fc', bg: '#160d28', abbr: 'WO' },
  FunctionalStrengthTraining:{ color: '#e879f9', bg: '#1e0622', abbr: 'FS' },
  Crossfit:                 { color: '#f87171', bg: '#200808', abbr: 'CF' },
  Rowing:                   { color: '#38bdf8', bg: '#051824', abbr: 'RW' },
  Yoga:                     { color: '#a3e635', bg: '#0e1a04', abbr: 'YG' },
};

function getActivityCfg(type) {
  return ACTIVITY_CFG[type] || { color: '#8a8a96', bg: '#1a1a20', abbr: type.slice(0,2).toUpperCase() };
}

// ── Activity type icon badge ──────────────────────────────────────────────────
function ActivityBadge({ type, size = 40 }) {
  const cfg = getActivityCfg(type);
  return (
    <div style={{
      width: size, height: size, borderRadius: size * 0.28,
      background: cfg.bg,
      border: `1px solid ${cfg.color}30`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexShrink: 0,
    }}>
      <span style={{ fontSize: size * 0.32, fontWeight: 700, color: cfg.color, letterSpacing: '-0.02em' }}>
        {cfg.abbr}
      </span>
    </div>
  );
}

// ── Card wrapper ──────────────────────────────────────────────────────────────
function Card({ children, style, onClick }) {
  return (
    <div onClick={onClick} style={{
      background: COLORS.card,
      borderRadius: 16,
      border: `1px solid ${COLORS.border}`,
      overflow: 'hidden',
      ...style,
    }}>
      {children}
    </div>
  );
}

// ── Section header ────────────────────────────────────────────────────────────
function SectionHeader({ label, right }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
      <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', color: COLORS.textSecondary, textTransform: 'uppercase' }}>
        {label}
      </span>
      {right && <span style={{ fontSize: 12, color: COLORS.textMuted }}>{right}</span>}
    </div>
  );
}

// ── Pill / period selector ────────────────────────────────────────────────────
function PillSelector({ options, value, onChange, style }) {
  return (
    <div style={{ display: 'flex', gap: 6, ...style }}>
      {options.map(opt => {
        const active = opt === value;
        return (
          <button key={opt} onClick={() => onChange(opt)} style={{
            padding: '5px 12px', borderRadius: 20,
            background: active ? COLORS.cyan : 'transparent',
            border: `1px solid ${active ? COLORS.cyan : COLORS.border}`,
            color: active ? '#000' : COLORS.textSecondary,
            fontSize: 13, fontWeight: active ? 700 : 500,
            cursor: 'pointer', transition: 'all 0.15s',
          }}>
            {opt}
          </button>
        );
      })}
    </div>
  );
}

// ── Filter chip (activity type) ───────────────────────────────────────────────
function FilterChip({ label, count, active, color, onClick }) {
  return (
    <button onClick={onClick} style={{
      display: 'flex', alignItems: 'center', gap: 5,
      padding: '7px 12px', borderRadius: 20, flexShrink: 0,
      background: active ? `${color}22` : 'transparent',
      border: `1px solid ${active ? color : COLORS.border}`,
      color: active ? color : COLORS.textSecondary,
      fontSize: 13, fontWeight: active ? 600 : 400,
      cursor: 'pointer', transition: 'all 0.15s',
      whiteSpace: 'nowrap',
    }}>
      {label}
      {count != null && (
        <span style={{ fontSize: 11, opacity: 0.7 }}>{count}</span>
      )}
    </button>
  );
}

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ label, value, unit, accentColor, style }) {
  return (
    <Card style={{ padding: '16px 16px 14px', ...style }}>
      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', color: COLORS.textMuted, textTransform: 'uppercase', marginBottom: 8 }}>
        {label}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
        <span style={{ fontSize: 28, fontWeight: 700, color: COLORS.textPrimary, letterSpacing: '-0.03em', lineHeight: 1 }}>
          {value}
        </span>
        {unit && <span style={{ fontSize: 13, color: COLORS.textSecondary, fontWeight: 500 }}>{unit}</span>}
      </div>
      <div style={{ height: 2, borderRadius: 2, background: COLORS.borderFaint, marginTop: 12 }}>
        <div style={{ height: 2, borderRadius: 2, width: '60%', background: accentColor || COLORS.textMuted }} />
      </div>
    </Card>
  );
}

// ── Bottom navigation ─────────────────────────────────────────────────────────
function BottomNav({ active, onChange }) {
  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>
        <rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>
      </svg>
    )},
    { id: 'activities', label: 'Activities', icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
      </svg>
    )},
    { id: 'advanced', label: 'Advanced', icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/>
        <line x1="6" y1="20" x2="6" y2="14"/>
      </svg>
    )},
  ];
  return (
    <div style={{
      position: 'absolute', bottom: 0, left: 0, right: 0,
      height: 82,
      background: `${COLORS.bg}ee`,
      backdropFilter: 'blur(20px)',
      borderTop: `1px solid ${COLORS.border}`,
      display: 'flex', alignItems: 'flex-start', justifyContent: 'space-around',
      paddingTop: 10, paddingBottom: 20, zIndex: 100,
    }}>
      {tabs.map(tab => {
        const isActive = tab.id === active;
        return (
          <button key={tab.id} onClick={() => onChange(tab.id)} style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
            background: 'none', border: 'none', cursor: 'pointer',
            color: isActive ? COLORS.cyan : COLORS.textMuted,
            transition: 'color 0.15s', padding: '4px 16px',
          }}>
            {tab.icon}
            <span style={{ fontSize: 10, fontWeight: isActive ? 600 : 400, letterSpacing: '0.02em' }}>
              {tab.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// ── SVG Donut chart ───────────────────────────────────────────────────────────
function DonutChart({ data, size = 170 }) {
  const cx = size / 2, cy = size / 2;
  const r = size * 0.38, strokeW = size * 0.13;
  const circumference = 2 * Math.PI * r;
  const total = data.reduce((s, d) => s + d.value, 0);
  let cumulative = 0;
  const segments = data.map(d => {
    const fraction = d.value / total;
    const dashLen = fraction * circumference;
    const offset = circumference - cumulative * circumference / total;
    cumulative += d.value;
    return { ...d, dashLen, offset };
  });
  const center = data[0];
  return (
    <svg width={size} height={size} style={{ overflow: 'visible' }}>
      {/* Background ring */}
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={COLORS.borderFaint} strokeWidth={strokeW} />
      {segments.map((seg, i) => (
        <circle key={i} cx={cx} cy={cy} r={r} fill="none"
          stroke={seg.color} strokeWidth={strokeW}
          strokeDasharray={`${seg.dashLen} ${circumference - seg.dashLen}`}
          strokeDashoffset={seg.offset}
          strokeLinecap="butt"
          style={{ transform: 'rotate(-90deg)', transformOrigin: `${cx}px ${cy}px` }}
        />
      ))}
      <text x={cx} y={cy - 8} textAnchor="middle" fill={center.color}
        style={{ fontSize: size * 0.16, fontWeight: 700, fontFamily: 'inherit' }}>
        {Math.round(center.value / total * 100)}%
      </text>
      <text x={cx} y={cy + 10} textAnchor="middle" fill={COLORS.textMuted}
        style={{ fontSize: size * 0.07, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', fontFamily: 'inherit' }}>
        {center.label}
      </text>
    </svg>
  );
}

// ── SVG Activity Calendar (heatmap) ──────────────────────────────────────────
function ActivityCalendar({ weeks = 26 }) {
  const days = ['M', '', 'W', '', 'F', '', 'S'];
  const cellSize = 11, gap = 2;
  const totalCells = weeks * 7;

  // Generate mock intensity data
  const data = Array.from({ length: totalCells }, (_, i) => {
    const r = Math.random();
    if (r < 0.2) return 0;
    if (r < 0.5) return 1;
    if (r < 0.75) return 2;
    if (r < 0.9) return 3;
    return 4;
  });

  const intensityColors = ['#1a1a20', '#0d3320', '#0f5a30', '#16a34a', '#22c55e'];
  const monthLabels = ['Nov','Dec','Jan','Feb','Mar','Apr'];

  const svgW = weeks * (cellSize + gap) + 24;
  const svgH = 7 * (cellSize + gap) + 20;

  return (
    <svg width="100%" viewBox={`0 0 ${svgW} ${svgH}`} style={{ overflow: 'visible' }}>
      {/* Month labels */}
      {monthLabels.map((m, i) => (
        <text key={m} x={24 + i * (weeks / monthLabels.length) * (cellSize + gap)}
          y={10} fill={COLORS.textMuted} style={{ fontSize: 9, fontFamily: 'inherit' }}>
          {m}
        </text>
      ))}
      {/* Day labels */}
      {days.map((d, row) => (
        d ? <text key={row} x={0} y={20 + row * (cellSize + gap) + cellSize * 0.85}
          fill={COLORS.textMuted} style={{ fontSize: 8, fontFamily: 'inherit' }}>{d}</text> : null
      ))}
      {/* Cells */}
      {Array.from({ length: weeks }, (_, week) =>
        Array.from({ length: 7 }, (_, day) => {
          const idx = week * 7 + day;
          const intensity = data[idx] || 0;
          return (
            <rect key={idx}
              x={24 + week * (cellSize + gap)}
              y={20 + day * (cellSize + gap)}
              width={cellSize} height={cellSize}
              rx={2}
              fill={intensityColors[intensity]}
            />
          );
        })
      )}
    </svg>
  );
}

// ── Simple bar chart ──────────────────────────────────────────────────────────
function BarChart({ data, color = COLORS.violet, height = 80 }) {
  const max = Math.max(...data.map(d => d.value));
  const w = 100 / data.length;
  return (
    <svg width="100%" height={height} preserveAspectRatio="none" viewBox={`0 0 100 ${height}`}>
      {data.map((d, i) => {
        const barH = (d.value / max) * (height - 16);
        return (
          <g key={i}>
            <rect
              x={i * w + w * 0.1} y={height - 14 - barH}
              width={w * 0.8} height={barH}
              rx={2} fill={color} opacity={0.85}
            />
            {i % Math.ceil(data.length / 6) === 0 && (
              <text x={i * w + w / 2} y={height - 2} textAnchor="middle"
                fill={COLORS.textMuted} style={{ fontSize: 6, fontFamily: 'inherit' }}>
                {d.label}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

// ── Sparkline ─────────────────────────────────────────────────────────────────
function SparkLine({ data, color, height = 50, filled = true }) {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data), min = Math.min(...data);
  const range = max - min || 1;
  const w = 100, h = height;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    return `${x},${y}`;
  });
  const pathD = `M ${pts.join(' L ')}`;
  const areaD = `M 0,${h} L ${pts.join(' L ')} L ${w},${h} Z`;
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      {filled && <path d={areaD} fill={color} opacity={0.12} />}
      <path d={pathD} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ── Radar chart ───────────────────────────────────────────────────────────────
function RadarChart({ data, size = 160, color = COLORS.cyan }) {
  const cx = size / 2, cy = size / 2;
  const r = size * 0.38;
  const n = data.length;
  const angle = (i) => (i / n) * 2 * Math.PI - Math.PI / 2;
  const gridLevels = [0.3, 0.6, 1.0];

  const labelPts = data.map((d, i) => ({
    x: cx + r * 1.28 * Math.cos(angle(i)),
    y: cy + r * 1.28 * Math.sin(angle(i)),
    label: d.label,
  }));

  const valuePts = data.map((d, i) => ({
    x: cx + r * d.value * Math.cos(angle(i)),
    y: cy + r * d.value * Math.sin(angle(i)),
  }));

  const polyPts = valuePts.map(p => `${p.x},${p.y}`).join(' ');

  return (
    <svg width={size} height={size}>
      {/* Grid lines */}
      {gridLevels.map((lvl, li) => {
        const gridPts = Array.from({ length: n }, (_, i) => ({
          x: cx + r * lvl * Math.cos(angle(i)),
          y: cy + r * lvl * Math.sin(angle(i)),
        })).map(p => `${p.x},${p.y}`).join(' ');
        return <polygon key={li} points={gridPts} fill="none"
          stroke={COLORS.border} strokeWidth={0.8} />;
      })}
      {/* Axis lines */}
      {data.map((_, i) => (
        <line key={i}
          x1={cx} y1={cy}
          x2={cx + r * Math.cos(angle(i))} y2={cy + r * Math.sin(angle(i))}
          stroke={COLORS.border} strokeWidth={0.8}
        />
      ))}
      {/* Value polygon */}
      <polygon points={polyPts} fill={color} fillOpacity={0.2} stroke={color} strokeWidth={1.5} />
      {/* Dots */}
      {valuePts.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={3} fill={color} />
      ))}
      {/* Labels */}
      {labelPts.map((p, i) => (
        <text key={i} x={p.x} y={p.y + 3} textAnchor="middle"
          fill={COLORS.textSecondary}
          style={{ fontSize: 9, fontFamily: 'inherit', fontWeight: 500 }}>
          {p.label}
        </text>
      ))}
    </svg>
  );
}

// ── Pace line chart ───────────────────────────────────────────────────────────
function PaceLineChart({ data, color = COLORS.cyan, height = 120 }) {
  const max = Math.max(...data.map(d => d.pace));
  const min = Math.min(...data.map(d => d.pace));
  const range = max - min || 1;
  const w = 300, h = height - 20;
  const pts = data.map((d, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((d.pace - min) / range) * (h - 8) - 4;
    return { x, y, ...d };
  });
  const polyline = pts.map(p => `${p.x},${p.y}`).join(' ');
  const areaPath = `M 0,${h} L ${polyline} L ${w},${h} Z`;

  return (
    <svg width="100%" height={height} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="xMidYMid meet">
      <defs>
        <linearGradient id="paceGrad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient>
      </defs>
      {/* Grid */}
      {[0.25, 0.5, 0.75, 1].map(lvl => (
        <line key={lvl} x1={0} y1={h * lvl} x2={w} y2={h * lvl}
          stroke={COLORS.borderFaint} strokeWidth={0.8} strokeDasharray="4,4" />
      ))}
      <path d={areaPath} fill="url(#paceGrad)" />
      <polyline points={polyline} fill="none" stroke={color}
        strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      {/* X axis labels */}
      {data.filter((_, i) => i % Math.ceil(data.length / 7) === 0).map((d, i, arr) => {
        const idx = data.indexOf(d);
        const x = (idx / (data.length - 1)) * w;
        return (
          <text key={i} x={x} y={height - 4} textAnchor="middle"
            fill={COLORS.textMuted} style={{ fontSize: 8, fontFamily: 'inherit' }}>
            {d.label}
          </text>
        );
      })}
    </svg>
  );
}

// ── Fitness/Fatigue line chart ────────────────────────────────────────────────
function FitnessFatigueChart({ height = 140 }) {
  const n = 60;
  const fitness = Array.from({ length: n }, (_, i) => 20 + 15 * Math.sin(i / 8) + i * 0.3 + Math.random() * 3);
  const fatigue = Array.from({ length: n }, (_, i) => 25 + 20 * Math.sin(i / 4 + 1) + Math.random() * 5);
  const form    = fitness.map((f, i) => f - fatigue[i]);

  const allVals = [...fitness, ...fatigue, ...form];
  const max = Math.max(...allVals), min = Math.min(...allVals);
  const range = max - min;
  const w = 300, h = height - 20;
  const toY = v => h - ((v - min) / range) * (h - 8) - 4;
  const line = (arr) => arr.map((v, i) => `${(i / (n-1)) * w},${toY(v)}`).join(' ');

  const months = ['Oct','Nov','Dec','Jan','Feb','Mar','Apr'];

  return (
    <svg width="100%" height={height} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="xMidYMid meet">
      {[0.25, 0.5, 0.75].map(lvl => (
        <line key={lvl} x1={0} y1={h * lvl} x2={w} y2={h * lvl}
          stroke={COLORS.borderFaint} strokeWidth={0.8} strokeDasharray="4,4"/>
      ))}
      <polyline points={line(fitness)} fill="none" stroke={COLORS.green} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"/>
      <polyline points={line(fatigue)} fill="none" stroke={COLORS.pink} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="4,3"/>
      <polyline points={line(form)} fill="none" stroke={COLORS.violet} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="2,3"/>
      {months.map((m, i) => (
        <text key={m} x={(i / (months.length - 1)) * w} y={height - 3}
          textAnchor="middle" fill={COLORS.textMuted}
          style={{ fontSize: 8, fontFamily: 'inherit' }}>{m}</text>
      ))}
    </svg>
  );
}

// Export to window for cross-file sharing
Object.assign(window, {
  COLORS, ACTIVITY_CFG, getActivityCfg,
  ActivityBadge, Card, SectionHeader, PillSelector, FilterChip,
  StatCard, BottomNav,
  DonutChart, ActivityCalendar, BarChart, SparkLine,
  RadarChart, PaceLineChart, FitnessFatigueChart,
});

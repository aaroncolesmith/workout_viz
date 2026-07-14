
// ── Mock data ──────────────────────────────────────────────────────────────────
const PERIOD_OPTIONS = ['All', '2Y', '1Y', '6M', '90D'];

const DASHBOARD_STATS = {
  '1Y': { activities: 497, distance: 1979, time: 410, avgPace: '8:28', avgHR: 120 },
  '6M': { activities: 243, distance: 982, time: 198, avgPace: '8:41', avgHR: 122 },
  '90D': { activities: 74, distance: 318, time: 61, avgPace: '8:19', avgHR: 118 },
  '2Y': { activities: 890, distance: 3820, time: 776, avgPace: '8:33', avgHR: 121 },
  'All': { activities: 3568, distance: 14820, time: 2940, avgPace: '8:45', avgHR: 123 },
};

const BREAKDOWN_DATA = [
  { label: 'Run',   value: 197, color: '#26c6f9' },
  { label: 'Walk',  value: 158, color: '#f59e0b' },
  { label: 'Weight',value: 57,  color: '#f472b6' },
  { label: 'Ride',  value: 37,  color: '#a78bfa' },
  { label: 'Hike',  value: 17,  color: '#34d399' },
  { label: 'Other', value: 31,  color: '#4a4a56' },
];

const RACE_PREDICTIONS = [
  { dist: '5K',           time: '22:54', pace: '7:22/mi', color: '#26c6f9' },
  { dist: '10K',          time: '47:46', pace: '7:41/mi', color: '#a78bfa' },
  { dist: 'Half Marathon',time: '1:59:06',pace: '9:05/mi', color: '#f59e0b' },
  { dist: 'Marathon',     time: '4:08:19',pace: '9:28/mi', color: '#34d399' },
];

const PERSONAL_RECORDS = {
  RUN: [
    { dist: '1 Mile',       time: '6:45',    pace: '6:45/mi', date: 'Aug 19, 2025' },
    { dist: '2 Miles',      time: '13:41',   pace: '6:50/mi', date: 'Aug 19, 2025' },
    { dist: '5K',           time: '21:31',   pace: '6:55/mi', date: 'Aug 19, 2025' },
    { dist: 'Half Marathon',time: '1:16:29', pace: '7:38/mi', date: 'Oct 5, 2025' },
    { dist: 'Marathon',     time: '3:25:28', pace: '7:50/mi', date: 'Oct 5, 2025' },
  ],
  BIKE: [
    { dist: '5 Miles',  time: '14:34',   pace: '2:54/mi', date: 'Aug 3, 2019' },
    { dist: '10 Miles', time: '31:13',   pace: '3:07/mi', date: 'Aug 3, 2019' },
    { dist: '25 Miles', time: '1:45:26', pace: '4:13/mi', date: 'Jul 24, 2019' },
    { dist: '50 Miles', time: '3:57:50', pace: '4:45/mi', date: 'Aug 3, 2019' },
  ],
};

const WEEKLY_MILEAGE = [
  { label: '11/10', value: 28 }, { label: '11/17', value: 35 }, { label: '11/24', value: 22 },
  { label: '12/01', value: 31 }, { label: '12/08', value: 38 }, { label: '12/15', value: 25 },
  { label: '12/22', value: 18 }, { label: '12/29', value: 32 }, { label: '1/05', value: 30 },
  { label: '1/12', value: 34 }, { label: '1/19', value: 28 }, { label: '1/26', value: 33 },
  { label: '2/02', value: 29 }, { label: '2/09', value: 31 }, { label: '2/16', value: 26 },
  { label: '2/23', value: 35 }, { label: '3/01', value: 27 }, { label: '3/08', value: 32 },
  { label: '3/15', value: 30 }, { label: '3/22', value: 38 }, { label: '3/29', value: 22 },
  { label: '4/05', value: 41 }, { label: '4/12', value: 46 }, { label: '4/19', value: 8 },
];

// ── Dashboard component ────────────────────────────────────────────────────────
function Dashboard() {
  const [period, setPeriod] = React.useState('1Y');
  const [ffPeriod, setFfPeriod] = React.useState('6 Mo');
  const [racePeriod, setRacePeriod] = React.useState('90 days');
  const stats = DASHBOARD_STATS[period] || DASHBOARD_STATS['1Y'];

  const scrollRef = React.useRef(null);

  return (
    <div ref={scrollRef} style={{
      position: 'absolute', top: 0, left: 0, right: 0, bottom: 82,
      overflowY: 'auto', overflowX: 'hidden',
      padding: '16px 16px 32px',
      WebkitOverflowScrolling: 'touch',
    }}>
      {/* ── Header ── */}
      <div style={{ marginBottom: 20, paddingTop: 4 }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', color: COLORS.textMuted, textTransform: 'uppercase', marginBottom: 4 }}>
          Performance Overview
        </div>
        <h1 style={{ fontSize: 32, fontWeight: 800, color: COLORS.textPrimary, margin: '0 0 14px', letterSpacing: '-0.04em' }}>
          {period === '1Y' ? 'Last Year' : period === '6M' ? 'Last 6 Months' : period === '90D' ? 'Last 90 Days' : period === '2Y' ? 'Last 2 Years' : 'All Time'}
        </h1>
        <PillSelector options={PERIOD_OPTIONS} value={period} onChange={setPeriod} />
      </div>

      {/* ── Stat cards ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
        <StatCard label="Activities" value={stats.activities} accentColor={COLORS.textMuted} />
        <StatCard label="Distance" value={stats.distance.toLocaleString()} unit="mi" accentColor={COLORS.violet} />
        <StatCard label="Time" value={stats.time} unit="hrs" accentColor={COLORS.green} />
        <StatCard label="Avg Pace" value={stats.avgPace} unit="/mi" accentColor={COLORS.cyan} />
      </div>
      <div style={{ marginBottom: 20 }}>
        <StatCard label="Avg Heart Rate" value={stats.avgHR} unit="bpm" accentColor={COLORS.pink} />
      </div>

      {/* ── Form card ── */}
      <Card style={{ padding: 18, marginBottom: 20, background: '#0d2016', border: `1px solid #1a4028` }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, flexShrink: 0 }}>
            <div style={{ width: 3, height: 44, borderRadius: 2, background: COLORS.green, marginRight: 4 }} />
            <div>
              <div style={{ fontSize: 38, fontWeight: 900, color: COLORS.green, letterSpacing: '-0.05em', lineHeight: 1 }}>100</div>
              <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', color: COLORS.green, opacity: 0.8, marginTop: 2 }}>PEAK FORM</div>
            </div>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: COLORS.textPrimary, marginBottom: 4 }}>Today's Recommendation</div>
            <div style={{ fontSize: 12, color: COLORS.textSecondary, lineHeight: 1.5 }}>Peak form — consider a race or time trial</div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 24, marginTop: 16, paddingTop: 14, borderTop: `1px solid #1a4028` }}>
          {[
            { label: 'CTL 42D', value: '79.9', color: COLORS.cyan },
            { label: 'ATL 7D', value: '50.3', color: COLORS.amber },
            { label: 'TSB', value: '+23.2', color: COLORS.green },
          ].map(item => (
            <div key={item.label}>
              <div style={{ fontSize: 18, fontWeight: 700, color: item.color, letterSpacing: '-0.03em' }}>{item.value}</div>
              <div style={{ fontSize: 10, color: COLORS.textMuted, fontWeight: 600, letterSpacing: '0.06em', marginTop: 2 }}>{item.label}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* ── Activity Calendar ── */}
      <Card style={{ padding: 16, marginBottom: 12 }}>
        <SectionHeader label="Activity Calendar" right="Last 6 months" />
        <ActivityCalendar weeks={26} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end', marginTop: 10 }}>
          <span style={{ fontSize: 10, color: COLORS.textMuted }}>Less</span>
          {['#1a1a20','#0d3320','#0f5a30','#16a34a','#22c55e'].map((c,i) => (
            <div key={i} style={{ width: 10, height: 10, borderRadius: 2, background: c }} />
          ))}
          <span style={{ fontSize: 10, color: COLORS.textMuted }}>More</span>
        </div>
      </Card>

      {/* ── Activity Breakdown ── */}
      <Card style={{ padding: 16, marginBottom: 12 }}>
        <SectionHeader label="Activity Breakdown" right={`${stats.activities} total`} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <DonutChart data={BREAKDOWN_DATA} size={150} />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 7 }}>
            {BREAKDOWN_DATA.map(d => {
              const pct = (d.value / BREAKDOWN_DATA.reduce((s,x) => s+x.value, 0) * 100).toFixed(1);
              return (
                <div key={d.label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: d.color, flexShrink: 0 }} />
                  <span style={{ flex: 1, fontSize: 12, color: COLORS.textSecondary }}>{d.label}</span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: d.color }}>{pct}%</span>
                </div>
              );
            })}
          </div>
        </div>
      </Card>

      {/* ── Fitness & Fatigue ── */}
      <Card style={{ padding: 16, marginBottom: 12 }}>
        <SectionHeader label="Fitness & Fatigue" />
        <div style={{ fontSize: 11, color: COLORS.textMuted, marginBottom: 10 }}>Acute (ATL) vs Chronic (CTL) Training Load</div>
        <div style={{ display: 'flex', gap: 14, marginBottom: 12 }}>
          {[{label:'FITNESS',color:COLORS.green},{label:'FATIGUE',color:COLORS.pink},{label:'FORM',color:COLORS.violet}].map(item => (
            <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ width: 16, height: 2, background: item.color, borderRadius: 1 }} />
              <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.06em', color: COLORS.textMuted }}>{item.label}</span>
            </div>
          ))}
        </div>
        <PillSelector
          options={['3 Mo','6 Mo','1 Yr','2 Yr','All']}
          value={ffPeriod}
          onChange={setFfPeriod}
          style={{ marginBottom: 12, flexWrap: 'wrap' }}
        />
        <FitnessFatigueChart height={140} />
        <div style={{ fontSize: 10, color: COLORS.textMuted, marginTop: 8 }}>
          TRIMP model · Max HR 178.1 bpm · Resting HR 60 bpm
        </div>
      </Card>

      {/* ── Race Predictor ── */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: COLORS.textPrimary }}>Race Predictor</span>
          <div style={{ display: 'flex', gap: 6 }}>
            {['30 days','60 days','90 days','6 months'].map(opt => (
              <button key={opt} onClick={() => setRacePeriod(opt)} style={{
                padding: '4px 8px', borderRadius: 12,
                background: racePeriod === opt ? COLORS.cyan : 'transparent',
                border: `1px solid ${racePeriod === opt ? COLORS.cyan : COLORS.border}`,
                color: racePeriod === opt ? '#000' : COLORS.textSecondary,
                fontSize: 10, fontWeight: 600, cursor: 'pointer',
              }}>{opt}</button>
            ))}
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {RACE_PREDICTIONS.map(r => (
            <Card key={r.dist} style={{ padding: '14px 14px 12px' }}>
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', color: COLORS.textMuted, textTransform: 'uppercase', marginBottom: 6 }}>{r.dist}</div>
              <div style={{ fontSize: 22, fontWeight: 800, color: COLORS.textPrimary, letterSpacing: '-0.04em', marginBottom: 2 }}>{r.time}</div>
              <div style={{ fontSize: 11, color: COLORS.textSecondary, marginBottom: 10 }}>{r.pace}</div>
              <div style={{ height: 2, borderRadius: 2, background: COLORS.borderFaint }}>
                <div style={{ height: 2, borderRadius: 2, width: '65%', background: r.color }} />
              </div>
            </Card>
          ))}
        </div>
      </div>

      {/* ── Personal Records ── */}
      <Card style={{ padding: 16, marginBottom: 12 }}>
        <SectionHeader label="Personal Records" />
        {[
          { sport: 'RUN', color: COLORS.cyan, records: PERSONAL_RECORDS.RUN },
          { sport: 'BIKE', color: COLORS.violet, records: PERSONAL_RECORDS.BIKE },
        ].map(({ sport, color, records }) => (
          <div key={sport} style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', color, marginBottom: 10 }}>{sport}</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {records.map(r => (
                <div key={r.dist} style={{
                  background: COLORS.cardAlt, borderRadius: 10,
                  border: `1px solid ${COLORS.border}`, padding: '10px 12px',
                }}>
                  <div style={{ fontSize: 10, color: COLORS.textMuted, fontWeight: 600, marginBottom: 4 }}>{r.dist}</div>
                  <div style={{ fontSize: 18, fontWeight: 800, color, letterSpacing: '-0.04em', marginBottom: 2 }}>{r.time}</div>
                  <div style={{ fontSize: 10, color: COLORS.textMuted }}>{r.date}</div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </Card>

      {/* ── Weekly Mileage ── */}
      <Card style={{ padding: 16, marginBottom: 12 }}>
        <SectionHeader label="Weekly Mileage" right="Last 6 months" />
        <BarChart data={WEEKLY_MILEAGE} color={COLORS.violet} height={90} />
      </Card>
    </div>
  );
}

window.Dashboard = Dashboard;

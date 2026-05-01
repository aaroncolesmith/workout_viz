import { useState, useRef, useEffect } from 'react';
import { BrowserRouter, Routes, Route, NavLink, useLocation, useNavigate } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Activities from './pages/Activities';
import ActivityDetail from './pages/ActivityDetail';
import SimilarityExplorer from './pages/SimilarityExplorer';
import TrainingBlocksPage from './pages/TrainingBlocksPage';
import RoutesPage from './pages/RoutesPage';
import Settings from './pages/Settings';
import AuthCallback from './pages/AuthCallback';
import ErrorBoundary from './components/ErrorBoundary';

const ADVANCED_ROUTES = ['/blocks', '/routes', '/similarity', '/settings'];

const ADVANCED_ITEMS = [
  { to: '/blocks',     label: 'Blocks',     color: '#26c6f9' },
  { to: '/routes',     label: 'Routes',     color: '#a78bfa' },
  { to: '/similarity', label: 'Similarity', color: '#f472b6' },
  { to: '/settings',   label: 'Settings',   color: '#f59e0b' },
];

function IconDashboard() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  );
}

function IconActivities() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <polyline points="2,12 6,7 9,13 13,5 17,15 20,10 22,12" />
    </svg>
  );
}

function IconAdvanced() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3" y="12" width="4" height="9" rx="1" />
      <rect x="10" y="7" width="4" height="14" rx="1" />
      <rect x="17" y="3" width="4" height="18" rx="1" />
    </svg>
  );
}

function AdvancedTab() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const ref = useRef(null);
  const isActive = ADVANCED_ROUTES.some(p => location.pathname.startsWith(p));

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const go = (path) => { setOpen(false); navigate(path); };

  return (
    <div ref={ref} style={{ flex: 1, position: 'relative' }}>
      <button
        className={`bottom-nav-tab ${isActive ? 'active' : ''}`}
        style={{ width: '100%', height: '100%' }}
        onClick={() => setOpen(v => !v)}
        aria-label="Advanced"
      >
        <IconAdvanced />
        <span className="bottom-nav-label">Advanced</span>
      </button>

      {open && (
        <div className="bottom-nav-popup">
          {ADVANCED_ITEMS.map(item => {
            const active = location.pathname.startsWith(item.to);
            return (
              <button
                key={item.to}
                className={`bottom-nav-popup-item ${active ? 'active' : ''}`}
                onClick={() => go(item.to)}
              >
                <span
                  className="bottom-nav-popup-dot"
                  style={{ background: item.color }}
                />
                {item.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function BottomNav() {
  return (
    <nav className="bottom-nav">
      <NavLink
        to="/"
        end
        className={({ isActive }) => `bottom-nav-tab ${isActive ? 'active' : ''}`}
        aria-label="Dashboard"
      >
        <IconDashboard />
        <span className="bottom-nav-label">Dashboard</span>
      </NavLink>
      <NavLink
        to="/activities"
        className={({ isActive }) => `bottom-nav-tab ${isActive ? 'active' : ''}`}
        aria-label="Activities"
      >
        <IconActivities />
        <span className="bottom-nav-label">Activities</span>
      </NavLink>
      <AdvancedTab />
    </nav>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        <main className="page-container">
          <Routes>
            <Route path="/" element={
              <ErrorBoundary label="Dashboard">
                <Dashboard />
              </ErrorBoundary>
            } />
            <Route path="/activities" element={
              <ErrorBoundary label="Activities">
                <Activities />
              </ErrorBoundary>
            } />
            <Route path="/activity/:id" element={
              <ErrorBoundary label="Activity Detail">
                <ActivityDetail />
              </ErrorBoundary>
            } />
            <Route path="/blocks" element={
              <ErrorBoundary label="Training Blocks">
                <TrainingBlocksPage />
              </ErrorBoundary>
            } />
            <Route path="/routes" element={
              <ErrorBoundary label="Routes">
                <RoutesPage />
              </ErrorBoundary>
            } />
            <Route path="/similarity" element={
              <ErrorBoundary label="Similarity Explorer">
                <SimilarityExplorer />
              </ErrorBoundary>
            } />
            <Route path="/settings" element={
              <ErrorBoundary label="Settings">
                <Settings />
              </ErrorBoundary>
            } />
            <Route path="/auth/callback" element={<AuthCallback />} />
          </Routes>
        </main>
        <BottomNav />
      </div>
    </BrowserRouter>
  );
}

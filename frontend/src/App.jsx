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

function AdvancedMenu() {
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
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(v => !v)}
        className={isActive ? 'active' : ''}
        style={{
          padding: 'var(--space-sm) var(--space-lg)',
          fontFamily: 'var(--font-body)',
          fontSize: '0.72rem',
          fontWeight: 600,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
          background: 'transparent',
          border: 'none',
          borderBottom: `2px solid ${isActive ? '#34d399' : 'transparent'}`,
          cursor: 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
        }}
      >
        Advanced
        <span style={{ fontSize: '0.6rem', opacity: 0.7 }}>▼</span>
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            right: 0,
            minWidth: 180,
            background: 'rgba(28, 27, 27, 0.98)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: 8,
            padding: 6,
            boxShadow: '0 12px 32px rgba(0,0,0,0.4)',
            backdropFilter: 'blur(20px)',
            zIndex: 200,
          }}
        >
          {[
            { to: '/blocks', label: 'Blocks' },
            { to: '/routes', label: 'Routes' },
            { to: '/similarity', label: 'Similarity' },
            { to: '/settings', label: 'Settings' },
          ].map(item => {
            const active = location.pathname.startsWith(item.to);
            return (
              <button
                key={item.to}
                onClick={() => go(item.to)}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '8px 12px',
                  fontFamily: 'var(--font-body)',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  letterSpacing: '0.04em',
                  color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
                  background: active ? 'rgba(255,255,255,0.05)' : 'transparent',
                  border: 'none',
                  borderRadius: 4,
                  cursor: 'pointer',
                }}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        <header className="app-header">
          <NavLink to="/" className="app-logo">
            KINETICA OBSIDIAN
          </NavLink>
          <nav className="app-nav">
            <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''}>
              Dashboard
            </NavLink>
            <NavLink to="/activities" className={({ isActive }) => isActive ? 'active' : ''}>
              Activities
            </NavLink>
            <AdvancedMenu />
          </nav>
          <div />
        </header>

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
      </div>
    </BrowserRouter>
  );
}

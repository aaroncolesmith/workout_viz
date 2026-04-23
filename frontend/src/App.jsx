import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import ActivityDetail from './pages/ActivityDetail';
import SimilarityExplorer from './pages/SimilarityExplorer';
import TrainingBlocksPage from './pages/TrainingBlocksPage';
import RoutesPage from './pages/RoutesPage';
import AuthCallback from './pages/AuthCallback';
import SyncPanel from './components/SyncPanel';
import ErrorBoundary from './components/ErrorBoundary';

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
            <NavLink to="/blocks" className={({ isActive }) => isActive ? 'active' : ''}>
              Blocks
            </NavLink>
            <NavLink to="/routes" className={({ isActive }) => isActive ? 'active' : ''}>
              Routes
            </NavLink>
            <NavLink to="/similarity" className={({ isActive }) => isActive ? 'active' : ''}>
              Similarity
            </NavLink>
          </nav>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-md)' }}>
            <SyncPanel />
          </div>
        </header>

        <main className="page-container">
          <Routes>
            <Route path="/" element={
              <ErrorBoundary label="Dashboard">
                <Dashboard />
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
            <Route path="/auth/callback" element={<AuthCallback />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}


import React from 'react';

/**
 * ErrorBoundary — Catches unhandled render errors and shows a graceful fallback.
 * Wrap page-level routes and chart components with this to prevent one broken
 * component from taking down the whole UI.
 *
 * Usage:
 *   <ErrorBoundary>
 *     <MyChart />
 *   </ErrorBoundary>
 *
 *   <ErrorBoundary label="Dashboard">
 *     <Dashboard />
 *   </ErrorBoundary>
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // Could send to a logging service here in the future
    console.error('[ErrorBoundary] Caught render error:', error, info);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    const { hasError, error } = this.state;
    const { children, label = 'This section', compact = false } = this.props;

    if (!hasError) return children;

    if (compact) {
      // For chart-level wrappers — compact inline fallback
      return (
        <div style={{
          height: '100%',
          minHeight: 120,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          border: '1px dashed rgba(239, 68, 68, 0.3)',
          borderRadius: 12,
          color: 'var(--text-muted)',
          padding: 16,
          background: 'rgba(239, 68, 68, 0.03)',
        }}>
          <span style={{ fontSize: '1.25rem' }}>!</span>
          <span style={{ fontSize: '0.75rem' }}>Chart failed to render</span>
          <button
            onClick={this.handleRetry}
            style={{
              fontSize: '0.7rem',
              padding: '3px 10px',
              borderRadius: 20,
              border: '1px solid rgba(239, 68, 68, 0.3)',
              background: 'transparent',
              color: '#f87171',
              cursor: 'pointer',
            }}
          >
            Retry
          </button>
        </div>
      );
    }

    // For page-level wrappers — full-panel fallback
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '60vh',
        gap: 16,
        color: 'var(--text-muted)',
        padding: 32,
      }}>
        <div style={{
          width: 56,
          height: 56,
          borderRadius: '50%',
          background: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.2)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '1.5rem',
        }}>
          !
        </div>
        <div style={{ textAlign: 'center' }}>
          <h3 style={{ color: 'var(--text-primary)', fontSize: '1.1rem', fontWeight: 700, marginBottom: 6 }}>
            {label} failed to load
          </h3>
          <p style={{ fontSize: '0.8rem', maxWidth: 360, lineHeight: 1.6 }}>
            An unexpected error occurred. Your data is safe — this is a display issue.
          </p>
          {error?.message && (
            <code style={{
              display: 'block',
              marginTop: 12,
              padding: '6px 12px',
              borderRadius: 6,
              background: 'rgba(239, 68, 68, 0.05)',
              border: '1px solid rgba(239, 68, 68, 0.15)',
              fontSize: '0.7rem',
              color: '#f87171',
              fontFamily: 'var(--font-mono)',
              maxWidth: 400,
              wordBreak: 'break-word',
            }}>
              {error.message}
            </code>
          )}
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button
            onClick={this.handleRetry}
            className="filter-chip active"
            style={{ fontSize: '0.8rem' }}
          >
            Try Again
          </button>
          <button
            onClick={() => window.location.href = '/'}
            className="filter-chip"
            style={{ fontSize: '0.8rem' }}
          >
            Go to Dashboard
          </button>
        </div>
      </div>
    );
  }
}

import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

export default function AuthCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const code = searchParams.get('code');
    if (!code) {
      setError('No authorization code found in URL');
      setLoading(false);
      return;
    }

    // Exchange code for token via backend
    fetch(`/api/auth/strava/callback?code=${code}`, {
      method: 'POST',
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'authenticated') {
          navigate('/', { state: { message: 'Successfully connected to Strava!' } });
        } else {
          setError(data.detail || 'Authentication failed');
        }
      })
      .catch(err => {
        setError(err.message);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [searchParams, navigate]);

  return (
    <div className="loading-state" style={{ height: '80vh' }}>
      {loading ? (
        <>
          <div className="loading-spinner" />
          <span>Connecting your Strava account...</span>
        </>
      ) : error ? (
        <div style={{ textAlign: 'center' }}>
          <h2 style={{ color: '#f87171', marginBottom: 'var(--space-md)' }}>Authentication Error</h2>
          <p style={{ color: 'var(--text-secondary)', marginBottom: 'var(--space-lg)' }}>{error}</p>
          <button className="filter-chip active" onClick={() => navigate('/')}>
            Return to Dashboard
          </button>
        </div>
      ) : (
        <span>Redirecting...</span>
      )}
    </div>
  );
}

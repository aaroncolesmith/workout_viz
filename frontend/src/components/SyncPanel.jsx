import { useState, useEffect, useRef, useCallback } from 'react';
import {
  getAuthStatus, getAuthUrl, syncActivities, getSyncStatus,
  startSplitsBackfill, getSplitsSyncStatus,
  importAppleHealth, getAppleHealthImportStatus,
} from '../utils/api';

const POLL_INTERVAL_MS = 1500;

export default function SyncPanel({ onSyncComplete }) {
  const [authStatus, setAuthStatus]   = useState(null);
  const [syncState, setSyncState]     = useState(null);
  const [splitsState, setSplitsState] = useState(null);
  const [ahState, setAhState]         = useState(null);

  const pollRef       = useRef(null);
  const splitsPollRef = useRef(null);
  const ahPollRef     = useRef(null);
  const fileInputRef  = useRef(null);

  // ── Strava sync polling ────────────────────────────────────────────────
  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      try {
        const state = await getSyncStatus();
        setSyncState(state);
        if (state.status !== 'running') {
          stopPolling();
          if (state.status === 'done' && state.added > 0) {
            setTimeout(() => {
              if (onSyncComplete) onSyncComplete();
              else window.location.reload();
            }, 2000);
          }
        }
      } catch { stopPolling(); }
    }, POLL_INTERVAL_MS);
  }, [onSyncComplete, stopPolling]);

  // ── Splits polling ─────────────────────────────────────────────────────
  const stopSplitsPolling = useCallback(() => {
    if (splitsPollRef.current) { clearInterval(splitsPollRef.current); splitsPollRef.current = null; }
  }, []);

  const startSplitsPolling = useCallback(() => {
    if (splitsPollRef.current) return;
    splitsPollRef.current = setInterval(async () => {
      try {
        const state = await getSplitsSyncStatus();
        setSplitsState(state);
        if (state.status !== 'running') stopSplitsPolling();
      } catch { stopSplitsPolling(); }
    }, POLL_INTERVAL_MS);
  }, [stopSplitsPolling]);

  // ── Apple Health polling ───────────────────────────────────────────────
  const stopAhPolling = useCallback(() => {
    if (ahPollRef.current) { clearInterval(ahPollRef.current); ahPollRef.current = null; }
  }, []);

  const startAhPolling = useCallback(() => {
    if (ahPollRef.current) return;
    ahPollRef.current = setInterval(async () => {
      try {
        const state = await getAppleHealthImportStatus();
        setAhState(state);
        if (state.status !== 'running') {
          stopAhPolling();
          if (state.status === 'done' && state.added > 0) {
            setTimeout(() => window.location.reload(), 2000);
          }
        }
      } catch { stopAhPolling(); }
    }, POLL_INTERVAL_MS);
  }, [stopAhPolling]);

  // ── Mount: check if any job is already running ────────────────────────
  useEffect(() => {
    getAuthStatus().then(setAuthStatus).catch(console.error);
    getSyncStatus().then(state => {
      if (state.status === 'running') { setSyncState(state); startPolling(); }
    }).catch(() => {});
    getSplitsSyncStatus().then(state => {
      if (state.status === 'running') { setSplitsState(state); startSplitsPolling(); }
    }).catch(() => {});
    getAppleHealthImportStatus().then(state => {
      if (state.status === 'running') { setAhState(state); startAhPolling(); }
    }).catch(() => {});
    return () => { stopPolling(); stopSplitsPolling(); stopAhPolling(); };
  }, [startPolling, startSplitsPolling, startAhPolling, stopPolling, stopSplitsPolling, stopAhPolling]);

  // ── Handlers ───────────────────────────────────────────────────────────
  const handleConnect = () => {
    getAuthUrl().then(res => { if (res.url) window.location.href = res.url; }).catch(console.error);
  };

  const handleSync = async (deep = false) => {
    try {
      await syncActivities(deep);
      setSyncState({ status: 'running', deep, fetched: 0, added: 0, message: 'Starting…' });
      startPolling();
    } catch (err) {
      setSyncState({ status: 'error', message: err.message });
    }
  };

  const handleSyncSplits = async () => {
    try {
      await startSplitsBackfill();
      setSplitsState({ status: 'running', total: 0, completed: 0, message: 'Starting…' });
      startSplitsPolling();
    } catch (err) {
      setSplitsState({ status: 'error', message: err.message });
    }
  };

  const handleAppleHealthFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    try {
      setAhState({ status: 'running', message: 'Uploading…', parsed: 0, added: 0, skipped: 0 });
      await importAppleHealth(file);
      startAhPolling();
    } catch (err) {
      setAhState({ status: 'error', message: err.message });
    }
  };

  if (!authStatus) return null;

  // ── Derived display state ──────────────────────────────────────────────
  const isRunning = syncState?.status === 'running';
  const isDone    = syncState?.status === 'done';
  const isError   = syncState?.status === 'error';

  const progressLabel = isRunning
    ? (syncState.fetched > 0 ? `Fetched ${syncState.fetched}…` : 'Syncing…')
    : isDone
      ? (syncState.added > 0 ? `✓ Added ${syncState.added}` : '✓ Up to date')
      : isError ? syncState.message : null;

  const isSplitsRunning = splitsState?.status === 'running';
  const isSplitsDone    = splitsState?.status === 'done';
  const isSplitsError   = splitsState?.status === 'error';
  const splitsTotal     = splitsState?.total || 0;
  const splitsCompleted = splitsState?.completed || 0;
  const splitsSkipped   = splitsState?.skipped || 0;
  const splitsFailed    = splitsState?.failed || 0;
  const splitsEffective = splitsTotal - splitsSkipped - splitsFailed;
  const splitsPct       = splitsTotal > 0 ? Math.round((splitsCompleted / splitsTotal) * 100) : 0;

  const splitsLabel = isSplitsRunning
    ? (splitsTotal > 0 ? `Splits ${splitsCompleted}/${splitsEffective > 0 ? splitsEffective : splitsTotal}` : 'Fetching splits…')
    : isSplitsDone
      ? `✓ ${splitsState.completed} synced${splitsSkipped > 0 ? `, ${splitsSkipped} skipped` : ''}`
      : isSplitsError ? splitsState.message : null;

  const isAhRunning = ahState?.status === 'running';
  const isAhDone    = ahState?.status === 'done';
  const isAhError   = ahState?.status === 'error';
  const ahLabel     = isAhRunning
    ? (ahState.message || 'Importing…')
    : isAhDone
      ? `✓ ${ahState.added} added${ahState.skipped > 0 ? `, ${ahState.skipped} skipped` : ''}`
      : isAhError ? (ahState.message || 'Import failed') : null;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-md)' }}>
      {authStatus.authenticated ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)' }}>

          {/* Strava sync status */}
          {syncState && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 3 }}>
              <span style={{
                fontSize: '0.75rem',
                color: isError ? '#f87171' : isDone ? '#34d399' : '#38bdf8',
                background: 'rgba(255,255,255,0.05)',
                padding: '3px 10px',
                borderRadius: 20,
                whiteSpace: 'nowrap',
              }}>
                {progressLabel}
              </span>
              {isRunning && (
                <div style={{ width: 120, height: 2, background: 'rgba(255,255,255,0.1)', borderRadius: 1, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    background: 'linear-gradient(90deg, #38bdf8, #818cf8)',
                    borderRadius: 1,
                    animation: 'progress-indeterminate 1.5s ease-in-out infinite',
                  }} />
                </div>
              )}
            </div>
          )}

          {/* Gaps warning */}
          {authStatus.strava_total_count && authStatus.strava_total_count > authStatus.local_count && !syncState && (
            <span style={{
              fontSize: '0.68rem',
              fontFamily: "'Inter', sans-serif",
              fontWeight: 600,
              color: 'rgba(251,191,36,0.7)',
              border: '1px solid rgba(251,191,36,0.2)',
              padding: '4px 10px',
              borderRadius: 4,
              background: 'transparent',
              letterSpacing: '0.04em',
            }} title={`${authStatus.strava_total_count - authStatus.local_count} activities missing. Deep sync recommended.`}>
              Gaps detected
            </span>
          )}

          {/* Apple Health import progress */}
          {ahLabel && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 3 }}>
              <span style={{
                fontSize: '0.75rem',
                color: isAhError ? '#f87171' : isAhDone ? '#34d399' : '#fb923c',
                background: 'rgba(255,255,255,0.05)',
                padding: '3px 10px',
                borderRadius: 20,
                whiteSpace: 'nowrap',
                maxWidth: 240,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}>
                {ahLabel}
              </span>
              {isAhRunning && (
                <div style={{ width: 120, height: 2, background: 'rgba(255,255,255,0.1)', borderRadius: 1, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    background: 'linear-gradient(90deg, #fb923c, #f97316)',
                    borderRadius: 1,
                    animation: 'progress-indeterminate 1.5s ease-in-out infinite',
                  }} />
                </div>
              )}
            </div>
          )}

          {/* Splits progress */}
          {splitsLabel && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 3 }}>
              <span style={{
                fontSize: '0.75rem',
                color: isSplitsError ? '#f87171' : isSplitsDone ? '#34d399' : '#a78bfa',
                background: 'rgba(255,255,255,0.05)',
                padding: '3px 10px',
                borderRadius: 20,
                whiteSpace: 'nowrap',
              }}>
                {splitsLabel}
              </span>
              {isSplitsRunning && splitsTotal > 0 && (
                <div style={{ width: 120, height: 2, background: 'rgba(255,255,255,0.1)', borderRadius: 1, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: `${splitsPct}%`,
                    background: 'linear-gradient(90deg, #a78bfa, #818cf8)',
                    borderRadius: 1,
                    transition: 'width 0.4s ease',
                  }} />
                </div>
              )}
            </div>
          )}

          {/* Sync buttons */}
          <div style={{ display: 'flex', gap: 1 }}>
            <button
              onClick={() => handleSync(false)}
              disabled={isRunning}
              style={{
                background: 'transparent',
                border: '1px solid rgba(252,76,2,0.35)',
                borderRight: 'none',
                color: isRunning ? 'rgba(252,76,2,0.45)' : 'rgba(252,76,2,0.85)',
                fontFamily: "'Inter', sans-serif",
                fontWeight: 600,
                fontSize: '0.72rem',
                letterSpacing: '0.04em',
                padding: '5px 12px',
                borderRadius: '6px 0 0 6px',
                cursor: isRunning ? 'not-allowed' : 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {isRunning ? 'Syncing…' : 'Sync'}
            </button>
            <button
              onClick={() => handleSync(true)}
              disabled={isRunning}
              title="Deep Sync — scans entire Strava history for gaps"
              style={{
                background: 'transparent',
                border: '1px solid rgba(252,76,2,0.2)',
                color: isRunning ? 'rgba(252,76,2,0.3)' : 'rgba(252,76,2,0.6)',
                fontFamily: "'Inter', sans-serif",
                fontWeight: 500,
                fontSize: '0.68rem',
                letterSpacing: '0.04em',
                padding: '5px 10px',
                borderRadius: '0 6px 6px 0',
                cursor: isRunning ? 'not-allowed' : 'pointer',
                transition: 'all 0.15s',
              }}
            >
              Deep
            </button>
          </div>

          {/* Splits backfill button */}
          <button
            onClick={handleSyncSplits}
            disabled={isSplitsRunning}
            title="Fetch splits for all activities that don't have them yet (~1 req/sec)"
            style={{
              background: 'transparent',
              border: '1px solid rgba(167,139,250,0.3)',
              color: isSplitsRunning ? 'rgba(167,139,250,0.35)' : 'rgba(167,139,250,0.75)',
              fontFamily: "'Inter', sans-serif",
              fontWeight: 500,
              fontSize: '0.68rem',
              letterSpacing: '0.04em',
              padding: '5px 12px',
              borderRadius: 6,
              cursor: isSplitsRunning ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s',
            }}
          >
            {isSplitsRunning ? 'Syncing Splits…' : 'Sync Splits'}
          </button>

          {/* Apple Health import */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip,.xml"
            style={{ display: 'none' }}
            onChange={handleAppleHealthFile}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isAhRunning}
            title="Import Apple Health export.zip — includes workouts not tracked in Strava (strength, swim, etc.)"
            style={{
              background: 'transparent',
              border: '1px solid rgba(251,146,60,0.3)',
              color: isAhRunning ? 'rgba(251,146,60,0.35)' : 'rgba(251,146,60,0.75)',
              fontFamily: "'Inter', sans-serif",
              fontWeight: 500,
              fontSize: '0.68rem',
              letterSpacing: '0.04em',
              padding: '5px 12px',
              borderRadius: 6,
              cursor: isAhRunning ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s',
            }}
          >
            {isAhRunning ? 'Importing…' : 'Apple Health'}
          </button>
        </div>
      ) : (
        <button
          onClick={handleConnect}
          style={{
            background: 'transparent',
            border: '1px solid rgba(252,76,2,0.4)',
            color: 'rgba(252,76,2,0.85)',
            fontFamily: "'Inter', sans-serif",
            fontWeight: 600,
            fontSize: '0.72rem',
            letterSpacing: '0.04em',
            padding: '6px 16px',
            borderRadius: 6,
            cursor: 'pointer',
          }}
        >
          Connect Strava
        </button>
      )}
    </div>
  );
}

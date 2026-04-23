import { createContext, createElement, useCallback, useContext, useMemo, useRef, useState } from 'react';
import { getActivities, getOverview, getTrends } from '../utils/api';

const AppStateContext = createContext(null);

function buildCacheKey(params = {}) {
  const entries = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .sort(([a], [b]) => a.localeCompare(b));
  return JSON.stringify(entries);
}

const EMPTY_ARRAY = [];

function sanitizeComparisonIds(ids) {
  return Array.from(
    new Set(
      (ids || [])
        .map((value) => Number(value))
        .filter((value) => Number.isFinite(value) && value > 0)
    )
  ).slice(-5);
}

export function AppStateProvider({ children }) {
  const [overviewState, setOverviewState] = useState({
    data: null,
    loading: false,
    error: null,
    lastFetched: null,
  });
  const [activityCache, setActivityCache] = useState({});
  const [trendCache, setTrendCache] = useState({});
  const [comparisonSelections, setComparisonSelections] = useState({});
  const inFlightRef = useRef({
    overview: null,
    activities: new Map(),
    trends: new Map(),
  });

  const ensureOverview = useCallback(async ({ force = false } = {}) => {
    if (!force && overviewState.data) return overviewState.data;
    if (!force && inFlightRef.current.overview) return inFlightRef.current.overview;

    setOverviewState((prev) => ({ ...prev, loading: true, error: null }));

    const request = getOverview()
      .then((data) => {
        setOverviewState({
          data,
          loading: false,
          error: null,
          lastFetched: Date.now(),
        });
        inFlightRef.current.overview = null;
        return data;
      })
      .catch((error) => {
        setOverviewState((prev) => ({
          ...prev,
          loading: false,
          error,
        }));
        inFlightRef.current.overview = null;
        throw error;
      });

    inFlightRef.current.overview = request;
    return request;
  }, [overviewState.data]);

  const ensureActivities = useCallback(async (params = {}, { force = false } = {}) => {
    const key = buildCacheKey(params);
    const cached = activityCache[key];
    if (!force && cached?.data) return cached.data;
    if (!force && inFlightRef.current.activities.has(key)) {
      return inFlightRef.current.activities.get(key);
    }

    setActivityCache((prev) => ({
      ...prev,
      [key]: { ...(prev[key] || {}), params, loading: true, error: null },
    }));

    const request = getActivities(params)
      .then((data) => {
        setActivityCache((prev) => ({
          ...prev,
          [key]: {
            data,
            params,
            loading: false,
            error: null,
            lastFetched: Date.now(),
          },
        }));
        inFlightRef.current.activities.delete(key);
        return data;
      })
      .catch((error) => {
        setActivityCache((prev) => ({
          ...prev,
          [key]: {
            ...(prev[key] || {}),
            params,
            loading: false,
            error,
          },
        }));
        inFlightRef.current.activities.delete(key);
        throw error;
      });

    inFlightRef.current.activities.set(key, request);
    return request;
  }, [activityCache]);

  const ensureTrends = useCallback(async (params = {}, { force = false } = {}) => {
    const key = buildCacheKey(params);
    const cached = trendCache[key];
    if (!force && cached?.data) return cached.data;
    if (!force && inFlightRef.current.trends.has(key)) {
      return inFlightRef.current.trends.get(key);
    }

    setTrendCache((prev) => ({
      ...prev,
      [key]: { ...(prev[key] || {}), params, loading: true, error: null },
    }));

    const request = getTrends(params)
      .then((data) => {
        setTrendCache((prev) => ({
          ...prev,
          [key]: {
            data,
            params,
            loading: false,
            error: null,
            lastFetched: Date.now(),
          },
        }));
        inFlightRef.current.trends.delete(key);
        return data;
      })
      .catch((error) => {
        setTrendCache((prev) => ({
          ...prev,
          [key]: {
            ...(prev[key] || {}),
            params,
            loading: false,
            error,
          },
        }));
        inFlightRef.current.trends.delete(key);
        throw error;
      });

    inFlightRef.current.trends.set(key, request);
    return request;
  }, [trendCache]);

  const getActivitiesState = useCallback((params = {}) => {
    const key = buildCacheKey(params);
    return activityCache[key] || { data: null, params, loading: false, error: null };
  }, [activityCache]);

  const getTrendsState = useCallback((params = {}) => {
    const key = buildCacheKey(params);
    return trendCache[key] || { data: null, params, loading: false, error: null };
  }, [trendCache]);

  const setComparisonIds = useCallback((activityId, nextOrUpdater) => {
    const key = String(activityId);
    setComparisonSelections((prev) => {
      const current = prev[key] || EMPTY_ARRAY;
      const nextValue = typeof nextOrUpdater === 'function'
        ? nextOrUpdater(current)
        : nextOrUpdater;
      const nextIds = sanitizeComparisonIds(nextValue);

      // Deep equal check for arrays
      if (
        nextIds.length === current.length &&
        nextIds.every((id, idx) => id === current[idx])
      ) {
        return prev;
      }

      if (nextIds.length === 0) {
        if (!(key in prev)) return prev;
        const updated = { ...prev };
        delete updated[key];
        return updated;
      }
      return { ...prev, [key]: nextIds };
    });
  }, []);

  const clearComparisonIds = useCallback((activityId) => {
    const key = String(activityId);
    setComparisonSelections((prev) => {
      if (!(key in prev)) return prev;
      const updated = { ...prev };
      delete updated[key];
      return updated;
    });
  }, []);

  const getComparisonIds = useCallback((activityId) => (
    comparisonSelections[String(activityId)] || EMPTY_ARRAY
  ), [comparisonSelections]);

  const toggleComparisonId = useCallback((activityId, comparisonId) => {
    setComparisonIds(activityId, (current) => (
      current.includes(comparisonId)
        ? current.filter((id) => id !== comparisonId)
        : [...current, comparisonId]
    ));
  }, [setComparisonIds]);

  const value = useMemo(() => ({
    overviewState,
    ensureOverview,
    getActivitiesState,
    ensureActivities,
    getTrendsState,
    ensureTrends,
    getComparisonIds,
    setComparisonIds,
    clearComparisonIds,
    toggleComparisonId,
  }), [
    overviewState,
    ensureOverview,
    getActivitiesState,
    ensureActivities,
    getTrendsState,
    ensureTrends,
    getComparisonIds,
    setComparisonIds,
    clearComparisonIds,
    toggleComparisonId,
  ]);

  return createElement(AppStateContext.Provider, { value }, children);
}

function useAppStateContext() {
  const context = useContext(AppStateContext);
  if (!context) {
    throw new Error('AppStateProvider is required');
  }
  return context;
}

export function useOverviewStore() {
  const { overviewState, ensureOverview } = useAppStateContext();
  return {
    overview: overviewState.data,
    loading: overviewState.loading,
    error: overviewState.error,
    ensureOverview,
  };
}

export function useActivityStore() {
  const { getActivitiesState, ensureActivities, getTrendsState, ensureTrends } = useAppStateContext();
  return {
    getActivitiesState,
    ensureActivities,
    getTrendsState,
    ensureTrends,
  };
}

export function useComparisonStore() {
  const {
    getComparisonIds,
    setComparisonIds,
    clearComparisonIds,
    toggleComparisonId,
  } = useAppStateContext();
  return {
    getComparisonIds,
    setComparisonIds,
    clearComparisonIds,
    toggleComparisonId,
  };
}

import { useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useComparisonStore } from '../stores/appState';

function parseComparisonIds(rawValue) {
  if (!rawValue) return [];
  return Array.from(
    new Set(
      rawValue
        .split(',')
        .map((value) => Number(value.trim()))
        .filter((value) => Number.isFinite(value) && value > 0)
    )
  ).slice(0, 5);
}

export function useComparisonState(activityId) {
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    getComparisonIds,
    setComparisonIds: setStoredComparisonIds,
    clearComparisonIds,
    toggleComparisonId,
  } = useComparisonStore();

  const routeComparisonIds = useMemo(
    () => parseComparisonIds(searchParams.get('compare')),
    [searchParams]
  );
  const comparisonIds = getComparisonIds(activityId);

  useEffect(() => {
    if (!activityId) return;
    if (routeComparisonIds.length > 0) {
      setStoredComparisonIds(activityId, routeComparisonIds);
    } else {
      clearComparisonIds(activityId);
    }
  }, [activityId, routeComparisonIds, setStoredComparisonIds, clearComparisonIds]);

  useEffect(() => {
    if (!activityId) return;
    const currentParam = searchParams.get('compare') || '';
    const nextParam = comparisonIds.join(',');
    if (currentParam === nextParam) return;

    const nextSearchParams = new URLSearchParams(searchParams);
    if (comparisonIds.length > 0) {
      nextSearchParams.set('compare', nextParam);
    } else {
      nextSearchParams.delete('compare');
    }
    setSearchParams(nextSearchParams, { replace: true });
  }, [activityId, comparisonIds, searchParams, setSearchParams]);

  const setComparisonIds = (nextOrUpdater) => {
    if (!activityId) return;
    setStoredComparisonIds(activityId, nextOrUpdater);
  };

  const clearAllComparisonIds = () => {
    if (!activityId) return;
    clearComparisonIds(activityId);
  };

  const toggleId = (comparisonId) => {
    if (!activityId) return;
    toggleComparisonId(activityId, comparisonId);
  };

  return {
    comparisonIds,
    setComparisonIds,
    clearComparisonIds: clearAllComparisonIds,
    toggleComparisonId: toggleId,
  };
}

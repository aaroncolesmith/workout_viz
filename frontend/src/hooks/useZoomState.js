import { useCallback, useEffect, useMemo, useState } from 'react';

export function useZoomState({ data = [], xAxisType = 'distance' }) {
  const [zoom, setZoom] = useState(null);
  const [drag, setDrag] = useState(null);

  useEffect(() => {
    setZoom(null);
    setDrag(null);
  }, [xAxisType]);

  useEffect(() => {
    if (!zoom?.isZoomed) return;
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setZoom(null);
        setDrag(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [zoom]);

  const xKey = xAxisType === 'distance' ? 'mile' : 'time';

  const filteredData = useMemo(() => {
    if (!zoom?.isZoomed || data.length === 0) return data;
    const lo = zoom.startVal <= zoom.endVal ? zoom.startVal : zoom.endVal;
    const hi = zoom.startVal <= zoom.endVal ? zoom.endVal : zoom.startVal;

    if (xAxisType === 'distance') {
      return data.filter((row) => {
        const value = parseFloat(row[xKey]);
        return value >= parseFloat(lo) && value <= parseFloat(hi);
      });
    }

    return data.filter((row) => row[xKey] >= lo && row[xKey] <= hi);
  }, [data, xAxisType, xKey, zoom]);

  const commitDrag = useCallback(() => {
    if (!drag || drag.startVal === drag.currentVal) {
      setDrag(null);
      return;
    }
    setZoom({
      startVal: drag.startVal,
      endVal: drag.currentVal,
      isZoomed: true,
    });
    setDrag(null);
  }, [drag]);

  const onMouseDown = useCallback((event) => {
    if (!event || event.activeLabel == null) return;
    setDrag({ startVal: event.activeLabel, currentVal: event.activeLabel });
  }, []);

  const onMouseMove = useCallback((event) => {
    if (!drag || !event || event.activeLabel == null) return;
    setDrag((prev) => ({ ...prev, currentVal: event.activeLabel }));
  }, [drag]);

  const onMouseUp = useCallback(() => {
    commitDrag();
  }, [commitDrag]);

  const onMouseLeave = useCallback(() => {
    commitDrag();
  }, [commitDrag]);

  const reset = useCallback(() => {
    setZoom(null);
    setDrag(null);
  }, []);

  return {
    zoom,
    drag,
    isZoomed: Boolean(zoom?.isZoomed),
    filteredData,
    onMouseDown,
    onMouseMove,
    onMouseUp,
    onMouseLeave,
    reset,
    referenceAreaProps: drag
      ? {
          x1: drag.startVal,
          x2: drag.currentVal,
        }
      : null,
  };
}

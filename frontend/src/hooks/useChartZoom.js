import { useState, useEffect, useCallback } from 'react';

/**
 * useChartZoom — reusable drag-to-zoom state for Recharts charts.
 *
 * Works with both numeric axes (ScatterChart) and category axes (AreaChart).
 * Handles axis key capture via Recharts' e.activeLabel / e.activePayload,
 * and filters the source data array to the selected range.
 *
 * Usage:
 *   const zoom = useChartZoom({ data, xKey: 'date', mode: 'numeric' });
 *   <ScatterChart
 *     onMouseDown={zoom.onMouseDown}
 *     onMouseMove={zoom.onMouseMove}
 *     onMouseUp={zoom.onMouseUp}
 *     onMouseLeave={zoom.onMouseLeave}
 *   >
 *     {zoom.referenceArea}
 *   </ScatterChart>
 *   {zoom.isZoomed && <button onClick={zoom.reset}>Reset Zoom</button>}
 *
 * The hook also wire a global `keydown` → Escape listener when zoomed.
 */
export function useChartZoom({ data = [], xKey = 'x', yKey = 'y', mode = 'numeric' }) {
  const [drag, setDrag] = useState(null);   // { x1, y1, x2, y2 } during drag
  const [domain, setDomain] = useState(null); // { xMin, xMax, yMin, yMax } when zoomed

  const isZoomed = domain !== null;
  const isDragging = drag !== null;

  // ── Escape key reset ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!isZoomed) return;
    const handler = (e) => { if (e.key === 'Escape') reset(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isZoomed]);

  // ── Event helpers ────────────────────────────────────────────────────────────
  const getCoords = useCallback((e) => {
    if (!e) return null;

    if (mode === 'numeric') {
      // ScatterChart: activePayload gives the {x, y} data-space values
      if (!e.activePayload?.length) return null;
      const p = e.activePayload[0].payload;
      return { x: p[xKey], y: p[yKey] };
    }

    // category / AreaChart mode: use activeLabel for X
    if (e.activeLabel == null) return null;
    return { x: e.activeLabel, y: null };
  }, [mode, xKey, yKey]);

  // ── Mouse handlers ────────────────────────────────────────────────────────────
  const onMouseDown = useCallback((e) => {
    const c = getCoords(e);
    if (!c) return;
    setDrag({ x1: c.x, y1: c.y, x2: c.x, y2: c.y });
  }, [getCoords]);

  const onMouseMove = useCallback((e) => {
    if (!drag) return;
    const c = getCoords(e);
    if (!c) return;
    setDrag(prev => ({ ...prev, x2: c.x, y2: c.y ?? prev.y2 }));
  }, [drag, getCoords]);

  const onMouseUp = useCallback(() => {
    if (!drag) return;
    const { x1, x2, y1, y2 } = drag;

    // Require a meaningful drag (not a click)
    const xMoved = x1 !== x2;
    const yMoved = y1 != null && y2 != null && Math.abs(y1 - y2) > 1;
    if (!xMoved && !yMoved) {
      setDrag(null);
      return;
    }

    if (mode === 'numeric') {
      const xMin = Math.min(x1, x2);
      const xMax = Math.max(x1, x2);
      // If drag is mostly horizontal, don't lock Y — let Chart auto-scale
      const dy = Math.abs((y1 ?? 0) - (y2 ?? 0));
      const yLock = dy > 2;
      setDomain({
        xMin, xMax,
        yMin: yLock ? Math.min(y1, y2) : null,
        yMax: yLock ? Math.max(y1, y2) : null,
      });
    } else {
      // Category mode: x1/x2 are the label values
      setDomain({ x1, x2, yMin: null, yMax: null });
    }
    setDrag(null);
  }, [drag, mode]);

  // onMouseLeave commits whatever selection is in progress (using last known position).
  // This lets users drag to the very edge of the chart and slightly beyond
  // without losing their selection.
  const onMouseLeave = useCallback(() => {
    if (!drag) return;
    const { x1, x2, y1, y2 } = drag;

    // Discard if the user just clicked without dragging
    const xMoved = x1 !== x2;
    const yMoved = y1 != null && y2 != null && Math.abs(y1 - y2) > 1;
    if (!xMoved && !yMoved) {
      setDrag(null);
      return;
    }

    // Commit the selection with whatever x2/y2 we last captured
    if (mode === 'numeric') {
      const xMin = Math.min(x1, x2);
      const xMax = Math.max(x1, x2);
      const dy = Math.abs((y1 ?? 0) - (y2 ?? 0));
      const yLock = dy > 2;
      setDomain({
        xMin, xMax,
        yMin: yLock ? Math.min(y1, y2) : null,
        yMax: yLock ? Math.max(y1, y2) : null,
      });
    } else {
      setDomain({ x1, x2, yMin: null, yMax: null });
    }
    setDrag(null);
  }, [drag, mode]);

  const reset = useCallback(() => {
    setDomain(null);
    setDrag(null);
  }, []);

  // ── Filtered data (category mode) / domain props (numeric mode) ─────────────
  const filteredData = domain && mode === 'category'
    ? (() => {
        const { x1, x2 } = domain;
        const lo = x1 <= x2 ? x1 : x2;
        const hi = x1 <= x2 ? x2 : x1;
        return data.filter(d => d[xKey] >= lo && d[xKey] <= hi);
      })()
    : data;

  // Recharts axis domain props for numeric zoom
  const xDomain = domain && mode === 'numeric'
    ? [domain.xMin, domain.xMax]
    : undefined;
  const yDomain = domain?.yMin != null
    ? [domain.yMin, domain.yMax]
    : undefined;

  // ── ReferenceArea for visual drag feedback ─────────────────────────────────
  // Caller spreads this inside the chart JSX
  const referenceAreaProps = drag
    ? {
        x1: drag.x1,
        x2: drag.x2,
        y1: drag.y1 ?? undefined,
        y2: drag.y2 ?? undefined,
        fill: 'rgba(56, 189, 248, 0.15)',
        stroke: 'rgba(56, 189, 248, 0.4)',
        strokeWidth: 1,
        strokeDasharray: '3 3',
        isFront: true,
      }
    : null;

  return {
    // State
    isZoomed,
    isDragging,
    domain,
    drag,
    filteredData,
    // Axis domain props (numeric mode)
    xDomain,
    yDomain,
    // Reference area
    referenceAreaProps,
    // Chart event handlers
    onMouseDown,
    onMouseMove,
    onMouseUp,
    onMouseLeave,
    // Reset
    reset,
  };
}

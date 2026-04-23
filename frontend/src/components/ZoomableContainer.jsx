import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { ReferenceArea, XAxis, YAxis } from 'recharts';

/**
 * ZoomableContainer - Perfected version using Recharts internal coordinates.
 * 
 * Uses e.chartX and e.viewBox from Recharts events for precise mapping.
 * Uses data filtering for categorical zoom.
 * Uses window mouseup for robustness.
 */
export default function ZoomableContainer({ 
  children, 
  data = [], 
  xAxisKey = 'index',
  yAxisKey = 'value',
  initialXDomain = ['dataMin', 'dataMax'],
  initialYDomain = ['auto', 'auto'],
  reversedY = false,
  onZoomChange,
  className = "",
  ...props
}) {
  const [zoom, setZoom] = useState({
    left: initialXDomain[0],
    right: initialXDomain[1],
    top: initialYDomain[1],
    bottom: initialYDomain[0],
    refAreaLeftIdx: null,
    refAreaRightIdx: null,
    refAreaTopValue: null,
    refAreaBottomValue: null,
  });

  const [isZoomed, setIsZoomed] = useState(false);
  const zoomStateRef = useRef(zoom);
  zoomStateRef.current = zoom;

  const isDragging = zoom.refAreaLeftIdx !== null;

  const getValuesFromEvent = useCallback((e) => {
    if (!e || !e.viewBox) return null;
    const { chartX, chartY, viewBox } = e;
    
    // X-Axis (Index based)
    const xRatio = (chartX - viewBox.x) / viewBox.width;
    const clampedXRatio = Math.max(0, Math.min(1, xRatio));
    const idx = Math.round(clampedXRatio * (data.length - 1));
    
    // Y-Axis (Value based)
    const yRatio = (chartY - viewBox.y) / viewBox.height;
    const clampedYRatio = Math.max(0, Math.min(1, yRatio));
    const yValues = data.map(d => d[yAxisKey]).filter(v => v != null);
    const min = Math.min(...yValues);
    const max = Math.max(...yValues);
    const yVal = reversedY ? min + clampedYRatio * (max - min) : max - clampedYRatio * (max - min);

    return { idx, yVal, xVal: data[idx]?.[xAxisKey] };
  }, [data, xAxisKey, yAxisKey, reversedY]);

  const handleMouseDown = useCallback((e) => {
    const vals = getValuesFromEvent(e);
    if (!vals) return;

    setZoom(prev => ({
      ...prev,
      refAreaLeftIdx: vals.idx,
      refAreaRightIdx: vals.idx,
      refAreaTopValue: vals.yVal,
      refAreaBottomValue: vals.yVal,
    }));
  }, [getValuesFromEvent]);

  const handleMouseMove = useCallback((e) => {
    if (zoomStateRef.current.refAreaLeftIdx === null) return;
    const vals = getValuesFromEvent(e);
    if (!vals) return;

    setZoom(prev => ({
      ...prev,
      refAreaRightIdx: vals.idx,
      refAreaBottomValue: vals.yVal,
    }));
  }, [getValuesFromEvent]);

  const applyZoom = useCallback(() => {
    const current = zoomStateRef.current;
    if (current.refAreaLeftIdx === null || current.refAreaRightIdx === null) return;

    const startIdx = current.refAreaLeftIdx;
    const endIdx = current.refAreaRightIdx;

    if (startIdx === endIdx && Math.abs(current.refAreaTopValue - current.refAreaBottomValue) < 0.1) {
      setZoom(prev => ({ ...prev, refAreaLeftIdx: null, refAreaRightIdx: null }));
      return;
    }

    const s = Math.min(startIdx, endIdx);
    const e = Math.max(startIdx, endIdx);

    const l = data[s]?.[xAxisKey];
    const r = data[e]?.[xAxisKey];

    const dy = Math.abs(current.refAreaTopValue - current.refAreaBottomValue);
    const isHorizontalOnly = dy < 1; // threshold in data units

    setZoom(prev => ({
      ...prev,
      left: l,
      right: r,
      top: isHorizontalOnly ? initialYDomain[1] : Math.max(current.refAreaTopValue, current.refAreaBottomValue),
      bottom: isHorizontalOnly ? initialYDomain[0] : Math.min(current.refAreaTopValue, current.refAreaBottomValue),
      refAreaLeftIdx: null,
      refAreaRightIdx: null,
    }));
    setIsZoomed(true);
    if (onZoomChange) onZoomChange(true);
  }, [data, xAxisKey, initialYDomain, onZoomChange]);

  useEffect(() => {
    if (isDragging) {
      const onUp = () => applyZoom();
      window.addEventListener('mouseup', onUp, { once: true });
      return () => window.removeEventListener('mouseup', onUp);
    }
  }, [isDragging, applyZoom]);

  const handleResetZoom = useCallback(() => {
    setZoom({
      left: initialXDomain[0],
      right: initialXDomain[1],
      top: initialYDomain[1],
      bottom: initialYDomain[0],
      refAreaLeftIdx: null,
      refAreaRightIdx: null,
      refAreaTopValue: null,
      refAreaBottomValue: null,
    });
    setIsZoomed(false);
    if (onZoomChange) onZoomChange(false);
  }, [initialXDomain, initialYDomain, onZoomChange]);

  const filteredData = useMemo(() => {
    if (!isZoomed) return data;
    const s = data.findIndex(d => d[xAxisKey] === zoom.left);
    const e = data.findIndex(d => d[xAxisKey] === zoom.right);
    if (s === -1 || e === -1) return data;
    return data.slice(Math.min(s, e), Math.max(s, e) + 1);
  }, [data, isZoomed, zoom.left, zoom.right, xAxisKey]);

  return (
    <div className={`zoomable-wrapper ${className}`} style={{ position: 'relative', width: '100%', height: '100%', cursor: 'crosshair' }}>
      {isZoomed && (
        <button onClick={handleResetZoom} className="filter-chip" style={{ 
          position: 'absolute', top: 10, right: 10, zIndex: 1000, background: 'rgba(56, 189, 248, 0.4)', color: '#fff', border: '1px solid #38bdf8', borderRadius: 20, padding: '4px 12px', fontSize: '0.7rem' 
        }}>
          Reset Zoom
        </button>
      )}
      {React.cloneElement(children, {
        onMouseDown: handleMouseDown,
        onMouseMove: handleMouseMove,
        data: filteredData,
        width: props.width || children.props.width,
        height: props.height || children.props.height,
        children: [
          ...React.Children.map(children.props.children, child => {
            if (!child) return null;
            const type = child.type?.displayName || child.type?.name;
            if (type === 'YAxis' || child.type === YAxis) {
              return React.cloneElement(child, { domain: [zoom.bottom, zoom.top], allowDataOverflow: true });
            }
            return child;
          }),
          isDragging && zoom.refAreaLeftIdx !== null && zoom.refAreaRightIdx !== null && (
            <ReferenceArea 
              key="zoombox"
              x1={data[zoom.refAreaLeftIdx]?.[xAxisKey]} 
              x2={data[zoom.refAreaRightIdx]?.[xAxisKey]} 
              strokeOpacity={0.3} fill="rgba(56, 189, 248, 0.2)" isFront={true}
              style={{ pointerEvents: 'none' }}
            />
          )
        ]
      })}
    </div>
  );
}

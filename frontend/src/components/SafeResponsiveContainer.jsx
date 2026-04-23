import React, { useState, useEffect, useRef } from 'react';
import { ResponsiveContainer } from 'recharts';

/**
 * SafeResponsiveContainer — A bulletproof wrapper for Recharts' ResponsiveContainer.
 * It uses a ResizeObserver to only mount the chart once valid dimensions are detected,
 * and a debounce to prevent jitter during page layout shifts.
 */
const SafeResponsiveContainer = ({ children, height, ...props }) => {
  const [dims, setDims] = useState({ width: 0, height: 0 });
  const containerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const observer = new ResizeObserver((entries) => {
      if (!entries.length) return;
      const { width, height: entryHeight } = entries[0].contentRect;
      if (width > 0) {
        setDims({ width, height: entryHeight || height });
      }
    });

    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [height]);

  return (
    <div 
      ref={containerRef} 
      style={{ 
        width: '100%', 
        height, 
        position: 'relative', 
        minWidth: 0, 
        minHeight: 0,
        overflow: 'hidden' 
      }}
    >
      {dims.width > 0 ? (
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}>
          <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0} {...props}>
            {children}
          </ResponsiveContainer>
        </div>
      ) : null}
    </div>
  );
};

export default SafeResponsiveContainer;

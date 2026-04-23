import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import { Search, RefreshCw, X, Info } from 'lucide-react';
import _ from 'lodash';

/**
 * WorkoutPCA - High-performance scatter plot for PCA data.
 * Uses HTML5 Canvas for data points (handles thousands of nodes)
 * and SVG for axes/labels/interactive markers.
 */
const WorkoutPCA = ({ 
  data, 
  loadings, 
  onSelectActivity, 
  selectedId, 
  highlightIds = [],
  isMini = false
}) => {
  const svgRef = useRef();
  const canvasRef = useRef();
  const containerRef = useRef();
  
  const [hoveredNode, setHoveredNode] = useState(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const [zoomTransform, setZoomTransform] = useState(d3.zoomIdentity);
  const [searchTerm, setSearchTerm] = useState('');
  const [showLoadings, setShowLoadings] = useState(true);
  const [searchResults, setSearchResults] = useState([]);

  // Store various state-related values in refs to avoid frequent effect re-triggers while allowing the canvas redraw to access them
  const stateRef = useRef({
    data: [],
    selectedId: null,
    highlightIds: [],
    searchTerm: '',
    zoomTransform: d3.zoomIdentity,
    scales: { x: null, y: null },
    hoveredNodeId: null
  });

  const clusterColors = [
    'rgba(59, 130, 246, 0.7)', // Blue
    'rgba(16, 185, 129, 0.7)', // green
    'rgba(245, 158, 11, 0.7)', // amber
    'rgba(139, 92, 246, 0.7)', // violet
    'rgba(239, 68, 68, 0.7)',  // red
    'rgba(6, 182, 212, 0.7)',  // cyan
    'rgba(244, 63, 94, 0.7)',  // rose
    'rgba(20, 184, 166, 0.7)'  // teal
  ];

  // Helper to draw the scene on canvas
  const drawCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const { 
      data, selectedId, highlightIds, searchTerm, zoomTransform, scales 
    } = stateRef.current;
    
    if (!scales.x || !scales.y) return;

    const width = canvas.width;
    const height = canvas.height;
    
    // Account for High DPI
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width / dpr, height / dpr);

    const tx = zoomTransform.rescaleX(scales.x);
    const ty = zoomTransform.rescaleY(scales.y);

    // Draw non-highlighted points first
    data.forEach(d => {
      // Logic for filtering/opacity
      const isMatch = !searchTerm || d.name.toLowerCase().includes(searchTerm.toLowerCase());
      const isHighlighted = highlightIds.includes(d.id) || d.id === selectedId;
      
      if (isHighlighted) return; // Draw these last for layering

      const lx = tx(d.pca_x);
      const ly = ty(d.pca_y);
      
      ctx.beginPath();
      ctx.arc(lx, ly, 4.5, 0, 2 * Math.PI);
      ctx.fillStyle = isMatch ? clusterColors[d.cluster % clusterColors.length] : 'rgba(255, 255, 255, 0.05)';
      ctx.fill();
    });

    // Draw highlighted points (selected or filtered) on top
    data.forEach(d => {
      const isHighlighted = highlightIds.includes(d.id) || d.id === selectedId;
      if (!isHighlighted) return;

      const lx = tx(d.pca_x);
      const ly = ty(d.pca_y);
      const isSelected = d.id === selectedId;
      
      ctx.beginPath();
      ctx.arc(lx, ly, isSelected ? 7 : 6, 0, 2 * Math.PI);
      ctx.fillStyle = clusterColors[d.cluster % clusterColors.length].replace('0.7', '1.0');
      ctx.fill();
      
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });
  }, []);

  useEffect(() => {
    if (!data || data.length === 0) return;

    const width = containerRef.current.clientWidth;
    const height = isMini ? 350 : 600;
    const margin = isMini 
      ? { top: 10, right: 10, bottom: 20, left: 30 }
      : { top: 40, right: 40, bottom: 40, left: 50 };

    // Set canvas dimensions with HDPI support
    const dpr = window.devicePixelRatio || 1;
    const canvas = canvasRef.current;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    const svg = d3.select(svgRef.current)
      .attr("width", width)
      .attr("height", height);
    
    svg.selectAll("*").remove();

    // Data Extents
    const xExtent = d3.extent(data, d => d.pca_x);
    const yExtent = d3.extent(data, d => d.pca_y);
    const xRange = xExtent[1] - xExtent[0];
    const yRange = yExtent[1] - yExtent[0];
    
    const xScale = d3.scaleLinear()
      .domain([xExtent[0] - xRange * 0.1, xExtent[1] + xRange * 0.1])
      .range([margin.left, width - margin.right]);

    const yScale = d3.scaleLinear()
      .domain([yExtent[0] - yRange * 0.1, yExtent[1] + yRange * 0.1])
      .range([height - margin.bottom, margin.top]);

    stateRef.current.scales = { x: xScale, y: yScale };
    stateRef.current.data = data;

    // Axes
    const xAxis = d3.axisBottom(xScale).ticks(10).tickSize(-height + margin.top + margin.bottom);
    const yAxis = d3.axisLeft(yScale).ticks(10).tickSize(-width + margin.left + margin.right);

    const xG = svg.append("g")
      .attr("class", "x-axis")
      .attr("transform", `translate(0, ${height - margin.bottom})`)
      .call(xAxis);

    const yG = svg.append("g")
      .attr("class", "y-axis")
      .attr("transform", `translate(${margin.left}, 0)`)
      .call(yAxis);

    const styleAxis = (axisG) => {
      axisG.selectAll(".tick line").attr("stroke", "rgba(255,255,255,0.05)");
      axisG.selectAll(".domain").remove();
      axisG.selectAll("text").attr("fill", "rgba(255,255,255,0.4)").style("font-size", "9px");
    };
    styleAxis(xG);
    styleAxis(yG);

    // Quadtree for super-fast point finding
    const quadtree = d3.quadtree()
      .x(d => xScale(d.pca_x))
      .y(d => yScale(d.pca_y))
      .addAll(data);

    // Loadings (Feature Vectors)
    let loadingGroup = null;
    const updateLoadings = (transform) => {
      if (!loadings || !showLoadings) return;
      if (!loadingGroup) loadingGroup = svg.append("g").attr("class", "loadings-viz");
      loadingGroup.selectAll("*").remove();
      
      const tx = transform.rescaleX(xScale);
      const ty = transform.rescaleY(yScale);
      const scaleFactor = Math.min(xRange, yRange) * 1.5;

      loadings.forEach(l => {
        const x1 = tx(0), y1 = ty(0);
        const x2 = tx(l.pc1 * scaleFactor), y2 = ty(l.pc2 * scaleFactor);

        loadingGroup.append("line")
          .attr("x1", x1).attr("y1", y1)
          .attr("x2", x2).attr("y2", y2)
          .attr("stroke", "rgba(255,255,255,0.15)")
          .attr("stroke-width", 1)
          .attr("stroke-dasharray", "4,2");

        loadingGroup.append("text")
          .attr("x", x2).attr("y", y2)
          .attr("dy", -5)
          .attr("fill", "rgba(255,255,255,0.4)")
          .attr("font-size", "10px")
          .attr("text-anchor", "middle")
          .text(l.feature.split('_')[0]);
      });
    };

    // Zoom & Pan
    const zoom = d3.zoom()
      .scaleExtent([0.1, 40])
      .on("zoom", (event) => {
        const { transform } = event;
        stateRef.current.zoomTransform = transform;
        setZoomTransform(transform);
        
        // Redraw canvas and rescaled axes
        drawCanvas();
        
        xG.call(xAxis.scale(transform.rescaleX(xScale)));
        yG.call(yAxis.scale(transform.rescaleY(yScale)));
        styleAxis(xG);
        styleAxis(yG);

        // Update loadings if visible
        if (showLoadings) updateLoadings(transform);
      });

    svg.call(zoom);
    svg.call(zoom.transform, zoomTransform);
    updateLoadings(zoomTransform);

    // Interactive Overlay Element for Hoover
    const hoverCircle = svg.append("circle")
      .attr("r", 10)
      .attr("fill", "none")
      .attr("stroke", "#ffffff")
      .attr("stroke-width", 2.5)
      .style("opacity", 0)
      .style("pointer-events", "none")
      .style("filter", "drop-shadow(0 0 5px rgba(255,255,255,0.5))");

    // Mouse events
    svg.on("mousemove", (event) => {
      const [mx, my] = d3.pointer(event);
      // Project mouse into data space via zoom transform inverse
      const transform = stateRef.current.zoomTransform;
      const invMx = transform.invertX(mx);
      const invMy = transform.invertY(my);
      
      const searchRadius = 20 / transform.k;
      const closest = quadtree.find(invMx, invMy, 20); // Search in screen space approx if quadtree built on xScale/yScale

      if (closest) {
        const tx = transform.applyX(xScale(closest.pca_x));
        const ty = transform.applyY(yScale(closest.pca_y));
        
        hoverCircle
          .attr("cx", tx)
          .attr("cy", ty)
          .style("opacity", 1)
          .attr("stroke", clusterColors[closest.cluster % clusterColors.length].replace('0.7', '1.0'));
        
        if (!hoveredNode || hoveredNode.id !== closest.id) {
          setHoveredNode(closest);
          stateRef.current.hoveredNodeId = closest.id;
        }

        const [containerX, containerY] = d3.pointer(event, containerRef.current);
        setTooltipPos({ x: containerX, y: containerY });
      } else {
        setHoveredNode(null);
        stateRef.current.hoveredNodeId = null;
        hoverCircle.style("opacity", 0);
      }
    });

    svg.on("mouseleave", () => {
      setHoveredNode(null);
      stateRef.current.hoveredNodeId = null;
      hoverCircle.style("opacity", 0);
    });

    svg.on("click", (event) => {
      const [mx, my] = d3.pointer(event);
      const transform = stateRef.current.zoomTransform;
      const invMx = transform.invertX(mx);
      const invMy = transform.invertY(my);
      const closest = quadtree.find(invMx, invMy, 20);
      if (closest) onSelectActivity(closest.id);
    });

    drawCanvas();
    
    window.resetZoom = () => {
      svg.transition().duration(750)
        .call(zoom.transform, d3.zoomIdentity);
    };

  }, [data, loadings, isMini, drawCanvas, showLoadings]);

  // Handle prop updates separately for reactivity without full SVG rebuild
  useEffect(() => {
    stateRef.current.selectedId = selectedId;
    stateRef.current.highlightIds = highlightIds;
    stateRef.current.searchTerm = searchTerm;
    drawCanvas();
  }, [selectedId, highlightIds, searchTerm, drawCanvas]);

  const handleSearch = (e) => {
    const term = e.target.value;
    setSearchTerm(term);
    if (term.length > 1) {
      const results = data.filter(d => 
        d.name.toLowerCase().includes(term.toLowerCase()) || 
        d.date.includes(term)
      ).slice(0, 5);
      setSearchResults(results);
    } else {
      setSearchResults([]);
    }
  };

  return (
    <div className={`pca-container ${isMini ? 'is-mini' : ''}`} ref={containerRef}>
      {!isMini && (
        <div className="pca-controls">
          <div className="control-group">
            <button onClick={() => window.resetZoom()} className="control-btn" title="Reset View">
              <RefreshCw size={16} />
            </button>
            <div className="divider-v" />
            <button 
              onClick={() => setShowLoadings(!showLoadings)}
              className={`control-btn ${showLoadings ? 'active' : ''}`}
              title="Toggle Feature Vectors"
            >
              <Info size={16} />
            </button>
          </div>

          <div style={{ position: 'relative' }}>
            <div className="pca-search-box">
              <Search size={16} style={{ opacity: 0.4 }} />
              <input 
                type="text"
                placeholder="Search workouts..."
                value={searchTerm}
                onChange={handleSearch}
                className="pca-search-input"
              />
              {searchTerm && (
                <button onClick={() => setSearchTerm('')} className="search-clear-btn">
                  <X size={14} />
                </button>
              )}
            </div>
            
            {searchResults.length > 0 && (
              <div className="search-results-dropdown">
                {searchResults.map(res => (
                  <button 
                    key={res.id}
                    onClick={() => {
                      onSelectActivity(res.id);
                      setSearchTerm('');
                      setSearchResults([]);
                    }}
                    className="search-result-item"
                  >
                    <span className="result-name">{res.name}</span>
                    <span className="result-meta">{res.date} • {res.distance_miles.toFixed(2)} mi</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {!isMini && (
        <div className="pca-legend">
          <h4 className="legend-title">Archetypes</h4>
          {_.uniqBy(data, 'cluster').sort((a,b) => a.cluster - b.cluster).map(d => (
            <div key={d.cluster} className="legend-item">
              <div className="legend-color" style={{ background: clusterColors[d.cluster % clusterColors.length] }} />
              <span className="legend-label">Cluster {d.cluster}</span>
            </div>
          ))}
        </div>
      )}

      {hoveredNode && (
        <div 
          className="pca-tooltip"
          style={{ 
            left: `${tooltipPos.x + 15}px`,
            top: `${tooltipPos.y + 15}px`,
            borderLeft: `4px solid ${clusterColors[hoveredNode.cluster % clusterColors.length]}`,
            pointerEvents: 'none',
            transform: `
              ${tooltipPos.x > (containerRef.current?.clientWidth || 0) * 0.7 ? 'translateX(-110%)' : ''}
              ${tooltipPos.y > (containerRef.current?.clientHeight || 0) * 0.7 ? 'translateY(-110%)' : ''}
            `
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span className="header-badge-text">{hoveredNode.type}</span>
            <span className="header-badge-text" style={{ opacity: 0.5 }}>{hoveredNode.date}</span>
          </div>
          <h3>{hoveredNode.name}</h3>
          
          <div className="tooltip-grid">
            <div className="stat-item">
              <span className="mini-label">Distance</span>
              <div className="mini-value">{hoveredNode.distance_miles.toFixed(2)} mi</div>
            </div>
            <div className="stat-item">
              <span className="mini-label">Pace</span>
              <div className="mini-value">{hoveredNode.pace ? hoveredNode.pace.toFixed(2) + '/mi' : 'N/A'}</div>
            </div>
            <div className="stat-item full">
              <span className="mini-label">Avg HR</span>
              <div className="mini-value">{hoveredNode.average_heartrate ? hoveredNode.average_heartrate.toFixed(0) + ' bpm' : 'N/A'}</div>
            </div>
          </div>
        </div>
      )}

      {/* Rendering Layers */}
      <canvas ref={canvasRef} className="pca-canvas-layer" />
      <svg ref={svgRef} className="pca-svg-layer cursor-crosshair" />
      
      {!isMini && (
        <div className="pca-variance-info">
          <span>PC1: Volume vs PC2: Intensity</span>
        </div>
      )}
    </div>
  );
};

export default WorkoutPCA;

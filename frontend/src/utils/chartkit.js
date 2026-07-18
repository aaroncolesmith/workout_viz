/**
 * ChartKit — the one place chart chrome is defined.
 *
 * Every quantitative chart shares: margins, grid, axis ticks, the scrub
 * cursor, and the tooltip box. Consistency rule: hovering (or touch-
 * dragging) ANYWHERE over a chart must surface the nearest point — never
 * require landing exactly on a 3px dot.
 *
 * Recharts only recognises its own element types as chart children, so the
 * helpers here are PROPS FACTORIES (spread them onto real <Line>/<Tooltip>
 * elements), not wrapper components.
 *
 * The scrub trick for scatter data: render dots with <Scatter> as usual,
 * plus an invisible <Line {...scrubLine(key, color)}> over the same data —
 * the Line participates in axis-mode tooltips, so the cursor snaps to the
 * closest x anywhere in the plot and highlights it with activeDot.
 */
export const CHART_MARGIN = { top: 6, right: 12, bottom: 0, left: -8 };

export const GRID_PROPS = { strokeDasharray: '3 3', stroke: 'rgba(255,255,255,0.05)' };

export const AXIS_TICK = { fontSize: 10, fill: '#8a8a96' };

/** Vertical scrub line shown while hovering (Tooltip cursor prop). */
export const SCRUB_CURSOR = {
  stroke: 'rgba(255,255,255,0.28)',
  strokeWidth: 1,
  strokeDasharray: '4 4',
};

/** Bar-chart hover highlight (Tooltip cursor prop for BarCharts). */
export const BAR_CURSOR = { fill: 'rgba(255,255,255,0.04)' };

/**
 * Invisible line that makes scatter data scrubbable: axis-mode tooltip +
 * a highlighted nearest point. Spread onto a <Line> in a ComposedChart.
 */
export const scrubLine = (dataKey, color) => ({
  type: 'monotone',
  dataKey,
  stroke: 'none',
  dot: false,
  isAnimationActive: false,
  legendType: 'none',
  activeDot: { r: 5, fill: color, stroke: '#0d0d0f', strokeWidth: 2 },
});


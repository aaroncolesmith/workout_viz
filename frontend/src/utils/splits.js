/**
 * Sequential whole-mile aggregation (mile 1, mile 2, …) from raw fine-grain
 * splits. Shared by the per-activity Splits tab and the multi-activity
 * comparison charts so both derive mile marks the same way.
 */
export function buildMileSplits(splits) {
  if (!splits || !splits.length) return [];
  const rows = [];
  let mileIdx = 1;
  let timeAcc = 0;
  let hrWeighted = 0;
  let hrTimeAcc = 0;
  let prevMile = 0;

  for (const s of splits) {
    const mile = Number(s.total_distance_miles) || (prevMile + 0.05);
    const dt = s.time_seconds || 0;
    timeAcc += dt;
    if (s.avg_heartrate) { hrWeighted += s.avg_heartrate * dt; hrTimeAcc += dt; }

    if (mile >= mileIdx) {
      rows.push({
        mile: mileIdx,
        time_seconds: timeAcc,
        pace_per_mile: timeAcc > 0 ? timeAcc / 60 : null,
        avg_hr: hrTimeAcc > 0 ? hrWeighted / hrTimeAcc : null,
        partial: false,
      });
      mileIdx += 1;
      timeAcc = 0; hrWeighted = 0; hrTimeAcc = 0;
    }
    prevMile = mile;
  }
  if (timeAcc > 0) {
    rows.push({
      mile: Math.round(prevMile * 100) / 100,
      time_seconds: timeAcc,
      pace_per_mile: null,
      avg_hr: hrTimeAcc > 0 ? hrWeighted / hrTimeAcc : null,
      partial: true,
    });
  }
  return rows;
}

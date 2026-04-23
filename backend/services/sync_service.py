"""
Sync service — handles fetching data from Strava and updating local CSVs.
"""
import time
import threading
import logging
from typing import List, Optional
from datetime import datetime
from stravalib.client import Client
from stravalib.model import SummaryActivity

from backend.services.strava_auth import get_strava_auth
from backend.services.data_service import get_data_service
from backend.services.database import get_conn

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

_SYNC_TIMEOUT_SECONDS = 600  # 10-minute hard cap on any sync operation


class SyncService:
    def __init__(self):
        self.auth = get_strava_auth()
        self.data_service = get_data_service()
        self.client = Client()

        # Configure stravalib to NOT sleep when rate limited
        from stravalib.util.limiter import RateLimiter
        self.client.protocol.rate_limiter = RateLimiter()

        self._total_count_cache = None
        self._total_count_timestamp = 0
        self._CACHE_TTL = 3600

        # ── Async sync state machine ──────────────────────────────────────────
        # Shared state read by both the background thread and the API layer.
        # Protected by _sync_lock for thread-safe access.
        self._sync_lock = threading.Lock()
        self._sync_state = {
            "status": "idle",       # idle | running | done | error
            "deep": False,
            "started_at": None,
            "fetched": 0,
            "added": 0,
            "skipped": 0,
            "message": "",
            "error": None,
        }

        # ── Splits backfill state machine ─────────────────────────────────────
        self._splits_lock = threading.Lock()
        self._splits_state = {
            "status": "idle",       # idle | running | done | error
            "total": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "current_activity": None,
            "started_at": None,
            "message": "",
            "error": None,
        }

    # ── Background sync API ───────────────────────────────────────────────────

    def start_sync_background(self, deep: bool = False) -> dict:
        """
        Start a sync in a background thread and return immediately.
        Returns an error dict if a sync is already running.
        """
        with self._sync_lock:
            if self._sync_state["status"] == "running":
                return {"status": "error", "message": "Sync already in progress"}
            self._sync_state = {
                "status": "running",
                "deep": deep,
                "started_at": datetime.utcnow().isoformat(),
                "fetched": 0,
                "added": 0,
                "skipped": 0,
                "message": "Starting…",
                "error": None,
            }

        thread = threading.Thread(target=self._run_sync, args=(deep,), daemon=True)
        thread.start()
        self._record_sync_event(
            sync_kind="activities",
            status="started",
            deep=deep,
            message="Background sync started",
            started_at=self._sync_state["started_at"],
        )
        return {"status": "started", "deep": deep}

    def get_sync_status(self) -> dict:
        """Return a snapshot of the current sync state (safe to call from any thread)."""
        with self._sync_lock:
            return dict(self._sync_state)

    # ── Splits backfill API ───────────────────────────────────────────────────

    def start_splits_backfill(self, limit: Optional[int] = None, types: Optional[List[str]] = None) -> dict:
        """
        Start a background job that fetches splits for all activities that don't have them.
        Processes most-recent activities first. Respects Strava rate limits (~1 req/sec).
        Returns an error dict if already running.
        """
        with self._splits_lock:
            if self._splits_state["status"] == "running":
                return {"status": "error", "message": "Splits backfill already in progress"}
            self._splits_state = {
                "status": "running",
                "total": 0,
                "completed": 0,
                "failed": 0,
                "skipped": 0,
                "current_activity": None,
                "started_at": datetime.utcnow().isoformat(),
                "message": "Starting…",
                "error": None,
            }

        thread = threading.Thread(
            target=self._run_splits_backfill,
            args=(limit, types),
            daemon=True,
        )
        thread.start()
        return {"status": "started"}

    def get_splits_sync_status(self) -> dict:
        with self._splits_lock:
            return dict(self._splits_state)

    def _run_splits_backfill(self, limit: Optional[int], types: Optional[List[str]]):
        """
        Background worker: walks activities without splits, fetches from Strava one-by-one.
        Rate limit: ~1 req/sec (well under Strava's 100 req/15min cap).
        """
        # Default to run-family types
        if types is None:
            types = ['Run', 'VirtualRun', 'TrailRun', 'Walk', 'Hike', 'Ride']

        try:
            if not self.auth.is_authenticated:
                raise RuntimeError("Not authenticated with Strava")

            self.client.access_token = self.auth.get_access_token()

            # Find activities without splits, ordered most-recent first
            conn = get_conn()
            placeholders = ','.join('?' * len(types))
            query = f"""
                SELECT a.id, a.name, a.type, a.start_date
                FROM activities a
                LEFT JOIN (
                    SELECT DISTINCT activity_id FROM splits
                ) s ON s.activity_id = a.id
                WHERE s.activity_id IS NULL
                  AND a.type IN ({placeholders})
                ORDER BY a.start_date DESC
            """
            rows = conn.execute(query, types).fetchall()

            if limit:
                rows = rows[:limit]

            total = len(rows)
            with self._splits_lock:
                self._splits_state["total"] = total
                self._splits_state["message"] = f"Found {total} activities without splits"

            if total == 0:
                with self._splits_lock:
                    self._splits_state.update({
                        "status": "done",
                        "message": "All activities already have splits",
                    })
                return

            completed = failed = skipped = 0

            for row in rows:
                act_id = row[0]
                act_name = row[1]

                with self._splits_lock:
                    self._splits_state["current_activity"] = act_name
                    self._splits_state["message"] = (
                        f"Fetching splits for {act_name} "
                        f"({completed + failed + skipped + 1}/{total})"
                    )

                try:
                    result = self.sync_activity_details(act_id)
                    if result.get("status") == "success":
                        completed += 1
                    else:
                        msg = result.get("message", "")
                        if "Rate Limit" in msg or "429" in msg:
                            # Back off for a full 15-minute window then retry once
                            logger.warning(f"Splits backfill: rate limited — backing off 15 min")
                            with self._splits_lock:
                                self._splits_state["message"] = "Rate limited — waiting 15 min before resuming…"
                            time.sleep(900)
                            self.client.access_token = self.auth.get_access_token()
                            retry = self.sync_activity_details(act_id)
                            if retry.get("status") == "success":
                                completed += 1
                            else:
                                failed += 1
                                logger.warning(f"Splits backfill: failed after retry for {act_id}: {retry.get('message')}")
                        elif "No stream data" in msg or "not found" in msg.lower() or "Not Found" in msg:
                            # Activity has no GPS/stream data, or no longer exists on Strava — skip it
                            skipped += 1
                            with self._splits_lock:
                                self._splits_state["skipped"] = skipped
                        else:
                            failed += 1
                            logger.warning(f"Splits backfill: failed for {act_id} ({act_name}): {msg}")
                except Exception as exc:
                    failed += 1
                    logger.warning(f"Splits backfill: exception for {act_id}: {exc}")

                with self._splits_lock:
                    self._splits_state["completed"] = completed
                    self._splits_state["failed"] = failed
                    self._splits_state["skipped"] = skipped

                # 2 Strava API calls per activity (get_activity + get_streams).
                # Strava cap: 100 req/15min = ~6.6/min.
                # 20s sleep → 3 activities/min → 6 API calls/min — safely under cap.
                time.sleep(20)

            with self._splits_lock:
                self._splits_state.update({
                    "status": "done",
                    "completed": completed,
                    "failed": failed,
                    "current_activity": None,
                    "message": f"Done — {completed} synced, {failed} failed out of {total}",
                })

        except Exception as exc:
            logger.error(f"Splits backfill failed: {exc}")
            with self._splits_lock:
                self._splits_state.update({
                    "status": "error",
                    "error": str(exc),
                    "message": f"Backfill failed: {exc}",
                })

    def _run_sync(self, deep: bool):
        """Background worker. Updates _sync_state throughout; never raises."""
        deadline = time.time() + _SYNC_TIMEOUT_SECONDS
        try:
            if not self.auth.is_authenticated:
                raise RuntimeError("Not authenticated with Strava")

            self.client.access_token = self.auth.get_access_token()
            self._update_state(message="Fetching activity list from Strava…")

            after_dt = None if deep else self.data_service.get_latest_activity_timestamp()
            limit = None if deep else 200

            strava_activities = []
            for sa in self.client.get_activities(after=after_dt, limit=limit):
                if time.time() > deadline:
                    raise TimeoutError("Sync timed out after 10 minutes")
                strava_activities.append(sa)
                if len(strava_activities) % 100 == 0:
                    self._update_state(
                        fetched=len(strava_activities),
                        message=f"Fetched {len(strava_activities)} activities…"
                    )

            self._update_state(fetched=len(strava_activities), message="Processing…")

            if not strava_activities:
                self._finish_state(added=0, skipped=0, message="Already up to date")
                return

            new_activities = [self._activity_to_dict(sa) for sa in strava_activities]
            added_count = self.data_service.add_activities(new_activities)
            skipped_count = len(new_activities) - added_count

            self._finish_state(
                added=added_count,
                skipped=skipped_count,
                message=(
                    f"Synced {added_count} new {'activity' if added_count == 1 else 'activities'}"
                    + (" (deep sync)" if deep else "")
                )
            )
            logger.info(f"Background sync complete: fetched={len(strava_activities)} added={added_count}")

        except Exception as exc:
            logger.error(f"Background sync failed: {exc}")
            with self._sync_lock:
                self._sync_state["status"] = "error"
                self._sync_state["error"] = str(exc)
                self._sync_state["message"] = f"Sync failed: {exc}"
                snapshot = dict(self._sync_state)
            self._record_sync_event(
                sync_kind="activities",
                status="error",
                deep=bool(snapshot.get("deep")),
                fetched=int(snapshot.get("fetched") or 0),
                added=int(snapshot.get("added") or 0),
                skipped=int(snapshot.get("skipped") or 0),
                message=snapshot.get("message"),
                error=str(exc),
                started_at=snapshot.get("started_at"),
                finished_at=datetime.utcnow().isoformat(),
            )

    def _update_state(self, **kwargs):
        with self._sync_lock:
            self._sync_state.update(kwargs)

    def _finish_state(self, added, skipped, message):
        with self._sync_lock:
            self._sync_state.update({
                "status": "done",
                "added": added,
                "skipped": skipped,
                "message": message,
            })
            snapshot = dict(self._sync_state)
        self._record_sync_event(
            sync_kind="activities",
            status="done",
            deep=bool(snapshot.get("deep")),
            fetched=int(snapshot.get("fetched") or 0),
            added=added,
            skipped=skipped,
            message=message,
            started_at=snapshot.get("started_at"),
            finished_at=datetime.utcnow().isoformat(),
        )

    def _record_sync_event(
        self,
        sync_kind: str,
        status: str,
        deep: bool = False,
        activity_id: Optional[int] = None,
        fetched: int = 0,
        added: int = 0,
        skipped: int = 0,
        message: Optional[str] = None,
        error: Optional[str] = None,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
    ) -> None:
        try:
            conn = get_conn()
            conn.execute("""
                INSERT INTO sync_log (
                    sync_kind, status, deep, activity_id, fetched, added, skipped,
                    message, error, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sync_kind,
                status,
                int(bool(deep)),
                activity_id,
                fetched,
                added,
                skipped,
                message,
                error,
                started_at,
                finished_at,
            ))
            conn.commit()
        except Exception as exc:
            logger.warning(f"Failed to record sync event: {exc}")

    # ── Legacy sync (kept for internal use / tests) ───────────────────────────

    def sync_activities(self, deep: bool = False) -> dict:

        """
        Fetch activity summaries from Strava and add them to the local dataset.
        
        Args:
            deep: If True, fetches up to 1000 activities (walking backwards) to fill gaps.
                  If False, only fetches activities since the most recent one.
        """
        if not self.auth.is_authenticated:
            return {"status": "error", "message": "Not authenticated with Strava"}

        try:
            self.client.access_token = self.auth.get_access_token()
            
            # 1. Determine fetch range
            if deep:
                logger.info("Starting deep sync (fetching FULL history)...")
                limit = None  # Fetch everything
                after_dt = None # Fetch from the beginning
            else:
                after_dt = self.data_service.get_latest_activity_timestamp()
                limit = 200
            
            # 2. Fetch from Strava
            strava_activities_iter = self.client.get_activities(after=after_dt, limit=limit)
            strava_activities = []
            
            # Use a list to exhaust the generator
            # For deep sync, this might take a while
            for sa in strava_activities_iter:
                strava_activities.append(sa)
                if deep and len(strava_activities) % 100 == 0:
                    logger.info(f"Fetched {len(strava_activities)} activities so far...")
            
            if not strava_activities:
                return {"status": "success", "synced_count": 0, "message": "Already up to date"}

            # 3. Convert to dicts for DataService
            new_activities = []
            for sa in strava_activities:
                activity_dict = self._activity_to_dict(sa)
                new_activities.append(activity_dict)

            # 4. Add to DataService (handles duplicate prevention by ID)
            added_count = self.data_service.add_activities(new_activities)
            skipped_count = len(new_activities) - added_count
            
            logger.info(f"Sync complete: Fetched {len(new_activities)}, Added {added_count}, Skipped {skipped_count}")
            
            return {
                "status": "success",
                "synced_count": added_count,
                "skipped_count": skipped_count,
                "fetched_count": len(new_activities),
                "message": f"Successfully synced {added_count} new activities" + (" (Deep sync)" if deep else ""),
                "activities": [a['name'] for a in new_activities[:5]]
            }

        except Exception as e:
            logger.error(f"Sync failed: {str(e)}")
            return {"status": "error", "message": str(e)}

    def get_strava_total_count(self) -> Optional[int]:
        """Get the total number of activities on Strava for this athlete (non-blocking)."""
        if not self.auth.is_authenticated:
            return None
            
        now = time.time()
        # If cache is valid, return it immediately
        if self._total_count_cache is not None and (now - self._total_count_timestamp) < self._CACHE_TTL:
            return self._total_count_cache

        # If we are already updating, don't start another thread
        if hasattr(self, '_is_updating_total') and self._is_updating_total:
            return self._total_count_cache

        # Start background update
        import threading
        def _update():
            self._is_updating_total = True
            try:
                self.client.access_token = self.auth.get_access_token()
                if hasattr(self.client, 'protocol') and hasattr(self.client.protocol, 'session'):
                    self.client.protocol.session.timeout = 5.0
                
                stats = self.client.get_athlete_stats()
                total = 0
                if stats.all_run_totals: total += stats.all_run_totals.count
                if stats.all_ride_totals: total += stats.all_ride_totals.count
                if stats.all_swim_totals: total += stats.all_swim_totals.count

                self._total_count_cache = total
                self._total_count_timestamp = time.time()
                logger.info(f"Updated Strava total count: {total}")
            except Exception as e:
                logger.error(f"Background total count update failed: {e}")
            finally:
                self._is_updating_total = False

        threading.Thread(target=_update, daemon=True).start()
        
        # Return whatever we have (even if expired or None)
        return self._total_count_cache

    def sync_activity_details(self, activity_id: int) -> dict:
        """Fetch granular splits for an activity using Strava streams, with fallback to native splits."""
        if not self.auth.is_authenticated:
            return {"status": "error", "message": "Not authenticated"}

        try:
            self.client.access_token = self.auth.get_access_token()

            # 1. Fetch detailed activity (includes native splits_standard)
            sa = self.client.get_activity(activity_id)

            # 2. Try stream-based splits first (better granularity for outdoor activities)
            splits = []
            types = ['time', 'distance', 'heartrate', 'altitude', 'cadence', 'velocity_smooth']
            streams = self.client.get_activity_streams(activity_id, types=types, resolution='high')

            if streams and 'distance' in streams:
                splits = self._process_streams_to_splits(activity_id, streams, sa)

            # 3. Fall back to Strava's native per-mile splits for indoor/trainer activities
            #    or when stream data is too sparse to produce useful splits.
            if not self._splits_are_usable(splits, sa):
                logger.info(f"Stream splits unusable for {activity_id}, trying native splits_standard")
                splits = self._process_native_splits_to_buckets(activity_id, sa)

            if not splits:
                return {"status": "error", "message": "No stream data available for this activity"}

            # 4. Save to CSV via DataService
            self.data_service.add_splits(splits)
            self._record_sync_event(
                sync_kind="activity_details",
                status="success",
                activity_id=activity_id,
                fetched=len(splits),
                added=len(splits),
                message=f"Successfully synced {len(splits)} splits for activity {activity_id}",
                started_at=datetime.utcnow().isoformat(),
                finished_at=datetime.utcnow().isoformat(),
            )
            
            return {
                "status": "success", 
                "message": f"Successfully synced {len(splits)} splits for activity {activity_id}",
                "count": len(splits)
            }
        except Exception as e:
            logger.error(f"Failed to sync details for {activity_id}: {e}")
            self._record_sync_event(
                sync_kind="activity_details",
                status="error",
                activity_id=activity_id,
                message=str(e),
                error=str(e),
                started_at=datetime.utcnow().isoformat(),
                finished_at=datetime.utcnow().isoformat(),
            )
            return {"status": "error", "message": str(e)}

    def _splits_are_usable(self, splits: List[dict], detailed_act) -> bool:
        """Return True if stream-based splits have meaningful time and distance data."""
        if not splits:
            return False
        total_time = sum(float(s.get('time_seconds') or 0) for s in splits)
        if total_time <= 0:
            return False
        # Check coverage: splits should account for at least 50% of the activity distance
        expected_dist = getattr(detailed_act, 'distance', None)
        if expected_dist is not None:
            dist_m = float(expected_dist.magnitude if hasattr(expected_dist, 'magnitude') else expected_dist)
            covered_miles = float(splits[-1].get('total_distance_miles') or 0)
            if dist_m > 0 and covered_miles < (dist_m / 1609.34) * 0.5:
                return False
        return len(splits) >= 2

    def _process_native_splits_to_buckets(self, activity_id: int, detailed_act) -> List[dict]:
        """Convert Strava's native per-mile splits_standard into 0.1-mile buckets.

        Used as a fallback for indoor/trainer activities where GPS stream data is
        unavailable or too sparse to produce useful splits.
        """
        native_splits = getattr(detailed_act, 'splits_standard', None) or []
        if not native_splits:
            return []

        name = getattr(detailed_act, 'name', 'Activity')
        date_str = detailed_act.start_date.strftime('%Y-%m-%d') if detailed_act.start_date else ''

        def _qty(val):
            """Extract float from stravalib Quantity or plain number."""
            if val is None:
                return None
            return float(val.magnitude if hasattr(val, 'magnitude') else val)

        results = []
        for sp in native_splits:
            split_num = int(getattr(sp, 'split', 1))
            time_secs = _qty(getattr(sp, 'elapsed_time', None)) or 0.0
            dist_m = _qty(getattr(sp, 'distance', None)) or 0.0
            avg_hr = _qty(getattr(sp, 'average_heartrate', None))
            avg_cadence = _qty(getattr(sp, 'average_cadence', None))
            avg_speed = _qty(getattr(sp, 'average_speed', None))
            elev_diff = _qty(getattr(sp, 'elevation_difference', None))

            dist_miles = dist_m / 1609.34
            buckets = max(1, round(dist_miles / 0.1))
            time_per_bucket = time_secs / buckets
            elev_per_bucket = max(0.0, elev_diff or 0.0) / buckets

            base_bucket = (split_num - 1) * 10

            for i in range(buckets):
                bucket_num = base_bucket + i + 1
                results.append({
                    '0.1_mile': bucket_num,
                    'time_seconds': round(time_per_bucket, 1),
                    'time_minutes': f"{int(time_per_bucket // 60):02d}:{int(time_per_bucket % 60):02d}",
                    'max_heartrate': avg_hr,
                    'avg_heartrate': avg_hr,
                    'avg_cadence': avg_cadence,
                    'avg_velocity': avg_speed,
                    'elevation_gain_meters': round(elev_per_bucket, 2),
                    'activity_id': activity_id,
                    'activity_name': name,
                    'total_distance_miles': round(bucket_num * 0.1, 1),
                    'date': date_str,
                    'id': activity_id,
                })

        return results

    def _process_streams_to_splits(self, activity_id, streams, detailed_act) -> List[dict]:
        """Convert raw GPS/sensor streams into 0.1-mile buckets."""
        # Convert streams to a DataFrame for easier processing
        data = {}
        for k, v in streams.items():
            data[k] = v.data
        
        df = pd.DataFrame(data)
        if 'distance' not in df.columns:
            return []
            
        # Convert distance to miles
        df['distance_miles'] = df['distance'] / 1609.34
        
        # Create 0.1 mile buckets
        df['bucket'] = (df['distance_miles'] / 0.1).astype(int) + 1
        
        # Max bucket (total distance in 0.1 mi increments)
        max_dist_miles = detailed_act.distance.magnitude / 1609.34 if hasattr(detailed_act.distance, 'magnitude') else float(detailed_act.distance) / 1609.34
        max_bucket = int(max_dist_miles / 0.1)
        
        splits = []
        name = getattr(detailed_act, 'name', 'Activity')
        date_str = detailed_act.start_date.strftime('%Y-%m-%d') if detailed_act.start_date else ''

        # Group by bucket and aggregate
        # We want the time difference for each bucket
        # and the average sensor values
        
        for b in range(1, max_bucket + 1):
            bucket_df = df[df['bucket'] == b]
            if bucket_df.empty:
                continue
            
            # Time spent in this bucket
            # (Last timestamp in bucket - First timestamp in bucket)
            # This is an approximation if the stream isn't perfectly dense
            time_secs = bucket_df['time'].max() - bucket_df['time'].min()
            
            # If a bucket has only 1 point, time_secs is 0. 
            # We can use the difference between buckets too, but this is simpler for now.
            if b > 1:
                prev_max_time = df[df['bucket'] == b-1]['time'].max()
                if pd.notna(prev_max_time):
                    time_secs = bucket_df['time'].max() - prev_max_time

            splits.append({
                '0.1_mile': b,
                'time_seconds': int(time_secs),
                'time_minutes': f"{int(time_secs // 60):02d}:{int(time_secs % 60):02d}",
                'max_heartrate': float(bucket_df['heartrate'].max()) if 'heartrate' in bucket_df.columns else None,
                'avg_heartrate': float(bucket_df['heartrate'].mean()) if 'heartrate' in bucket_df.columns else None,
                'avg_cadence': float(bucket_df['cadence'].mean()) if 'cadence' in bucket_df.columns else None,
                'avg_velocity': float(bucket_df['velocity_smooth'].mean()) if 'velocity_smooth' in bucket_df.columns else None,
                'elevation_gain_meters': float(max(0, bucket_df['altitude'].max() - bucket_df['altitude'].min())) if 'altitude' in bucket_df.columns else 0.0,
                'activity_id': activity_id,
                'activity_name': name,
                'total_distance_miles': round(b * 0.1, 1),
                'date': date_str,
                'id': activity_id
            })
            
        return splits

    def _activity_to_dict(self, sa: SummaryActivity) -> dict:
        """Convert stravalib Activity to a dictionary matching our CSV format."""
        
        def _to_float(val):
            if val is None: return 0.0
            try:
                # Handle pint Quantity objects (distance, speed, etc)
                if hasattr(val, 'num'): return float(val.num)
                if hasattr(val, 'magnitude'): return float(val.magnitude)
                return float(val)
            except (TypeError, ValueError):
                return 0.0

        def _to_seconds(val, label="field"):
            if val is None: return 0
            try:
                # In stravalib v2, Duration is an int subclass (seconds)
                return int(val)
            except (TypeError, ValueError):
                return 0

        map_dict = {}
        if hasattr(sa, 'map') and sa.map:
            map_dict = {
                'id': getattr(sa.map, 'id', None),
                'summary_polyline': getattr(sa.map, 'summary_polyline', None),
                'resource_state': getattr(sa.map, 'resource_state', None)
            }

        def _to_str(val):
            if val is None: return ''
            # Handle stravalib/pydantic RootModels (sa.type.root)
            if hasattr(val, 'root'): return str(val.root)
            return str(val)

        act_id = getattr(sa, 'id', None)
        name = getattr(sa, 'name', 'Unknown')
        dist = getattr(sa, 'distance', 0)
        m_time = getattr(sa, 'moving_time', None)
        e_time = getattr(sa, 'elapsed_time', None)
        
        # Try moving_time, then elapsed_time as fallback
        moving_secs = _to_seconds(m_time, "moving_time")
        elapsed_secs = _to_seconds(e_time, "elapsed_time")
        
        if moving_secs == 0 and elapsed_secs > 0:
            moving_secs = elapsed_secs

        if moving_secs == 0 and _to_float(dist) > 0:
            logger.info(f"Sync: Activity {act_id} ({name}) still has 0 moving_time. Dist: {_to_float(dist)}")

        # Use space instead of T for start_date to match existing CSV format
        start_date = getattr(sa, 'start_date', None)
        start_date_str = start_date.strftime('%Y-%m-%d %H:%M:%S+00:00') if start_date else None
        
        start_date_local = getattr(sa, 'start_date_local', None)
        start_date_local_str = start_date_local.isoformat() if start_date_local else None

        return {
            'id': act_id,
            'name': name,
            'distance': _to_float(dist),
            'moving_time': moving_secs,
            'elapsed_time': elapsed_secs,
            'total_elevation_gain': _to_float(getattr(sa, 'total_elevation_gain', 0)),
            'type': _to_str(getattr(sa, 'type', 'Run')) or _to_str(getattr(sa, 'sport_type', 'Run')),
            'sport_type': _to_str(getattr(sa, 'sport_type', 'Run')),
            'start_date': start_date_str,
            'start_date_local': start_date_local_str,
            'timezone': getattr(sa, 'timezone', None),
            'start_latlng': str(list(sa.start_latlng)) if getattr(sa, 'start_latlng', None) else "[]",
            'end_latlng': str(list(sa.end_latlng)) if getattr(sa, 'end_latlng', None) else "[]",
            'achievement_count': getattr(sa, 'achievement_count', 0),
            'kudos_count': getattr(sa, 'kudos_count', 0),
            'comment_count': getattr(sa, 'comment_count', 0),
            'athlete_count': getattr(sa, 'athlete_count', 0),
            'photo_count': getattr(sa, 'photo_count', 0),
            'map': str(map_dict),
            'trainer': bool(getattr(sa, 'trainer', False)),
            'commute': bool(getattr(sa, 'commute', False)),
            'manual': bool(getattr(sa, 'manual', False)),
            'private': bool(getattr(sa, 'private', False)),
            'flagged': bool(getattr(sa, 'flagged', False)),
            'gear_id': getattr(sa, 'gear_id', None),
            'average_speed': _to_float(getattr(sa, 'average_speed', 0)),
            'max_speed': _to_float(getattr(sa, 'max_speed', 0)),
            'average_cadence': getattr(sa, 'average_cadence', None),
            'average_watts': getattr(sa, 'average_watts', None),
            'max_watts': getattr(sa, 'max_watts', None),
            'weighted_average_watts': getattr(sa, 'weighted_average_watts', None),
            'kilojoules': getattr(sa, 'kilojoules', None),
            'device_watts': getattr(sa, 'device_watts', None),
            'has_heartrate': bool(getattr(sa, 'has_heartrate', False)),
            'average_heartrate': getattr(sa, 'average_heartrate', None),
            'max_heartrate': getattr(sa, 'max_heartrate', None),

            'elev_high': _to_float(getattr(sa, 'elev_high', None)),
            'elev_low': _to_float(getattr(sa, 'elev_low', None)),
            'pr_count': getattr(sa, 'pr_count', 0),
            'total_photo_count': getattr(sa, 'total_photo_count', 0),
            'has_kudoed': bool(getattr(sa, 'has_kudoed', False)),
        }



_sync_service: Optional[SyncService] = None

def get_sync_service() -> SyncService:
    global _sync_service
    if _sync_service is None:
        _sync_service = SyncService()
    return _sync_service

"""
Similarity engine — finds similar workouts using weighted feature scoring and GPS matching.
Robust against zero vectors and missing data.

Results are cached in the DataService analytics cache (TTL: 5 minutes).
"""
import numpy as np
import pandas as pd
import polyline
import logging
from typing import Optional, List, Dict
from sklearn.preprocessing import MinMaxScaler

from backend.services.data_service import get_data_service

logger = logging.getLogger(__name__)

def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate haversine distance in miles between two lat/lng points."""
    if any(v is None or np.isnan(v) for v in [lat1, lng1, lat2, lng2]):
        return 999.0
    R = 3959  # Earth radius in miles
    lat1, lng1, lat2, lng2 = map(np.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlng / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    return R * c

def get_route_waypoints(polyline_str: str, num_points: int = 5) -> List[tuple]:
    """Decode polyline and extract N distributed waypoints."""
    if not polyline_str or polyline_str == 'nan' or not isinstance(polyline_str, str):
        return []
    try:
        points = polyline.decode(polyline_str)
        if not points:
            return []
        
        # Extract points at regular intervals
        indices = np.linspace(0, len(points) - 1, num_points).astype(int)
        return [points[i] for i in indices]
    except Exception as e:
        logger.warning(f"Failed to decode polyline: {e}")
        return []

def find_similar_activities(
    activity_id: int,
    top_n: int = 5,
) -> List[dict]:
    """
    Find the top-N most similar activities to the given activity.

    Scores based on:
    - Distance (35%)
    - Pace (30%)
    - HR (15%)
    - Elevation (10%)
    - Duration (10%)

    Route matching is applied as a multiplicative factor (0.7x to 1.0x).
    Trainer/Indoor workouts skip route matching.

    Results are cached per (activity_id, top_n) for up to 5 minutes.
    """
    data_service = get_data_service()
    cache = data_service.get_analytics_cache()
    cache_key = f"similar:{activity_id}:{top_n}"

    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug(f"Similarity cache hit for activity {activity_id}")
        return cached

    # Load all activities as DataFrame then convert to dicts (avoids N+1 queries)
    df = data_service.get_activities_dataframe(limit=10_000)
    if df.empty:
        return []

    # IMPORTANT: Only fill NaN in numeric feature columns.
    # Do NOT fillna on the full DataFrame — that would destroy geo fields like
    # map_polyline and start_latlng (replacing them with 0), which breaks route matching
    # (treadmill runs get a neutral 1.0 multiplier, outdoor runs get 0.7x, flipping rankings).
    numeric_feature_cols = ['distance_miles', 'pace', 'average_heartrate', 'total_elevation_gain', 'moving_time_min']
    for col in numeric_feature_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    activities = [dict(row) for _, row in df.iterrows()]

    # Ensure native Python types for numeric fields to avoid JSON serialization errors.
    # Geo/string fields are left as-is so route matching can read them.
    for act in activities:
        act['id'] = int(act['id'])
        act['distance_miles'] = float(act['distance_miles'])
        act['pace'] = float(act['pace'])
        act['average_heartrate'] = float(act['average_heartrate'])
        act['total_elevation_gain'] = float(act['total_elevation_gain'])
        act['moving_time_min'] = float(act['moving_time_min'])
        act['trainer'] = bool(act['trainer'] or 0)

    target = next((a for a in activities if a['id'] == int(activity_id)), None)
    if not target:
        return []

    # Filter by type and exclude target
    same_type = [a for a in activities if a['type'] == target['type'] and a['id'] != target['id']]
    if not same_type:
        return []

    # 1. Prepare Feature Matrix
    features = ['distance_miles', 'pace', 'average_heartrate', 'total_elevation_gain', 'moving_time_min']
    all_to_process = [target] + same_type

    feat_matrix = np.array([
        [float(a.get(f) or 0) for f in features]
        for a in all_to_process
    ])
    feat_df = pd.DataFrame(feat_matrix, columns=features)


    # Impute missing values (pace, average_heartrate) with medians
    for col in ['pace', 'average_heartrate']:
        valid_vals = feat_df[feat_df[col] > 0][col]
        if not valid_vals.empty:
            feat_df.loc[feat_df[col] <= 0, col] = valid_vals.median()
        else:
            feat_df.loc[feat_df[col] <= 0, col] = 0.001 # Avoid absolute zero

    # 2. Normalize and compute weighted L1 distance
    scaler = MinMaxScaler()
    scaled_matrix = scaler.fit_transform(feat_df)
    
    target_vec = scaled_matrix[0]
    comparison_batch = scaled_matrix[1:]
    
    # Rebalanced weights
    # [dist, pace, hr, elev, duration]
    weights = np.array([0.35, 0.30, 0.15, 0.10, 0.10])
    
    # Calculate weighted penalties
    diffs = np.abs(comparison_batch - target_vec) * weights
    score_penalty = np.sum(diffs, axis=1) 
    base_scores = 1.0 - score_penalty

    # 3. Route matching factor
    is_indoor = target.get('trainer', False)
    target_waypoints = []
    target_start = None
    
    if not is_indoor:
        target_waypoints = get_route_waypoints(target.get('map_polyline'))
        target_start = _parse_latlng(target.get('start_latlng'))
    
    results = []
    for i, activity in enumerate(same_type):
        base_score = base_scores[i]
        
        # Determine route factor (0.7 to 1.0)
        route_factor = 0.0 # Component score for route
        
        act_is_indoor = bool(activity.get('trainer', False))
        if is_indoor and act_is_indoor:
            # Both indoor: route matching not applicable, neutral multiplier
            route_multiplier = 1.0
            route_factor = 1.0
        elif is_indoor != act_is_indoor:
            # One is indoor, one is outdoor — penalize this cross-type match heavily.
            # A treadmill run should NOT outrank an outdoor loop that shares the same route.
            route_multiplier = 0.5
            route_factor = 0.0
        else:
            # Outdoor matching
            match_points = 0
            
            # Start Proximity (Max 0.4 match points)
            act_start = _parse_latlng(activity.get('start_latlng'))
            if target_start and act_start:
                dist = haversine_distance(target_start[0], target_start[1], act_start[0], act_start[1])
                if dist < 0.1: match_points += 0.4
                elif dist < 0.5: match_points += 0.2
            
            # Waypoint Matching (Max 0.6 match points)
            if target_waypoints:
                act_waypoints = get_route_waypoints(activity.get('map_polyline'))
                if act_waypoints and len(act_waypoints) == len(target_waypoints):
                    waypoint_dists = [
                        haversine_distance(tw[0], tw[1], aw[0], aw[1])
                        for tw, aw in zip(target_waypoints, act_waypoints)
                    ]
                    avg_wp_dist = np.mean(waypoint_dists)
                    if avg_wp_dist < 0.15: match_points += 0.6
                    elif avg_wp_dist < 0.5: match_points += 0.3

            route_factor = min(1.0, match_points)
            # Route factor scales score between 0.7x (completely different) and 1.0x (identical)
            route_multiplier = 0.7 + (0.3 * route_factor)
        
        # Component scores for transparency
        feat_diffs = np.abs(comparison_batch[i] - target_vec)
        comp_scores = {
            'distance': round(float(max(0, 1.0 - feat_diffs[0])), 4),
            'pace': round(float(max(0, 1.0 - feat_diffs[1])), 4),
            'heartrate': round(float(max(0, 1.0 - feat_diffs[2])), 4),
            'elevation': round(float(max(0, 1.0 - feat_diffs[3])), 4),
            'duration': round(float(max(0, 1.0 - feat_diffs[4])), 4),
            'route': round(float(route_factor), 4),
            'base_score': round(float(base_score), 4)
        }
        
        final_score = base_score * route_multiplier
        import math
        f_score = float(final_score)
        if not math.isfinite(f_score):
            f_score = 0.0
            
        def safe_float(val):
            if val is None:
                return None
            try:
                f = float(val)
                return f if math.isfinite(f) and f > 0 else None
            except (ValueError, TypeError):
                return None

            
        # Return the full set of fields the frontend needs for radar/delta/comparison UI
        clean_act = {
            'id':                   int(activity.get('id', 0)),
            'name':                 str(activity.get('name') or ''),
            'type':                 str(activity.get('type') or ''),
            'date':                 str(activity.get('date') or ''),
            'start_date_local':     str(activity.get('start_date_local') or ''),
            'distance_miles':       float(activity.get('distance_miles') or 0.0),
            'pace':                 float(activity.get('pace') or 0.0),
            'moving_time_min':      float(activity.get('moving_time_min') or 0.0),
            'average_heartrate':    safe_float(activity.get('average_heartrate')),
            'total_elevation_gain': float(activity.get('total_elevation_gain') or 0.0),
            'average_cadence':      safe_float(activity.get('average_cadence')),

            'trainer':              bool(activity.get('trainer') or 0),
            'map_polyline':         str(activity.get('map_polyline') or '') or None,
        }
        
        results.append({
            'activity': clean_act,
            'similarity_score': round(f_score, 4),
            'match_percent': int(round(max(0, f_score) * 100)),
            'components': comp_scores
        })

    # Sort and return
    results.sort(key=lambda x: x['similarity_score'], reverse=True)
    result = results[:top_n]
    cache.set(cache_key, result)
    return result


def _parse_latlng(val) -> Optional[tuple]:
    """Parse a lat/lng value from multiple possible formats stored in SQLite."""
    if not val or val in ('None', '[]', 'nan', '', '0'):
        return None
    try:
        import ast
        if isinstance(val, str):
            parsed = ast.literal_eval(val)
        else:
            parsed = val

        # Standard format: [lat, lng]
        if isinstance(parsed, (list, tuple)) and len(parsed) >= 2:
            first = parsed[0]
            # Malformed pandas format: [('root', [lat, lng]), ...]
            if isinstance(first, tuple) and len(first) == 2 and isinstance(first[1], (list, tuple)):
                inner = first[1]
                if len(inner) >= 2:
                    return float(inner[0]), float(inner[1])
            # Normal format: [lat, lng] where both are numeric
            try:
                return float(first), float(parsed[1])
            except (TypeError, ValueError):
                pass
    except Exception:
        pass
    return None

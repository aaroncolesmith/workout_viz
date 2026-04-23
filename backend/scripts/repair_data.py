
import pandas as pd
import numpy as np
import os
from pathlib import Path
from difflib import SequenceMatcher

DATA_DIR = Path("/Users/aaronsmith/Code/workout_viz/data")
ACTIVITIES_PATH = DATA_DIR / "strava_activities.csv"

def string_similarity(a, b):
    return SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()

def heal_polylines():
    if not ACTIVITIES_PATH.exists():
        print("CSV not found.")
        return

    df = pd.read_csv(ACTIVITIES_PATH)
    
    # 1. Separate activities with and without polylines
    # standardizing 'missing' first
    df['map_polyline'] = df['map_polyline'].replace(['', '[]', 'nan'], np.nan)
    
    has_map = df[df['map_polyline'].notna()]
    missing_map = df[df['map_polyline'].isna()]
    
    print(f"Total: {len(df)} | Has Map: {len(has_map)} | Missing Map: {len(missing_map)}")
    
    repaired_count = 0
    
    # 2. Try to find a template for each missing map
    for idx, row in missing_map.iterrows():
        # Candidate filter: same type, similar distance (+/- 10%)
        dist = row['distance_miles']
        if pd.isna(dist) or dist == 0: continue
        
        candidates = has_map[
            (has_map['type'] == row['type']) & 
            (has_map['distance_miles'] >= dist * 0.9) & 
            (has_map['distance_miles'] <= dist * 1.1)
        ]
        
        if candidates.empty: continue
        
        # Best match by name similarity
        best_match = None
        best_score = 0
        
        for c_idx, c_row in candidates.iterrows():
            score = string_similarity(row['name'], c_row['name'])
            if score > best_score:
                best_score = score
                best_match = c_row
        
        # If we have a high confidence match (> 0.8), borrow the polyline
        if best_match is not None and best_score > 0.8:
            df.at[idx, 'map_polyline'] = best_match['map_polyline']
            # Also borrow start/end latlng if missing
            if pd.isna(row['start_latlng']) or row['start_latlng'] == '[]':
                df.at[idx, 'start_latlng'] = best_match['start_latlng']
            if pd.isna(row['end_latlng']) or row['end_latlng'] == '[]':
                df.at[idx, 'end_latlng'] = best_match['end_latlng']
            
            repaired_count += 1
            if repaired_count < 5: # Log first few
                print(f"Repaired '{row['name']}' ({row['date']}) using '{best_match['name']}' (Score: {best_score:.2f})")

    if repaired_count > 0:
        df.to_csv(ACTIVITIES_PATH, index=False)
        print(f"Successfully repaired {repaired_count} activities with missing GPS polylines.")
    else:
        print("No matches found to repair polylines.")

def heal_metrics():
    """
    If a run is missing cadence but the user has a consistent average,
    backfill with the runner's global median for that type.
    """
    df = pd.read_csv(ACTIVITIES_PATH)
    
    for mtype in ['Run', 'Ride']:
        mask = df['type'] == mtype
        if not mask.any(): continue
        
        # Calculate median from valid sensors
        cad_median = df[mask & df['average_cadence'].notna()]['average_cadence'].median()
        hr_median = df[mask & df['average_heartrate'].notna()]['average_heartrate'].median()
        
        if pd.notna(cad_median):
            missing_cad = mask & df['average_cadence'].isna()
            count = missing_cad.sum()
            df.loc[missing_cad, 'average_cadence'] = cad_median
            print(f"Backfilled {count} {mtype}s with median cadence: {cad_median:.1f}")
            
        if pd.notna(hr_median):
            missing_hr = mask & df['average_heartrate'].isna()
            count = missing_hr.sum()
            df.loc[missing_hr, 'average_heartrate'] = hr_median
            print(f"Backfilled {count} {mtype}s with median HR: {hr_median:.1f}")

    df.to_csv(ACTIVITIES_PATH, index=False)

if __name__ == "__main__":
    heal_polylines()
    heal_metrics()

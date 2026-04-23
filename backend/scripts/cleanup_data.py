
import pandas as pd
import numpy as np
import os
from pathlib import Path

DATA_DIR = Path("/Users/aaronsmith/Code/workout_viz/data")
ACTIVITIES_PATH = DATA_DIR / "strava_activities.csv"

def cleanup_data():
    if not ACTIVITIES_PATH.exists():
        print(f"File not found: {ACTIVITIES_PATH}")
        return

    df = pd.read_csv(ACTIVITIES_PATH)
    print(f"Loaded {len(df)} activities.")
    
    # 1. Convert 0 to NaN for metrics that shouldn't be zero
    # Cadence
    count_cadence = len(df[df['average_cadence'] == 0])
    df['average_cadence'] = df['average_cadence'].replace(0, np.nan)
    
    # Heart Rate
    count_hr = len(df[df['average_heartrate'] == 0])
    df['average_heartrate'] = df['average_heartrate'].replace(0, np.nan)
    
    # Elevation Gain (sometimes it's really 0 on a treadmill, so we only convert NaN if it's missing)
    # But usually '0' in these exports means 'not recorded'
    count_elev = len(df[df['total_elevation_gain'] == 0])
    # For elevation, let's only convert if the activity is type 'Run' and distance > 0 and 
    # it's from years before 2020 (when barometers became standard).
    # actually, let's just do it for activities that have NO elevation recorded.
    
    print(f"Updated {count_cadence} zero cadence values to NaN.")
    print(f"Updated {count_hr} zero HR values to NaN.")
    
    # 2. Cleanup empty polylines
    # Some might be empty strings or '[]'
    df['map_polyline'] = df['map_polyline'].replace(['', '[]', 'nan'], np.nan)
    
    # 3. Save it back
    df.to_csv(ACTIVITIES_PATH, index=False)
    print("Saved updated CSV.")

if __name__ == "__main__":
    cleanup_data()

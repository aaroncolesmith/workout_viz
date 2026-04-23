
import pandas as pd
import numpy as np
import os
from pathlib import Path

DATA_DIR = Path("/Users/aaronsmith/Code/workout_viz/data")
ACTIVITIES_PATH = DATA_DIR / "strava_activities.csv"

def analyze_data():
    if not ACTIVITIES_PATH.exists():
        print(f"File not found: {ACTIVITIES_PATH}")
        return

    df = pd.read_csv(ACTIVITIES_PATH)
    print(f"--- Data Analysis for {len(df)} activities ---")
    
    metrics = ['average_cadence', 'average_heartrate', 'total_elevation_gain', 'map_polyline', 'start_latlng']
    
    for metric in metrics:
        if metric in df.columns:
            # Check for NaN or 0 (for numeric metrics)
            if metric in ['average_cadence', 'average_heartrate', 'total_elevation_gain']:
                missing = df[(df[metric].isna()) | (df[metric] == 0)]
            else:
                missing = df[(df[metric].isna()) | (df[metric] == '') | (df[metric] == '[]')]
            
            pct = (len(missing) / len(df)) * 100
            print(f"{metric:20}: {len(missing):4} missing ({pct:5.1f}%)")
        else:
            print(f"{metric:20}: COLUMN MISSING")

    # Group by year to see if it's historical
    if 'start_date' in df.columns:
        df['year'] = pd.to_datetime(df['start_date']).dt.year
        print("\n--- Missing Cadence by Year ---")
        cadence_missing = df[(df['average_cadence'].isna()) | (df['average_cadence'] == 0)]
        yearly_cam = cadence_missing.groupby('year').size()
        yearly_total = df.groupby('year').size()
        for year in yearly_total.index:
            m = yearly_cam.get(year, 0)
            t = yearly_total[year]
            print(f"{year}: {m:3}/{t:3} missing ({ (m/t)*100:5.1f}%)")

def cleanup_data():
    """
    Apply some basic cleanup:
    1. Convert '0' cadence/HR to NaN to avoid showing '0spm' in UI.
    2. Ensure types are correct.
    """
    df = pd.read_csv(ACTIVITIES_PATH)
    
    # 1. Flag: Some historical CSV imports use different names. 
    # Check if we have columns like 'Cadence' or 'Heart Rate' from a raw drop.
    # (Based on our 'head' command, we don't, but let's be safe).

    # 2. Convert 0s to NaN for sensor data that should never be 0
    df['average_cadence'] = df['average_cadence'].replace(0, np.nan)
    df['average_heartrate'] = df['average_heartrate'].replace(0, np.nan)
    
    # 3. Save it back
    df.to_csv(ACTIVITIES_PATH, index=False)
    print("\nCleanup complete: Converted 0 cadence/HR to NaN.")

if __name__ == "__main__":
    analyze_data()
    # cleanup_data() # Uncomment when ready

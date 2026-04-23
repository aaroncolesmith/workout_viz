
import logging
import time
from backend.services.sync_service import get_sync_service
from backend.services.data_service import get_data_service

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def refetch():
    data_service = get_data_service()
    sync_service = get_sync_service()
    
    if not sync_service.auth.is_authenticated:
        print("Not authenticated with Strava. Please login first.")
        return

    # 1. Find low quality runs
    # Criteria: Type is Run, has ID, and (missing map OR missing cadence)
    df = data_service._activities_df
    if df is None or df.empty:
        print("No activities found in CSV.")
        return
        
    mask = (
        (df['type'] == 'Run') & 
        (df['id'].notna()) & 
        ( (df['map_polyline'].isna()) | (df['average_cadence'].isna()) | (df['average_cadence'] == 0) )
    )
    
    low_quality = df[mask].copy()
    print(f"Found {len(low_quality)} low quality runs with Strava IDs.")
    
    if low_quality.empty:
        return

    # Limit to 50 at a time to avoid heavy rate limiting
    to_refresh = low_quality.head(50)
    print(f"Refreshing details for {len(to_refresh)} activities...")

    updated_activities = []
    
    try:
        sync_service.client.access_token = sync_service.auth.get_access_token()
        
        for idx, row in to_refresh.iterrows():
            act_id = int(row['id'])
            print(f"Fetching {act_id} ({row['name']})...")
            
            try:
                # Get detailed activity
                detailed = sync_service.client.get_activity(act_id)
                # Convert to our dict format
                act_dict = sync_service._activity_to_dict(detailed)
                updated_activities.append(act_dict)
                
                # Sleep briefly to be nice to API
                time.sleep(0.5)
            except Exception as e:
                print(f"Failed to fetch {act_id}: {e}")
                if "Rate limit exceeded" in str(e):
                    break

        if updated_activities:
            print(f"Updating {len(updated_activities)} activities in local database...")
            data_service.update_activities(updated_activities)
            print("Done.")
        else:
            print("No activities were successfully updated.")

    except Exception as e:
        print(f"Critical error: {e}")

if __name__ == "__main__":
    refetch()

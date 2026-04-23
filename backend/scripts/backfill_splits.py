"""
Backfill missing splits for runs that don't have granular split data.
Runs via Strava API stream fetch for each activity without splits.
Usage: python3 backend/scripts/backfill_splits.py
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.services.database import init_db, get_conn
from backend.services.data_service import get_data_service, DB_PATH
from backend.services.sync_service import get_sync_service

init_db(DB_PATH)

conn = get_conn()
rows = conn.execute("""
    SELECT a.id, a.name, a.date, a.distance_miles 
    FROM activities a
    WHERE a.type = 'Run'
      AND a.id NOT IN (SELECT DISTINCT activity_id FROM splits)
      AND a.moving_time > 0
      AND a.distance_miles > 0.5
    ORDER BY a.date DESC
""").fetchall()

print(f"Found {len(rows)} runs without splits")
if not rows:
    print("Nothing to backfill.")
    sys.exit(0)

sync = get_sync_service()
success = 0
failed = 0
for row in rows:
    aid = row['id']
    name = row['name']
    date = row['date']
    print(f"  Fetching {aid} — {name} ({date}) ...", end=' ', flush=True)
    result = sync.sync_activity_details(aid)
    if result.get('status') == 'success' and result.get('splits_count', 0) > 0:
        print(f"✓ {result['splits_count']} splits")
        success += 1
    else:
        print(f"✗ {result.get('message', result.get('status'))}")
        failed += 1

print(f"\nDone: {success} succeeded, {failed} failed")

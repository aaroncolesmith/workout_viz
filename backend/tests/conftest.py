"""
Multi-tenant test harness (QA-1).

The seeded_backend fixture:
  - Injects a random DB_ENCRYPTION_MASTER_KEY so encryption is exercised.
  - Registers a device identity in a fresh identity DB.
  - Provisions that device's encrypted workouts DB.
  - Instantiates DataService(user_id) bound to the test DB.
  - Seeds 4 activities (3 runs, 1 ride) identical to the prior fixture.
"""
import importlib
import os
import secrets
from pathlib import Path

import pytest


@pytest.fixture
def seeded_backend(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Inject secrets so key_provider.get_master() works without a real env
    master_key = secrets.token_hex(32)
    monkeypatch.setenv("DB_ENCRYPTION_MASTER_KEY", master_key)
    monkeypatch.setenv("DATA_DIR", str(data_dir))

    # Reload all service modules so they pick up the fresh env and a clean state
    import backend.services.key_provider as key_provider_mod
    import backend.services.database as database
    import backend.services.identity_db as identity_db_mod
    import backend.services.data_service as data_service_mod
    import backend.services.pca_service as pca_service
    import backend.services.similarity_service as similarity_service

    # Clear LRU caches that memoize secrets
    key_provider_mod.get_master.cache_clear()

    database = importlib.reload(database)
    key_provider_mod = importlib.reload(key_provider_mod)
    identity_db_mod = importlib.reload(identity_db_mod)
    data_service_mod = importlib.reload(data_service_mod)
    pca_service = importlib.reload(pca_service)
    similarity_service = importlib.reload(similarity_service)

    # Boot identity DB
    identity_db_mod.init_identity_db(data_dir)

    # Register a test device identity
    user_id = identity_db_mod.register_device(data_dir=data_dir)

    # DataService bound to that user's encrypted DB
    service = data_service_mod.DataService(user_id, data_dir=data_dir)

    # Seed 4 activities
    service.add_activities([
        {
            "id": 101,
            "name": "Tempo Run",
            "type": "Run",
            "sport_type": "Run",
            "start_date": "2026-03-01T15:00:00Z",
            "start_date_local": "2026-03-01T07:00:00",
            "distance": 8046.72,
            "moving_time": 2400,
            "elapsed_time": 2460,
            "total_elevation_gain": 80.0,
            "average_speed": 3.3528,
            "average_heartrate": 155.0,
            "max_heartrate": 170.0,
            "average_cadence": 168.0,
            "has_heartrate": True,
            "trainer": False,
            "start_latlng": [37.77, -122.43],
            "end_latlng": [37.78, -122.42],
            "map": {"summary_polyline": "a~l~Fjk~uOwHJy@P"},
        },
        {
            "id": 102,
            "name": "Progression Run",
            "type": "Run",
            "sport_type": "Run",
            "start_date": "2026-03-03T15:00:00Z",
            "start_date_local": "2026-03-03T07:00:00",
            "distance": 8200.00,
            "moving_time": 2460,
            "elapsed_time": 2520,
            "total_elevation_gain": 85.0,
            "average_speed": 3.3333,
            "average_heartrate": 157.0,
            "max_heartrate": 172.0,
            "average_cadence": 169.0,
            "has_heartrate": True,
            "trainer": False,
            "start_latlng": [37.7705, -122.4305],
            "end_latlng": [37.7805, -122.4205],
            "map": {"summary_polyline": "a~l~Fjk~uOwHJy@P"},
        },
        {
            "id": 103,
            "name": "Long Run",
            "type": "Run",
            "sport_type": "Run",
            "start_date": "2026-03-05T15:00:00Z",
            "start_date_local": "2026-03-05T07:00:00",
            "distance": 16093.44,
            "moving_time": 5400,
            "elapsed_time": 5520,
            "total_elevation_gain": 220.0,
            "average_speed": 2.9803,
            "average_heartrate": 148.0,
            "max_heartrate": 162.0,
            "average_cadence": 164.0,
            "has_heartrate": True,
            "trainer": False,
            "start_latlng": [37.8, -122.45],
            "end_latlng": [37.86, -122.39],
            "map": {"summary_polyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
        },
        {
            "id": 104,
            "name": "Easy Ride",
            "type": "Ride",
            "sport_type": "Ride",
            "start_date": "2026-03-07T15:00:00Z",
            "start_date_local": "2026-03-07T07:00:00",
            "distance": 32186.88,
            "moving_time": 3600,
            "elapsed_time": 3660,
            "total_elevation_gain": 300.0,
            "average_speed": 8.9408,
            "average_heartrate": 140.0,
            "max_heartrate": 155.0,
            "average_cadence": 88.0,
            "has_heartrate": True,
            "trainer": False,
            "start_latlng": [37.71, -122.51],
            "end_latlng": [37.72, -122.5],
            "map": {"summary_polyline": "cxl_cBnnqgVo}@n}@"},
        },
    ])

    yield {
        "service":                 service,
        "user_id":                 user_id,
        "data_dir":                data_dir,
        "data_service_module":     data_service_mod,
        "pca_service_module":      pca_service,
        "similarity_service_module": similarity_service,
        "database_module":         database,
        "identity_db_module":      identity_db_mod,
        "db_path":                 service.db_path,
    }

    # Cleanup: close all connections for this user's DB
    try:
        database.close_conn(service.db_path)
    except Exception:
        pass

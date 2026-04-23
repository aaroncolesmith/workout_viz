import time

from backend.services.strava_auth import StravaAuthService


def test_data_service_get_activities_filters_and_paginates(seeded_backend):
    service = seeded_backend["service"]

    activities, total = service.get_activities(activity_type="Run", limit=2, offset=0)

    assert total == 3
    assert len(activities) == 2
    assert [activity["id"] for activity in activities] == [103, 102]
    assert all(activity["type"] == "Run" for activity in activities)


def test_find_similar_activities_returns_closest_run_first(seeded_backend):
    similar = seeded_backend["similarity_service_module"].find_similar_activities(101, top_n=2)

    assert len(similar) == 2
    assert similar[0]["activity"]["id"] == 102
    assert similar[0]["similarity_score"] >= similar[1]["similarity_score"]
    assert similar[0]["components"]["route"] >= 0.0


def test_get_activity_pca_returns_coordinates_for_run_activities(seeded_backend):
    pca = seeded_backend["pca_service_module"].get_activity_pca(activity_type="Run")

    assert len(pca["activities"]) == 3
    assert len(pca["loadings"]) == 6
    assert len(pca["variance_ratio"]) == 2
    assert all("pca_x" in activity and "pca_y" in activity for activity in pca["activities"])


def test_strava_auth_service_refreshes_expired_token(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    service = StravaAuthService()
    service._token_data = {
        "access_token": "old-token",
        "refresh_token": "refresh-me",
        "expires_at": time.time() - 10,
    }

    def fake_refresh():
        service._token_data = {
            "access_token": "new-token",
            "refresh_token": "refresh-me",
            "expires_at": time.time() + 3600,
        }
        return service._token_data

    monkeypatch.setattr(service, "refresh_token", fake_refresh)

    assert service.get_access_token() == "new-token"

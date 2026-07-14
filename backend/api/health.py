"""
Health metrics API (BIO-5 / BIO-6) — daily biometric trends and comparisons.

    GET /api/health/summary            today's snapshot of every metric with data
    GET /api/health/metrics/{metric}   daily series + rolling means + comparison

Results are cached in the per-user analytics _TTLCache and flushed whenever
the metrics ingest endpoint writes.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.deps import get_current_user
from backend.models import schemas
from backend.services import health_metrics_service
from backend.services.data_service import get_data_service

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/summary", response_model=schemas.HealthSummaryResponse)
def health_summary(user_id: str = Depends(get_current_user)):
    svc = get_data_service(user_id)
    cache = svc.get_analytics_cache()
    cached = cache.get("health:summary")
    if cached is not None:
        return cached
    result = health_metrics_service.get_health_summary(svc._conn())
    cache.set("health:summary", result)
    return result


@router.get("/metrics/{metric}", response_model=schemas.HealthMetricSeriesResponse)
def health_metric_series(
    metric: str,
    days: int = Query(90, ge=7, le=3650),
    user_id: str = Depends(get_current_user),
):
    if metric not in health_metrics_service.KNOWN_METRICS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown metric '{metric}'. Known: "
                   f"{sorted(health_metrics_service.KNOWN_METRICS)}",
        )
    svc = get_data_service(user_id)
    cache = svc.get_analytics_cache()
    cache_key = f"health:series:{metric}:{days}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    result = health_metrics_service.get_metric_series(svc._conn(), metric, days=days)
    cache.set(cache_key, result)
    return result

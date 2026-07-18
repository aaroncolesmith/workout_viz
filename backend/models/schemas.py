"""
Pydantic models for API request/response schemas.
"""
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any


class ActivitySummary(BaseModel):
    """Lightweight activity for list views."""
    id: int
    name: str
    type: str
    sport_type: str
    distance_miles: float
    moving_time_min: float
    elapsed_time_min: float
    pace: Optional[float] = None
    average_speed: float
    average_heartrate: Optional[float] = None
    max_heartrate: Optional[float] = None
    total_elevation_gain: float
    date: str
    start_date: str
    has_heartrate: bool = False
    start_latlng: Optional[str] = None
    end_latlng: Optional[str] = None
    source: Optional[str] = 'strava'


class ActivityDetail(ActivitySummary):
    """Full activity detail with all fields."""
    moving_time_hr: Optional[float] = None
    elapsed_time_hours: Optional[float] = None
    average_cadence: Optional[float] = None
    average_watts: Optional[float] = None
    max_watts: Optional[float] = None
    elev_high: Optional[float] = None
    elev_low: Optional[float] = None
    map_polyline: Optional[str] = None
    trainer: bool = False
    rolling_avg_speed: Optional[float] = None
    rolling_avg_distance: Optional[float] = None


class ActivityListResponse(BaseModel):
    activities: List[ActivitySummary]
    total: int
    limit: int
    offset: int


class Split(BaseModel):
    """0.1-mile split data."""
    split_number: float
    time_seconds: float
    time_minutes: Optional[str] = None
    max_heartrate: Optional[float] = None
    avg_heartrate: Optional[float] = None
    elevation_gain_meters: Optional[float] = None
    activity_id: int
    activity_name: str
    total_distance_miles: Optional[float] = None


class SplitsResponse(BaseModel):
    splits: List[Split]
    count: int


class FastestSegment(BaseModel):
    """Fastest segment summary for a given distance."""
    activity_id: int
    activity_name: str
    distance_miles: float
    fastest_time_seconds: float
    fastest_time_minutes: str
    start_mile: Optional[float] = None
    end_mile: Optional[float] = None
    avg_heartrate_fastest: Optional[float] = None
    elevation_gain_fastest_meters: Optional[float] = None


class SummarySegmentsResponse(BaseModel):
    segments: List[FastestSegment]
    count: int


class RollingFastestSegment(BaseModel):
    label: str
    distance_miles: float
    time_seconds: float
    time_str: str
    pace_str: str
    start_mile: Optional[float] = None
    end_mile: Optional[float] = None
    avg_hr: Optional[float] = None


class RollingFastestSegmentsResponse(BaseModel):
    segments: List[RollingFastestSegment]


class OverviewStats(BaseModel):
    """Dashboard overview statistics."""
    total_activities: int
    total_miles: float
    total_hours: float
    avg_pace: Optional[float] = None
    avg_heartrate: Optional[float] = None
    activity_types: Dict[str, int]
    recent_activities: List[ActivitySummary]
    strava_total_count: int = 0


class ActivityTypesResponse(BaseModel):
    types: List[str]


class SimilarActivityPayload(BaseModel):
    id: int
    name: str
    type: str
    date: str
    start_date_local: str
    distance_miles: float
    pace: float
    moving_time_min: float
    average_heartrate: Optional[float] = None
    total_elevation_gain: float
    average_cadence: Optional[float] = None
    trainer: bool
    map_polyline: Optional[str] = None


class SimilarActivity(BaseModel):
    """Activity with similarity score."""
    activity: SimilarActivityPayload
    similarity_score: float
    match_percent: int
    components: Dict[str, float]


class SimilarActivitiesResponse(BaseModel):
    similar: List[SimilarActivity]
    count: int


class ActivityFilter(BaseModel):
    """Filters for activity queries."""
    type: Optional[str] = None
    sport_type: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    min_distance: Optional[float] = None
    max_distance: Optional[float] = None
    limit: int = 50
    offset: int = 0


class CompareRequest(BaseModel):
    """Request body for comparing activities."""
    activity_ids: List[int]


class ComparisonItem(BaseModel):
    activity: ActivityDetail
    splits: List[Split]
    summary: List[FastestSegment]


class CompareResponse(BaseModel):
    comparisons: List[ComparisonItem]
    count: int


class TrendPoint(BaseModel):
    date: str
    name: str
    type: str
    sport_type: str
    distance_miles: Optional[float] = None
    pace: Optional[float] = None
    average_speed: Optional[float] = None
    average_heartrate: Optional[float] = None
    max_heartrate: Optional[float] = None
    total_elevation_gain: Optional[float] = None
    moving_time_min: Optional[float] = None
    rolling_avg_speed: Optional[float] = None
    rolling_avg_distance: Optional[float] = None


class TrendsResponse(BaseModel):
    data: List[TrendPoint]
    count: int


class SegmentTrendPoint(BaseModel):
    date: str
    activity_id: int
    activity_name: str
    time_seconds: float
    time_str: str
    pace_str: str
    avg_heartrate: Optional[float] = None


class SegmentTrendResponse(BaseModel):
    data: List[SegmentTrendPoint]
    distance_miles: float
    label: str


class CalendarDay(BaseModel):
    date: str
    count: int
    miles: float
    minutes: float
    type: str


class CalendarResponse(BaseModel):
    days: List[CalendarDay]
    months: int


class PCAPoint(BaseModel):
    id: int
    name: str
    date: str
    type: str
    distance_miles: float
    pace: float
    average_heartrate: float
    pca_x: float
    pca_y: float
    cluster: int


class PCALoading(BaseModel):
    feature: str
    pc1: float
    pc2: float


class PCAResponse(BaseModel):
    activities: List[PCAPoint]
    loadings: List[PCALoading]
    variance_ratio: List[float]


class SyncStatusResponse(BaseModel):
    status: str
    message: Optional[str] = None
    fetched: Optional[int] = None
    added: Optional[int] = None
    skipped: Optional[int] = None
    count: Optional[int] = None
    deep: Optional[bool] = None
    started_at: Optional[str] = None
    error: Optional[str] = None


class SyncStartResponse(SyncStatusResponse):
    pass


class AuthStatusResponse(BaseModel):
    configured: bool
    authenticated: bool
    auth_url: Optional[str] = None
    local_count: int
    strava_total_count: int


class AuthUrlResponse(BaseModel):
    url: str


class AuthCallbackResponse(BaseModel):
    status: str
    athlete: Dict[str, Any]


class CacheBucketStats(BaseModel):
    total_entries: int
    live_entries: int
    ttl_seconds: int


class CacheStatusResponse(BaseModel):
    overview: CacheBucketStats
    trends: CacheBucketStats
    calendar: CacheBucketStats
    analytics: CacheBucketStats


class CacheFlushResponse(BaseModel):
    status: str


class FitnessPoint(BaseModel):
    date: str
    ctl: float          # Chronic Training Load (fitness, 42-day EMA)
    atl: float          # Acute Training Load (fatigue, 7-day EMA)
    tsb: float          # Training Stress Balance (form = CTL - ATL)
    daily_stress: float # Raw TRIMP / estimated load for this day


class FitnessResponse(BaseModel):
    data: List[FitnessPoint]
    count: int
    resting_hr: Optional[float] = None
    max_hr: Optional[float] = None


class ReadinessFactor(BaseModel):
    name:   str                # Training load | HRV | Resting HR | Sleep
    score:  int                # 0-100 for this factor alone
    weight: float
    detail: str                # human-readable "why" for this factor


class ReadinessResponse(BaseModel):
    score: int                 # 0-100 (blended)
    zone: str                  # peak | ready | moderate | easy | recovery
    recommendation: str
    ctl: float
    atl: float
    tsb: float
    factors: List[ReadinessFactor] = []
    why: Optional[str] = None  # one-line explanation joining the factors
    computed_at: Optional[str] = None  # UTC ISO timestamp of this computation


class ReadinessHistoryPoint(BaseModel):
    date:         str
    score:        int
    zone:         str
    load_score:   int
    daily_stress: float
    hard_on_red:  bool         # trained hard on a sub-30 morning


class ReadinessHistoryResponse(BaseModel):
    data: List[ReadinessHistoryPoint]
    count: int


class EfficiencyPoint(BaseModel):
    activity_id: int
    date:        str
    name:        str
    ef:          float          # meters/min per bpm
    ef_rolling:  float
    pace:        float
    avg_hr:      float
    decoupling:  Optional[float] = None   # % EF decay first→second half


class EfficiencyTrendResponse(BaseModel):
    points:        List[EfficiencyPoint]
    verdict:       Optional[str] = None
    rolling_days:  int
    activity_type: str


class EffectCohort(BaseModel):
    label:        str
    n:            int
    adj_pace:     float
    adj_pace_str: str


class EffectFinding(BaseModel):
    factor:       str          # sleep | hrv | rhr | rest
    headline:     str
    delta_sec_mi: float
    confidence:   str          # high | moderate
    cohorts:      List[EffectCohort]


class EffectFindingsResponse(BaseModel):
    findings:      List[EffectFinding]
    runs_analyzed: int
    ref_hr:        Optional[float] = None


class DigestSection(BaseModel):
    kind:  str                 # volume | efficiency | best_moment | body | insight
    title: str
    text:  str


class DigestStats(BaseModel):
    activities: int
    miles:      float
    hours:      float
    prev_miles: float


class WeeklyDigestResponse(BaseModel):
    week_start: str
    week_end:   str
    stats:      DigestStats
    sections:   List[DigestSection]


class PREvent(BaseModel):
    activity_id: int
    activity_name: str
    activity_type: Optional[str] = None
    date: str
    distance_label: str        # "5K", "1 Mile", etc.
    distance_miles: float
    time_seconds: float
    time_str: str
    pace_str: str
    previous_best_seconds: Optional[float] = None  # None = first-ever effort


class PRsResponse(BaseModel):
    prs: List[PREvent]
    count: int


class InsightResponse(BaseModel):
    """Structured post-workout insights for a single activity."""
    headline:        Optional[str]       = None
    pr:              Optional[Dict[str, Any]] = None
    segment_ranking: Optional[Dict[str, Any]] = None
    hr_efficiency:   Optional[Dict[str, Any]] = None
    split_quality:   Optional[Dict[str, Any]] = None
    pace_trend:      Optional[Dict[str, Any]] = None
    volume_context:  Optional[Dict[str, Any]] = None
    comparison:      Optional[Dict[str, Any]] = None  # CMP-3: verdict summary


class UserSetting(BaseModel):
    key: str
    value: str


# ── Training Blocks ───────────────────────────────────────────────────────────

class PaceTrend(BaseModel):
    delta_sec_per_mi: float
    improving: bool
    early_pace: float
    recent_pace: float


class PaceSpark(BaseModel):
    date: str
    pace: float


class RouteActivity(BaseModel):
    id: int
    name: str
    date: str
    distance_miles: float
    pace: float
    pace_str: str
    average_heartrate: Optional[float] = None
    total_elevation_gain: float
    duration_str: str
    moving_time_min: Optional[float] = None
    similarity_score: float


class Route(BaseModel):
    id: int
    name: str
    activity_type: str
    representative_polyline: Optional[str] = None
    avg_distance_miles: float
    activity_count: int
    centroid_lat: Optional[float] = None
    centroid_lng: Optional[float] = None
    avg_pace: float
    avg_pace_str: str
    best_pace: float
    best_pace_str: str
    avg_hr: Optional[float] = None
    first_run: Optional[str] = None
    last_run: Optional[str] = None
    pace_trend: Optional[PaceTrend] = None
    pace_spark: List[PaceSpark] = []


class RoutesResponse(BaseModel):
    routes: List[Route]
    count: int
    built: bool


class RouteDetailResponse(BaseModel):
    route: Route
    activities: List[RouteActivity]


class RouteBuildResponse(BaseModel):
    status: str
    routes_found: int
    activities_clustered: int


class PredictionSource(BaseModel):
    distance_miles:  float
    distance_label:  str
    time_sec:        float
    time_str:        str
    pace_str:        str
    activity_id:     int
    activity_name:   str
    date:            str
    days_old:        int


class RacePrediction(BaseModel):
    target_distance_miles: float
    target_label:          str
    predicted_time_sec:    float
    predicted_time_str:    str
    predicted_pace_str:    str
    low_time_str:          str
    high_time_str:         str
    confidence:            str   # high | medium | low
    form_multiplier:       float
    source:                PredictionSource


class RacePredictionsResponse(BaseModel):
    predictions: List[RacePrediction]
    activity_type: str
    days: int


class TrainingBlockCreate(BaseModel):
    name: str
    block_type: str = 'base'   # base | build | peak | taper | race
    start_date: str            # YYYY-MM-DD
    end_date: str              # YYYY-MM-DD
    notes: Optional[str] = None


class TrainingBlockUpdate(BaseModel):
    name: Optional[str] = None
    block_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None


class BlockMetrics(BaseModel):
    """Aggregated stats for activities within a block."""
    activity_count: int
    run_count: int
    total_miles: float
    avg_weekly_miles: float
    avg_pace: Optional[float] = None       # runs only, min/mi
    avg_hr: Optional[float] = None
    total_elevation_ft: float
    ctl_start: Optional[float] = None      # CTL on first day of block
    ctl_end: Optional[float] = None        # CTL on last day of block
    ctl_delta: Optional[float] = None      # ctl_end - ctl_start
    tsb_start: Optional[float] = None      # form going into block


class BlockDelta(BaseModel):
    """Delta vs the previous block of same type."""
    pace_delta: Optional[float] = None         # sec/mi improvement (negative = faster)
    pace_delta_str: Optional[str] = None
    volume_delta_pct: Optional[float] = None   # % change in avg weekly miles
    hr_delta: Optional[float] = None           # bpm change


class TrainingBlock(BaseModel):
    id: int
    name: str
    block_type: str
    start_date: str
    end_date: str
    notes: Optional[str] = None
    created_at: str
    metrics: BlockMetrics
    delta: Optional[BlockDelta] = None     # vs previous block of same type


class TrainingBlocksResponse(BaseModel):
    blocks: List[TrainingBlock]
    count: int


# ── Device identity schemas ────────────────────────────────────────────────────

class DeviceRegisterResponse(BaseModel):
    device_token: str


class RootResponse(BaseModel):
    app: str
    version: str
    docs: str


class HealthResponse(BaseModel):
    status: str


class GenericMessageResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


# ── Apple Health Import ───────────────────────────────────────────────────

class ImportStartResponse(BaseModel):
    status: str   # started | already_running


class ImportStatusResponse(BaseModel):
    status:     str            # idle | running | done | error
    message:    str = ''
    parsed:     int = 0
    added:      int = 0
    skipped:    int = 0
    failed:     int = 0
    started_at: Optional[str] = None
    error:      Optional[str] = None


# ── Daily health metrics (BIO) ─────────────────────────────────────────────

class BaselineBand(BaseModel):
    mean:  float
    lower: float
    upper: float


class HealthMetricComparison(BaseModel):
    metric:        str
    label:         str
    unit:          str
    date:          str                      # day the snapshot is anchored at
    today:         float
    vs_yesterday:  Optional[float] = None
    vs_7d_avg:     Optional[float] = None
    vs_30d_avg:    Optional[float] = None
    vs_365d_avg:   Optional[float] = None
    avg_7d:        Optional[float] = None
    avg_30d:       Optional[float] = None
    avg_365d:      Optional[float] = None
    baseline_band: Optional[BaselineBand] = None
    out_of_band:   bool = False
    spark_30d:     List[float] = []         # 7d rolling mean, last 30 days


class HealthMetricPoint(BaseModel):
    date:        str
    value:       float
    rolling_7d:  Optional[float] = None
    rolling_30d: Optional[float] = None


class HealthMetricSeriesResponse(BaseModel):
    metric:     str
    label:      str
    unit:       str
    days:       int
    points:     List[HealthMetricPoint]
    comparison: Optional[HealthMetricComparison] = None


class HealthSummaryResponse(BaseModel):
    metrics: List[HealthMetricComparison]


# ── Post-workout comparison (CMP) ──────────────────────────────────────────

class ComparisonCohort(BaseModel):
    kind:     str                      # route | similar | distance
    label:    str                      # "7 previous runs on Riverside Loop"
    route_id: Optional[int] = None
    size:     int


class ComparisonDeltas(BaseModel):
    pace_vs_avg_sec_mi:  Optional[float] = None   # negative = faster than avg
    pace_vs_best_sec_mi: Optional[float] = None
    hr_vs_avg_bpm:       Optional[float] = None
    time_vs_avg_sec:     Optional[float] = None
    time_vs_best_sec:    Optional[float] = None


class RelativeEffort(BaseModel):
    trimp:      float
    percentile: float                  # 0-100 of trailing-90d efforts
    rank:       int
    of:         int
    label:      str


class ComparisonHistoryPoint(BaseModel):
    activity_id:  int
    date:         Optional[str] = None
    time_seconds: Optional[float] = None
    pace:         Optional[float] = None
    is_current:   bool = False


class ComparisonResponse(BaseModel):
    activity_id: int
    cohort:      Optional[ComparisonCohort] = None
    rank:        Optional[int] = None
    rank_of:     Optional[int] = None
    rank_metric: Optional[str] = None  # time | pace
    efficiency:  Optional[str] = None  # breakthrough | pushed | easier | …
    verdict:     Optional[str] = None
    deltas:      Optional[ComparisonDeltas] = None
    effort:      Optional[RelativeEffort] = None
    history:     List[ComparisonHistoryPoint] = []

"""
PCA Service — handles dimensionality reduction and clustering for activity visualization.

Results are cached in the DataService analytics cache (TTL: 5 minutes).
Cache is automatically invalidated when new activities are synced.
"""
import pandas as pd
import numpy as np
import logging
from typing import Dict
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

from backend.services.data_service import get_data_service

logger = logging.getLogger(__name__)


def get_activity_pca(activity_type: str = "Run") -> Dict:
    """
    Run PCA on all activities of a given type.
    Returns coordinates, clusters, and feature loadings.
    Result is memoised in the analytics TTL cache.
    """
    data_service = get_data_service()
    cache = data_service.get_analytics_cache()
    cache_key = f"pca:{activity_type}"

    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug(f"PCA cache hit for type={activity_type}")
        return cached

    df = data_service.get_activities_dataframe(activity_type=activity_type, limit=10_000)

    if df.empty or len(df) < 3:
        return {"activities": [], "loadings": [], "clusters": []}

    features = [
        "distance_miles", "pace", "average_heartrate",
        "total_elevation_gain", "moving_time_min", "average_cadence",
    ]

    # Extract feature matrix and metadata separately to keep things clean.
    # fillna(0) handles numeric NaN/None globally.
    df_clean = df.fillna(0)
    
    # We build the feature matrix directly from the clean DF
    X = df_clean[features].values
    feat_df = pd.DataFrame(X, columns=features)

    # Metadata — convert to dicts, handling Pydantic-incompatible types (like timestamp-like strings)
    metadata = []
    for _, row in df_clean.iterrows():
        metadata.append({
            "id":              int(row["id"]),
            "name":            str(row.get("name") or ""),
            "date":            str(row.get("date") or ""),
            "type":            str(row.get("type") or ""),
            "distance_miles":  float(row["distance_miles"]),
            "pace":            float(row["pace"]),
            "average_heartrate": float(row["average_heartrate"]),
        })

    # Impute zeros with column means
    for col in feat_df.columns:
        valid = feat_df[feat_df[col] > 0][col]
        feat_df.loc[feat_df[col] == 0, col] = valid.mean() if not valid.empty else 0.001

    # Scale → PCA → cluster
    # CRITICAL: Clean any NaN/inf before math
    feat_df = feat_df.fillna(0)
    X_clean = np.nan_to_num(feat_df.values)
    
    scaler     = StandardScaler()
    scaled     = scaler.fit_transform(X_clean)
    pca        = PCA(n_components=2)
    pca_result = pca.fit_transform(scaled)
    n_clusters = min(5, len(df))
    kmeans     = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
    clusters   = kmeans.fit_predict(scaled)

    loadings = []
    for i, feat in enumerate(features):
        try:
            # Handle cases where PCA might result in fewer than 2 components
            p1 = float(pca.components_[0, i]) if pca.n_components_ > 0 else 0.0
            p2 = float(pca.components_[1, i]) if pca.n_components_ > 1 else 0.0
        except (IndexError, AttributeError):
            p1, p2 = 0.0, 0.0
        loadings.append({"feature": feat, "pc1": p1, "pc2": p2})

    results = []
    for i, meta in enumerate(metadata):
        # Safer extraction if data only allowed 0 or 1 components
        try:
            px = float(pca_result[i, 0]) if pca.n_components_ > 0 else 0.0
            py = float(pca_result[i, 1]) if pca.n_components_ > 1 else 0.0
        except (IndexError, AttributeError):
            px, py = 0.0, 0.0
            
        meta.update({
            "pca_x":   px,
            "pca_y":   py,
            "cluster": int(clusters[i]),
        })
        results.append(meta)

    result = {
        "activities":     results,
        "loadings":       loadings,
        "variance_ratio": [float(v) for v in pca.explained_variance_ratio_],
    }

    cache.set(cache_key, result)
    logger.info(f"PCA computed and cached for type={activity_type} ({len(df)} activities)")
    return result

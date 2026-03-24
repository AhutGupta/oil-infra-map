"""
ETL script for the global-hydrocarbon-map project.

Loads GeoJSON or CSV source files, standardizes column names, reprojects to
EPSG:4326, merges touching line segments that share the same name/operator,
filters out invalid geometries, and writes separate GeoJSON outputs for
pipelines and facilities.

Usage:
    python scripts/process_data.py \
        --pipelines  data/raw/pipelines.geojson \
        --facilities data/raw/facilities.csv \
        --out-dir    data/processed
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from shapely.validation import make_valid

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column-name aliases that may appear in source data → canonical target name
# ---------------------------------------------------------------------------
COLUMN_ALIASES: dict[str, list[str]] = {
    "name": ["name", "pipeline_name", "facility_name", "title", "label"],
    "type": ["type", "feature_type", "category", "infra_type"],
    "status": ["status", "operational_status", "state", "phase"],
    "operator": ["operator", "operator_name", "company", "owner"],
}

REQUIRED_COLUMNS = list(COLUMN_ALIASES.keys())  # name, type, status, operator

TARGET_CRS = "EPSG:4326"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_column(df_columns: list[str], aliases: list[str]) -> Optional[str]:
    """Return the first column name from *df_columns* that matches an alias."""
    lower_map = {c.lower(): c for c in df_columns}
    for alias in aliases:
        if alias.lower() in lower_map:
            return lower_map[alias.lower()]
    return None


def standardize_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Rename source columns to the canonical set: name, type, status, operator.
    Missing columns are filled with an empty string so downstream code can
    rely on their presence.
    """
    rename_map: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        src = _find_column(list(gdf.columns), aliases)
        if src and src != canonical:
            rename_map[src] = canonical

    gdf = gdf.rename(columns=rename_map)

    for col in REQUIRED_COLUMNS:
        if col not in gdf.columns:
            log.warning("Column '%s' not found in source — filling with ''", col)
            gdf[col] = ""

    # Keep only canonical columns + geometry (drop everything else)
    keep = REQUIRED_COLUMNS + ["geometry"]
    gdf = gdf[[c for c in keep if c in gdf.columns]]

    # Ensure string dtype for categorical columns
    for col in REQUIRED_COLUMNS:
        gdf[col] = gdf[col].fillna("").astype(str)

    return gdf


def reproject(gdf: gpd.GeoDataFrame, target_crs: str = TARGET_CRS) -> gpd.GeoDataFrame:
    """Reproject *gdf* to *target_crs* if it is not already in that CRS."""
    if gdf.crs is None:
        log.warning("GeoDataFrame has no CRS — assuming %s", target_crs)
        gdf = gdf.set_crs(target_crs)
    elif gdf.crs.to_epsg() != int(target_crs.split(":")[1]):
        log.info("Reprojecting from %s to %s", gdf.crs, target_crs)
        gdf = gdf.to_crs(target_crs)
    return gdf


def filter_invalid_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Attempt to repair invalid geometries using shapely's make_valid; drop rows
    where geometry is null or cannot be repaired.
    """
    original_count = len(gdf)

    # Drop null geometries
    gdf = gdf[gdf.geometry.notna()].copy()

    # Attempt repair on invalid geometries
    invalid_mask = ~gdf.geometry.is_valid
    if invalid_mask.any():
        log.info("Attempting to repair %d invalid geometries", invalid_mask.sum())
        gdf.loc[invalid_mask, "geometry"] = gdf.loc[invalid_mask, "geometry"].apply(
            make_valid
        )

    # Drop any still-invalid or empty geometries after repair
    gdf = gdf[gdf.geometry.is_valid & ~gdf.geometry.is_empty].copy()

    dropped = original_count - len(gdf)
    if dropped:
        log.warning("Dropped %d invalid/empty geometries", dropped)

    return gdf


def merge_touching_lines(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Merge line-string segments that share the same *name* and *operator* by
    dissolving on those attributes.  Non-line geometries are returned unchanged.

    Only rows whose geometry type is LineString or MultiLineString participate
    in the dissolve; other geometry types (Point, Polygon, …) are preserved
    separately and re-appended.
    """
    line_types = {"LineString", "MultiLineString"}
    line_mask = gdf.geometry.geom_type.isin(line_types)

    lines = gdf[line_mask].copy()
    others = gdf[~line_mask].copy()

    if lines.empty:
        return gdf

    # dissolve aggregates all same-name/same-operator segments into one
    # MultiLineString; other categorical columns are joined with "|" where
    # values differ within the group.
    agg: dict[str, str] = {}
    for col in REQUIRED_COLUMNS:
        if col not in ("name", "operator"):
            agg[col] = lambda s, c=col: "|".join(sorted(s.dropna().unique()))

    dissolved = lines.dissolve(
        by=["name", "operator"],
        aggfunc=agg,  # type: ignore[arg-type]
        as_index=False,
    )

    result = pd.concat([dissolved, others], ignore_index=True)
    return gpd.GeoDataFrame(result, geometry="geometry", crs=gdf.crs)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_geojson(path: str | Path) -> gpd.GeoDataFrame:
    """Load a GeoJSON file into a GeoDataFrame."""
    log.info("Loading GeoJSON from %s", path)
    return gpd.read_file(str(path))


def load_csv(path: str | Path, lon_col: str = "longitude", lat_col: str = "latitude") -> gpd.GeoDataFrame:
    """
    Load a CSV that contains longitude/latitude columns and return a
    GeoDataFrame with Point geometries.  The caller may override the expected
    column names via *lon_col* / *lat_col*.
    """
    log.info("Loading CSV from %s", path)
    df = pd.read_csv(str(path))

    # Try to auto-detect coordinate columns if the defaults are missing
    lon = _find_column(list(df.columns), [lon_col, "lon", "long", "x"])
    lat = _find_column(list(df.columns), [lat_col, "lat", "y"])

    if lon is None or lat is None:
        raise ValueError(
            f"Cannot find longitude/latitude columns in {path}. "
            f"Columns present: {list(df.columns)}"
        )

    geometry = [Point(xy) for xy in zip(df[lon], df[lat])]
    return gpd.GeoDataFrame(df, geometry=geometry, crs=TARGET_CRS)


def load_source(path: str | Path) -> gpd.GeoDataFrame:
    """Dispatch to the appropriate loader based on file extension."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".geojson", ".json", ".gpkg", ".shp"}:
        return load_geojson(path)
    if suffix == ".csv":
        return load_csv(path)
    raise ValueError(f"Unsupported file format: {suffix}")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def process(path: str | Path, merge_lines: bool = True) -> gpd.GeoDataFrame:
    """
    Full ETL pipeline for a single source file:

    1. Load
    2. Standardize columns
    3. Reproject to EPSG:4326
    4. Filter invalid geometries
    5. (Optional) Merge touching line segments
    """
    gdf = load_source(path)
    gdf = standardize_columns(gdf)
    gdf = reproject(gdf)
    gdf = filter_invalid_geometries(gdf)
    if merge_lines:
        gdf = merge_touching_lines(gdf)
    log.info("Processed %d features from %s", len(gdf), path)
    return gdf


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ETL script: process hydrocarbon infrastructure data."
    )
    parser.add_argument(
        "--pipelines",
        metavar="FILE",
        help="Path to raw pipelines GeoJSON / CSV",
    )
    parser.add_argument(
        "--facilities",
        metavar="FILE",
        help="Path to raw facilities GeoJSON / CSV",
    )
    parser.add_argument(
        "--out-dir",
        metavar="DIR",
        default="data/processed",
        help="Output directory (default: data/processed)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.pipelines and not args.facilities:
        log.error("Provide at least --pipelines or --facilities.")
        sys.exit(1)

    if args.pipelines:
        pipelines = process(args.pipelines, merge_lines=True)
        out_path = out_dir / "pipelines.geojson"
        pipelines.to_file(str(out_path), driver="GeoJSON")
        log.info("Wrote %s", out_path)

    if args.facilities:
        facilities = process(args.facilities, merge_lines=False)
        out_path = out_dir / "facilities.geojson"
        facilities.to_file(str(out_path), driver="GeoJSON")
        log.info("Wrote %s", out_path)


if __name__ == "__main__":
    main()

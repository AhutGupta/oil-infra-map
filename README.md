# global-hydrocarbon-map

An interactive globe map of global oil & gas infrastructure (pipelines, refineries, wells) built with:

| Layer | Technology |
|-------|-----------|
| ETL   | Python · GeoPandas · Fiona · Shapely |
| Tiling | Tippecanoe → PMTiles |
| Frontend | React (Vite) · MapLibre GL JS · PMTiles plugin |
| Hosting | GitHub Pages (via GitHub Actions) |

---

## Project structure

```
.
├── scripts/
│   └── process_data.py   # ETL: load → standardise → reproject → dissolve → write GeoJSON
├── frontend/             # Vite + React app (MapLibre + PMTiles)
├── data/
│   ├── raw/              # Put your source GeoJSON / CSV files here (git-ignored)
│   ├── processed/        # Output of `make clean`  (git-ignored)
│   └── tiles/            # Output of `make tile`   (git-ignored)
├── Makefile
├── requirements.txt
└── .github/workflows/deploy.yml
```

---

## Quick-start

### 1 — Python ETL

```bash
pip install -r requirements.txt

# Drop your source files into data/raw/
# pipelines source must be a GeoJSON/Shapefile/GPKG
# facilities source can be a CSV with longitude/latitude columns

make clean   # → data/processed/pipelines.geojson + facilities.geojson
make tile    # → data/tiles/pipelines.pmtiles + facilities.pmtiles
```

### 2 — Frontend

```bash
# Copy tiles into the public folder so Vite's dev server can serve them
cp data/tiles/*.pmtiles frontend/public/tiles/

cd frontend
npm install
npm run dev   # → http://localhost:5173/
```

### 3 — Production build

```bash
cd frontend && npm run build   # → frontend/dist/
```

---

## ETL details (`scripts/process_data.py`)

| Step | Description |
|------|-------------|
| Load | Accepts GeoJSON, Shapefile, GPKG, or CSV (auto-detects lat/lon columns) |
| Standardise | Renames source columns → `name`, `type`, `status`, `operator` |
| Reproject | Converts any input CRS to EPSG:4326 |
| Filter | Removes null / invalid geometries; attempts `make_valid` repair first |
| Dissolve | Merges touching line-segments that share the same `name` + `operator` |

---

## CI/CD

Push to `main` → GitHub Actions:
1. Installs Python deps + tippecanoe
2. Runs `make clean` + `make tile` (skips if no source data present)
3. Builds the Vite app
4. Deploys `frontend/dist/` to GitHub Pages

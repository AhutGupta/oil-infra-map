# ---------------------------------------------------------------------------
# global-hydrocarbon-map — top-level Makefile
# ---------------------------------------------------------------------------

# Configurable paths
RAW_PIPELINES  ?= data/raw/pipelines.geojson
RAW_FACILITIES ?= data/raw/facilities.csv
PROCESSED_DIR  ?= data/processed
TILES_DIR      ?= data/tiles

PIPELINES_GEOJSON  = $(PROCESSED_DIR)/pipelines.geojson
FACILITIES_GEOJSON = $(PROCESSED_DIR)/facilities.geojson
PIPELINES_PMTILES  = $(TILES_DIR)/pipelines.pmtiles
FACILITIES_PMTILES = $(TILES_DIR)/facilities.pmtiles

PYTHON ?= python
TIPPECANOE ?= tippecanoe

# ---------------------------------------------------------------------------
# Default target
# ---------------------------------------------------------------------------
.PHONY: all
all: tile

# ---------------------------------------------------------------------------
# clean — run the Python ETL and (re)generate processed GeoJSON files
# ---------------------------------------------------------------------------
.PHONY: clean
clean:
	@echo "→ Running ETL (process_data.py)…"
	$(PYTHON) scripts/process_data.py \
		--pipelines  $(RAW_PIPELINES) \
		--facilities $(RAW_FACILITIES) \
		--out-dir    $(PROCESSED_DIR)

# ---------------------------------------------------------------------------
# tile — convert processed GeoJSON → PMTiles with tippecanoe
# ---------------------------------------------------------------------------
.PHONY: tile
tile: $(PIPELINES_PMTILES) $(FACILITIES_PMTILES)

$(TILES_DIR):
	mkdir -p $(TILES_DIR)

$(PIPELINES_PMTILES): $(PIPELINES_GEOJSON) | $(TILES_DIR)
	@echo "→ Tiling pipelines…"
	$(TIPPECANOE) \
		--output=$(PIPELINES_PMTILES) \
		--force \
		--name="Pipelines" \
		--layer="pipelines" \
		--minimum-zoom=0 \
		--maximum-zoom=14 \
		--drop-densest-as-needed \
		$(PIPELINES_GEOJSON)

$(FACILITIES_PMTILES): $(FACILITIES_GEOJSON) | $(TILES_DIR)
	@echo "→ Tiling facilities…"
	$(TIPPECANOE) \
		--output=$(FACILITIES_PMTILES) \
		--force \
		--name="Facilities" \
		--layer="facilities" \
		--minimum-zoom=0 \
		--maximum-zoom=14 \
		--drop-densest-as-needed \
		$(FACILITIES_GEOJSON)

# ---------------------------------------------------------------------------
# frontend build helpers (requires Node / npm)
# ---------------------------------------------------------------------------
.PHONY: frontend-install
frontend-install:
	cd frontend && npm install

.PHONY: frontend-build
frontend-build: frontend-install
	cd frontend && npm run build

# ---------------------------------------------------------------------------
# Full pipeline: ETL → tile → frontend build
# ---------------------------------------------------------------------------
.PHONY: build
build: clean tile frontend-build

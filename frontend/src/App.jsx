import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import 'maplibre-gl/dist/maplibre-gl.css';
import './App.css';

// ---------------------------------------------------------------------------
// PMTiles source URLs (relative so they work from any deploy base-path)
// ---------------------------------------------------------------------------
const PIPELINES_URL  = 'pmtiles:///tiles/pipelines.pmtiles';
const FACILITIES_URL = 'pmtiles:///tiles/facilities.pmtiles';

// Status values available for filtering
const STATUS_OPTIONS = ['Operating', 'Construction', 'Proposed'];

// Layer definitions (id, label, source, source-layer, geometry kind)
const LAYER_DEFS = [
  {
    id:          'pipelines',
    label:       'Pipelines',
    source:      'pipelines-src',
    sourceLayer: 'pipelines',
    kind:        'line',
    paint: {
      'line-color': [
        'match', ['get', 'status'],
        'Operating',    '#22c55e',
        'Construction', '#f59e0b',
        'Proposed',     '#60a5fa',
        /* other */     '#94a3b8',
      ],
      'line-width': 2,
    },
  },
  {
    id:          'refineries',
    label:       'Refineries',
    source:      'facilities-src',
    sourceLayer: 'facilities',
    kind:        'circle',
    filter:      ['==', ['get', 'type'], 'refinery'],
    paint: {
      'circle-radius': 6,
      'circle-color': [
        'match', ['get', 'status'],
        'Operating',    '#22c55e',
        'Construction', '#f59e0b',
        'Proposed',     '#60a5fa',
        /* other */     '#94a3b8',
      ],
      'circle-stroke-width': 1,
      'circle-stroke-color': '#fff',
    },
  },
  {
    id:          'wells',
    label:       'Wells',
    source:      'facilities-src',
    sourceLayer: 'facilities',
    kind:        'circle',
    filter:      ['==', ['get', 'type'], 'well'],
    paint: {
      'circle-radius': 4,
      'circle-color': [
        'match', ['get', 'status'],
        'Operating',    '#22c55e',
        'Construction', '#f59e0b',
        'Proposed',     '#60a5fa',
        /* other */     '#94a3b8',
      ],
      'circle-stroke-width': 1,
      'circle-stroke-color': '#fff',
    },
  },
];

export default function App() {
  const mapContainerRef = useRef(null);
  const mapRef          = useRef(null);

  // Layer visibility: { pipelines: true, refineries: true, wells: true }
  const [layerVisible, setLayerVisible] = useState(
    Object.fromEntries(LAYER_DEFS.map((l) => [l.id, true]))
  );

  // Active status filters (empty set = show all)
  const [activeStatuses, setActiveStatuses] = useState(new Set());

  // ---------------------------------------------------------------------------
  // Initialise map once
  // ---------------------------------------------------------------------------
  useEffect(() => {
    // Register PMTiles protocol
    const protocol = new Protocol();
    maplibregl.addProtocol('pmtiles', protocol.tile.bind(protocol));

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      // Minimal blank style — no external tile server needed
      style: {
        version: 8,
        glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
        sources: {},
        layers: [
          {
            id:   'background',
            type: 'background',
            paint: { 'background-color': '#0f172a' },
          },
        ],
      },
      center:    [0, 20],
      zoom:      2,
      projection: { type: 'globe' },
    });

    map.addControl(new maplibregl.NavigationControl(), 'top-right');

    map.on('load', () => {
      // Add PMTiles sources
      map.addSource('pipelines-src', {
        type: 'vector',
        url:  PIPELINES_URL,
      });
      map.addSource('facilities-src', {
        type: 'vector',
        url:  FACILITIES_URL,
      });

      // Add layers for each definition
      LAYER_DEFS.forEach((def) => {
        const layerSpec = {
          id:           def.id,
          type:         def.kind,
          source:       def.source,
          'source-layer': def.sourceLayer,
          paint:        def.paint,
        };
        if (def.filter) layerSpec.filter = def.filter;
        map.addLayer(layerSpec);
      });

      // Show feature popup on click
      LAYER_DEFS.forEach((def) => {
        map.on('click', def.id, (e) => {
          const props = e.features[0].properties;
          new maplibregl.Popup()
            .setLngLat(e.lngLat)
            .setHTML(
              `<strong>${props.name || '—'}</strong><br/>
               Type: ${props.type || '—'}<br/>
               Status: ${props.status || '—'}<br/>
               Operator: ${props.operator || '—'}`
            )
            .addTo(map);
        });
        map.on('mouseenter', def.id, () => {
          map.getCanvas().style.cursor = 'pointer';
        });
        map.on('mouseleave', def.id, () => {
          map.getCanvas().style.cursor = '';
        });
      });
    });

    mapRef.current = map;

    return () => {
      map.remove();
      maplibregl.removeProtocol('pmtiles');
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Sync layer visibility
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    LAYER_DEFS.forEach((def) => {
      const visible = layerVisible[def.id];
      map.setLayoutProperty(def.id, 'visibility', visible ? 'visible' : 'none');
    });
  }, [layerVisible]);

  // ---------------------------------------------------------------------------
  // Sync status filter
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    LAYER_DEFS.forEach((def) => {
      let filter;

      if (activeStatuses.size === 0) {
        // No status filter — show all (keep type filter if present)
        filter = def.filter ?? null;
      } else {
        const statusFilter = ['in', ['get', 'status'], ['literal', [...activeStatuses]]];
        filter = def.filter
          ? ['all', def.filter, statusFilter]
          : statusFilter;
      }

      if (filter) {
        map.setFilter(def.id, filter);
      } else {
        map.setFilter(def.id, null);
      }
    });
  }, [activeStatuses]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------
  function toggleLayer(id) {
    setLayerVisible((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  function toggleStatus(status) {
    setActiveStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(status)) {
        next.delete(status);
      } else {
        next.add(status);
      }
      return next;
    });
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="app-container">
      <div ref={mapContainerRef} className="map-container" />

      <aside className="overlay-panel">
        <h2 className="panel-title">Global Hydrocarbon Map</h2>

        <section className="panel-section">
          <h3 className="section-heading">Layers</h3>
          {LAYER_DEFS.map((def) => (
            <label key={def.id} className="checkbox-row">
              <input
                type="checkbox"
                checked={layerVisible[def.id]}
                onChange={() => toggleLayer(def.id)}
              />
              <span>{def.label}</span>
            </label>
          ))}
        </section>

        <section className="panel-section">
          <h3 className="section-heading">Status</h3>
          <p className="hint">
            {activeStatuses.size === 0
              ? 'Showing all statuses'
              : `Filtering: ${[...activeStatuses].join(', ')}`}
          </p>
          {STATUS_OPTIONS.map((s) => (
            <label key={s} className="checkbox-row">
              <input
                type="checkbox"
                checked={activeStatuses.has(s)}
                onChange={() => toggleStatus(s)}
              />
              <span>{s}</span>
            </label>
          ))}
        </section>

        <section className="panel-section legend">
          <h3 className="section-heading">Legend</h3>
          {STATUS_OPTIONS.map((s) => (
            <div key={s} className="legend-row">
              <span
                className="legend-swatch"
                style={{
                  background:
                    s === 'Operating'
                      ? '#22c55e'
                      : s === 'Construction'
                      ? '#f59e0b'
                      : '#60a5fa',
                }}
              />
              <span>{s}</span>
            </div>
          ))}
        </section>
      </aside>
    </div>
  );
}

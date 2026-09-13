import L from 'leaflet';

const CITIES: Array<[string, number, number]> = [
  ['Milton', 43.5183, -79.8774],
  ['Cambridge', 43.3616, -80.3144],
  ['Woodstock', 43.1315, -80.7472],
  ['London', 42.9849, -81.2453]
];

/** Draw a self-contained corridor context with no third-party tile requests. */
export function addLocalBasemap(map: L.Map): L.LayerGroup {
  const container = map.getContainer();
  container.style.backgroundColor = '#07111f';
  container.style.backgroundImage = [
    'radial-gradient(circle at 25% 20%, rgba(14,165,233,.11), transparent 30%)',
    'radial-gradient(circle at 75% 75%, rgba(16,185,129,.08), transparent 34%)',
    'linear-gradient(rgba(51,65,85,.16) 1px, transparent 1px)',
    'linear-gradient(90deg, rgba(51,65,85,.16) 1px, transparent 1px)'
  ].join(',');
  container.style.backgroundSize = 'auto, auto, 48px 48px, 48px 48px';

  const layers: L.Layer[] = [];
  for (let lat = 42.8; lat <= 43.8; lat += 0.2) {
    layers.push(L.polyline([[lat, -81.7], [lat, -79.4]], { color: '#334155', weight: 1, opacity: 0.32 }));
  }
  for (let lng = -81.6; lng <= -79.4; lng += 0.2) {
    layers.push(L.polyline([[42.75, lng], [43.85, lng]], { color: '#334155', weight: 1, opacity: 0.32 }));
  }

  CITIES.forEach(([name, lat, lng]) => {
    const icon = L.divIcon({
      className: 'roadstar-local-place-label',
      html: `<span style="color:#94a3b8;font:600 10px ui-monospace,monospace;white-space:nowrap;text-shadow:0 1px 2px #020617">${name}, ON</span>`,
      iconSize: [90, 16],
      iconAnchor: [45, -7]
    });
    layers.push(L.circleMarker([lat, lng], { radius: 3, color: '#64748b', fillColor: '#cbd5e1', fillOpacity: 0.9, weight: 1 }));
    layers.push(L.marker([lat, lng], { icon, interactive: false }));
  });

  const group = L.layerGroup(layers).addTo(map);
  fetch('/data/southern-ontario-basemap.geojson')
    .then(response => {
      if (!response.ok) throw new Error(`local basemap HTTP ${response.status}`);
      return response.json();
    })
    .then(data => {
      L.geoJSON(data, {
        interactive: false,
        style: feature => {
          const properties = feature?.properties ?? {};
          if (properties.kind === 'water') return { color: '#2563eb', weight: 2, opacity: 0.42 };
          if (properties.class === 'motorway') return { color: '#64748b', weight: 3, opacity: 0.72 };
          if (properties.class === 'trunk') return { color: '#64748b', weight: 2, opacity: 0.58 };
          return { color: '#475569', weight: 1.2, opacity: 0.48 };
        }
      }).addTo(group);
      map.attributionControl.addAttribution(
        '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors · ODbL</a>'
      );
    })
    .catch(error => console.warn('Bundled basemap unavailable; using corridor schematic.', error));
  return group;
}

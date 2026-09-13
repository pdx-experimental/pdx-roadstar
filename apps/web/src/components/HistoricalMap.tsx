import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import { addLocalBasemap } from './LocalBasemap';

export interface TruckItem {
  id: string;
  driver: string;
  orig: string;
  dest: string;
  lat: number;
  lng: number;
  status: string;
  leg_type: string;
  dist: number;
  is_empty: boolean;
  dwell: number;
  speed: number;
}

interface HistoricalMapProps {
  trucks: TruckItem[];
  geofences: any[];
}

export const HistoricalMap: React.FC<HistoricalMapProps> = ({ trucks, geofences }) => {
  const mapRef = useRef<HTMLDivElement>(null);
  const leafletMap = useRef<L.Map | null>(null);
  const markersRef = useRef<{ [id: string]: L.Marker }>({});

  useEffect(() => {
    if (!mapRef.current || leafletMap.current) return;

    const map = L.map(mapRef.current, {
      center: [43.25, -80.55],
      zoom: 9,
      zoomControl: false,
      preferCanvas: true
    });
    L.control.zoom({ position: 'bottomright' }).addTo(map);

    addLocalBasemap(map);

    leafletMap.current = map;

    // Highway 401 Backbone (Historical corridor)
    const hwy401: [number, number][] = [
      [43.5183, -79.8774], // Milton
      [43.4150, -80.3200], // Cambridge
      [43.1315, -80.7472], // Woodstock
      [42.9849, -81.2453]  // London
    ];
    L.polyline(hwy401, { color: '#f43f5e', weight: 4, opacity: 0.5, dashArray: '6, 6' }).addTo(map);

    // Geofences
    geofences.forEach(gf => {
      L.circle([gf.lat, gf.lng], {
        radius: gf.radius_meters || 2000,
        color: '#f43f5e',
        fillColor: '#f43f5e',
        fillOpacity: 0.1,
        weight: 1.5,
        dashArray: '4, 4'
      }).addTo(map).bindTooltip(`<b>${gf.name}</b><br/>${gf.city}`, {
        direction: 'top',
        className: 'bg-slate-900 text-slate-100 border border-slate-700 text-xs rounded p-1'
      });
    });

    return () => {
      map.remove();
      leafletMap.current = null;
    };
  }, [geofences]);

  // Update Markers
  useEffect(() => {
    if (!leafletMap.current) return;

    const visibleIds = new Set(trucks.map(t => t.id));
    Object.entries(markersRef.current).forEach(([id, marker]) => {
      if (!visibleIds.has(id)) {
        marker.remove();
        delete markersRef.current[id];
      }
    });

    trucks.filter(t => Number.isFinite(t.lat) && Number.isFinite(t.lng)).forEach(t => {
      let iconColor = 'bg-slate-700 border-slate-300';
      let badgeColor = 'bg-slate-950 text-slate-300 border-slate-800';
      let symbol = '🚛';
      let label = t.id;

      if (t.is_empty) {
        iconColor = 'bg-rose-700 border-rose-300 animate-pulse';
        badgeColor = 'bg-rose-950 text-rose-300 border-rose-700';
        symbol = '⚠️';
        label = `${t.id} [EMPTY]`;
      } else if (t.dwell > 2.0 && t.speed === 0) {
        iconColor = 'bg-amber-600 border-amber-300';
        badgeColor = 'bg-amber-950 text-amber-300 border-amber-700';
        symbol = '⏳';
        label = `${t.id} [DWELL]`;
      }

      const iconHtml = `
        <div class="relative flex items-center justify-center">
          <div class="w-6 h-6 rounded-full flex items-center justify-center shadow-lg border-2 ${iconColor}">
            <span class="text-white text-[10px] font-black">${symbol}</span>
          </div>
          <div class="absolute -bottom-4 whitespace-nowrap ${badgeColor} text-[8px] font-mono font-bold px-1 rounded border shadow pointer-events-none">
            ${label}
          </div>
        </div>
      `;

      const icon = L.divIcon({ className: 'custom-hist-icon', html: iconHtml, iconSize: [24, 24], iconAnchor: [12, 12] });

      const popupHtml = `
        <div class="p-2 text-slate-100 text-xs space-y-1">
          <div class="font-bold text-rose-400 border-b border-slate-700 pb-1">${t.id} · ${t.driver}</div>
          <div><b>Route:</b> ${t.orig} ➔ ${t.dest} (${t.dist.toFixed(0)} mi)</div>
          <div><b>Status:</b> <span class="${t.is_empty ? 'text-rose-400 font-bold' : 'text-slate-300'}">${t.status}</span></div>
          <div><b>Speed:</b> ${t.speed.toFixed(0)} km/h</div>
          ${t.dwell > 2.0 ? `<div class="text-amber-400"><b>Dock Dwell:</b> ${t.dwell.toFixed(1)}h (Unbilled Loss)</div>` : ''}
          ${t.is_empty ? `<div class="text-rose-400 font-bold">⚠️ Deadhead Return (38% Baseline Waste)</div>` : ''}
        </div>
      `;

      if (!markersRef.current[t.id]) {
        const m = L.marker([t.lat, t.lng], { icon }).addTo(leafletMap.current!).bindPopup(popupHtml, {
          className: 'custom-leaflet-popup'
        });
        markersRef.current[t.id] = m;
      } else {
        markersRef.current[t.id].setLatLng([t.lat, t.lng]);
        markersRef.current[t.id].setIcon(icon);
        markersRef.current[t.id].setPopupContent(popupHtml);
      }
    });
  }, [trucks]);

  return (
    <div className="relative w-full h-full bg-slate-900 overflow-hidden border-b border-slate-800">
      <div ref={mapRef} className="w-full h-full" />

      {/* Control Overlay */}
      <div className="absolute top-2 left-2 z-[500] flex items-center space-x-2 bg-slate-950/90 backdrop-blur-md px-2.5 py-1 rounded-lg border border-slate-800 shadow">
        <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-slate-800 text-slate-300">
          🗺️ Bundled OSM Map
        </span>
        <span className="text-[10px] text-rose-400 font-bold border-l border-slate-700 pl-2">
          🔴 Historical Baseline View
        </span>
      </div>

      {/* Legend */}
      <div className="absolute bottom-2 left-2 z-[500] bg-slate-950/90 backdrop-blur-md px-2.5 py-1.5 rounded-lg border border-slate-800 text-[9px] text-slate-300 space-y-0.5 pointer-events-none shadow">
        <div className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-rose-600"></span>
          <span>⚠️ Empty Deadhead Return</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-amber-500"></span>
          <span>⏳ Dock Dwell &gt; 2h (Unbilled Loss)</span>
        </div>
      </div>
    </div>
  );
};

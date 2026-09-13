import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import { addLocalBasemap } from './LocalBasemap';

interface TruckInfo {
  id: string;
  driver: string;
  lat: number;
  lng: number;
  status: string;
  leg: string;
  speed: number;
  is_empty: boolean;
}

interface DualTrackMapProps {
  baselineTrucks: TruckInfo[];
  pdxTrucks: TruckInfo[];
  geofences: any[];
}

export const DualTrackMap: React.FC<DualTrackMapProps> = ({
  baselineTrucks,
  pdxTrucks,
  geofences
}) => {
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

    // Draw Highway 401 Corridor backbone
    const hwy401Coords: [number, number][] = [
      [43.5183, -79.8774], // Milton
      [43.4150, -80.3200], // Cambridge
      [43.1315, -80.7472], // Woodstock
      [42.9849, -81.2453]  // London
    ];
    L.polyline(hwy401Coords, { color: '#38bdf8', weight: 4, opacity: 0.6 }).addTo(map);

    // Render Geofences
    geofences.forEach(gf => {
      L.circle([gf.lat, gf.lng], {
        radius: gf.radius_meters || 2000,
        color: '#6366f1',
        fillColor: '#6366f1',
        fillOpacity: 0.15,
        weight: 1.5,
        dashArray: '3, 5'
      }).addTo(map).bindTooltip(`<b>${gf.name}</b><br/>${gf.city}, ON`, {
        direction: 'top',
        className: 'bg-slate-900 text-slate-100 border border-slate-700 text-xs rounded p-1'
      });
    });

    return () => {
      map.remove();
      leafletMap.current = null;
    };
  }, [geofences]);

  // Update Truck Markers for Both Tracks
  useEffect(() => {
    if (!leafletMap.current) return;

    // 1. Baseline Trucks (Amber/Red icon)
    baselineTrucks.forEach(t => {
      const key = `base_${t.id}`;
      const iconHtml = `
        <div class="relative flex items-center justify-center">
          <div class="w-7 h-7 rounded-full flex items-center justify-center shadow-lg border-2 ${
            t.is_empty ? 'bg-rose-700 border-rose-300' : 'bg-slate-700 border-slate-300'
          }">
            <span class="text-white text-[11px] font-black">${t.is_empty ? '⚠️' : '🚛'}</span>
          </div>
          <div class="absolute -bottom-4 whitespace-nowrap bg-rose-950/90 text-rose-200 text-[9px] font-bold px-1 rounded border border-rose-800 shadow">
            [HIST] ${t.id}
          </div>
        </div>
      `;
      const icon = L.divIcon({ className: 'custom-truck-icon', html: iconHtml, iconSize: [28, 28], iconAnchor: [14, 14] });
      if (!markersRef.current[key]) {
        markersRef.current[key] = L.marker([t.lat, t.lng - 0.015], { icon }).addTo(leafletMap.current!); // offset slightly for visual side-by-side
      } else {
        markersRef.current[key].setLatLng([t.lat, t.lng - 0.015]);
        markersRef.current[key].setIcon(icon);
      }
    });

    // 2. PDX Trucks (Cyan/Green icon)
    pdxTrucks.forEach(t => {
      const key = `pdx_${t.id}`;
      const iconHtml = `
        <div class="relative flex items-center justify-center">
          <div class="w-7 h-7 rounded-full flex items-center justify-center shadow-lg border-2 bg-cyan-600 border-cyan-300">
            <span class="text-white text-[11px] font-black">⚡</span>
          </div>
          <div class="absolute -bottom-4 whitespace-nowrap bg-cyan-950/90 text-cyan-200 text-[9px] font-bold px-1 rounded border border-cyan-800 shadow">
            [PDX] ${t.id}
          </div>
        </div>
      `;
      const icon = L.divIcon({ className: 'custom-truck-icon', html: iconHtml, iconSize: [28, 28], iconAnchor: [14, 14] });
      if (!markersRef.current[key]) {
        markersRef.current[key] = L.marker([t.lat, t.lng + 0.015], { icon }).addTo(leafletMap.current!);
      } else {
        markersRef.current[key].setLatLng([t.lat, t.lng + 0.015]);
        markersRef.current[key].setIcon(icon);
      }
    });
  }, [baselineTrucks, pdxTrucks]);

  return (
    <div className="relative w-full h-full bg-slate-900 rounded-xl overflow-hidden border border-slate-800 shadow-2xl">
      <div ref={mapRef} className="w-full h-full" />

      {/* Map Control Overlay */}
      <div className="absolute top-3 left-3 z-[500] flex items-center space-x-2 bg-slate-900/90 backdrop-blur-md p-1.5 rounded-lg border border-slate-700 shadow-lg">
        <span className="px-3 py-1 text-xs font-bold rounded bg-slate-800 text-slate-300">
          🗺️ Bundled OSM Map
        </span>
        <span className="text-[11px] text-slate-400 px-2 border-l border-slate-700">
          Hwy 401 Corridor: Milton ⇄ London
        </span>
      </div>

      {/* Dual Legend */}
      <div className="absolute bottom-3 left-3 z-[500] bg-slate-900/90 backdrop-blur-md p-2.5 rounded-lg border border-slate-700 text-[10px] text-slate-300 space-y-1 shadow-lg pointer-events-none">
        <div className="font-bold text-slate-200 mb-1">Dual-Track Highway 401 Fleet:</div>
        <div className="flex items-center space-x-2">
          <span className="w-2.5 h-2.5 rounded-full bg-rose-600"></span>
          <span>[HIST] Baseline: 38% Deadhead Empty Return</span>
        </div>
        <div className="flex items-center space-x-2">
          <span className="w-2.5 h-2.5 rounded-full bg-cyan-500"></span>
          <span>[PDX] Autonomous: Backhaul Loaded &amp; Dossiers</span>
        </div>
      </div>
    </div>
  );
};

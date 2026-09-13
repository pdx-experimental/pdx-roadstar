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

export interface InterventionItem {
  time: string;
  sim_minute: number;
  type: string;
  truck: string;
  driver: string;
  lat: number;
  lng: number;
  location_name: string;
  desc: string;
  financial_delta: string;
  receipt_id?: string;
  sha256?: string;
}

interface PdxMapProps {
  trucks: TruckItem[];
  geofences: any[];
  interventions: InterventionItem[];
  simMinute: number;
  onSelectIntervention: (inv: InterventionItem) => void;
}

export const PdxMap: React.FC<PdxMapProps> = ({
  trucks,
  geofences,
  interventions,
  simMinute,
  onSelectIntervention
}) => {
  const mapRef = useRef<HTMLDivElement>(null);
  const leafletMap = useRef<L.Map | null>(null);
  const markersRef = useRef<{ [id: string]: L.Marker }>({});
  const calloutMarkersRef = useRef<{ [key: string]: L.Marker }>({});

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

    // Highway 401 Backbone (PDX AI Optimized Corridor)
    const hwy401: [number, number][] = [
      [43.5183, -79.8774], // Milton
      [43.4150, -80.3200], // Cambridge
      [43.1315, -80.7472], // Woodstock
      [42.9849, -81.2453]  // London
    ];
    L.polyline(hwy401, { color: '#10b981', weight: 4, opacity: 0.8 }).addTo(map);

    // Geofences
    geofences.forEach(gf => {
      L.circle([gf.lat, gf.lng], {
        radius: gf.radius_meters || 2000,
        color: '#10b981',
        fillColor: '#10b981',
        fillOpacity: 0.12,
        weight: 1.5,
        dashArray: '3, 4'
      }).addTo(map).bindTooltip(`<b>${gf.name}</b><br/>${gf.city} (ProDocuX Audited)`, {
        direction: 'top',
        className: 'bg-slate-900 text-slate-100 border border-slate-700 text-xs rounded p-1'
      });
    });

    return () => {
      map.remove();
      leafletMap.current = null;
    };
  }, [geofences]);

  // Update Truck Markers
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
      const hasBackhaul = interventions.some(inv => inv.truck === t.id && inv.type === 'PDX_BACKHAUL_MATCH');
      const hasDossier = interventions.some(inv => inv.truck === t.id && inv.type === 'PRODOCUX_DETENTION_DOSSIER');
      let iconColor = 'bg-cyan-700 border-cyan-300';
      let badgeColor = 'bg-cyan-950 text-cyan-300 border-cyan-700';
      let symbol = '⚡';
      let label = t.id;

      if (hasBackhaul) {
        iconColor = 'bg-emerald-600 border-emerald-300 animate-pulse';
        badgeColor = 'bg-emerald-950 text-emerald-300 border-emerald-600';
        symbol = '🤖';
        label = `${t.id} [BACKHAUL]`;
      } else if (hasDossier) {
        iconColor = 'bg-blue-600 border-blue-300';
        badgeColor = 'bg-blue-950 text-blue-300 border-blue-600';
        symbol = '📜';
        label = `${t.id} [SEALED]`;
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

      const icon = L.divIcon({ className: 'custom-pdx-icon', html: iconHtml, iconSize: [24, 24], iconAnchor: [12, 12] });

      const popupHtml = `
        <div class="p-2 text-slate-100 text-xs space-y-1">
          <div class="font-bold text-emerald-400 border-b border-slate-700 pb-1">${t.id} · ${t.driver}</div>
          <div><b>Route:</b> ${t.orig} ➔ ${t.dest} (${t.dist.toFixed(0)} mi)</div>
          <div><b>Status:</b> <span class="text-emerald-400 font-bold">${t.status}</span></div>
          <div><b>Optimization:</b> <span class="text-cyan-300">${t.leg_type}</span></div>
          <div><b>Speed:</b> ${t.speed.toFixed(0)} km/h</div>
          ${hasDossier ? `<div class="text-blue-300"><b>ProDocuX Sealed Dossier:</b> ${t.dwell.toFixed(1)}h ($95/h billed)</div>` : ''}
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
  }, [trucks, interventions]);

  // Render Floating On-Map Intervention Callouts (Active for 45 sim minutes after trigger)
  useEffect(() => {
    if (!leafletMap.current) return;

    const recentInterventions = interventions.filter(
      inv => simMinute >= inv.sim_minute && simMinute <= inv.sim_minute + 60
    );

    const activeKeys = new Set<string>();

    recentInterventions.forEach(inv => {
      const key = `${inv.truck}_${inv.sim_minute}`;
      activeKeys.add(key);

      const isBackhaul = inv.type === 'PDX_BACKHAUL_MATCH';
      const isDossier = inv.type === 'PRODOCUX_DETENTION_DOSSIER';

      const bgGlow = isBackhaul
        ? 'bg-emerald-950/95 border-emerald-400 text-emerald-100 ring-4 ring-emerald-500/20'
        : 'bg-blue-950/95 border-cyan-400 text-cyan-100 ring-4 ring-cyan-500/20';

      const icon = isBackhaul ? '🤖' : (isDossier ? '📜' : '🛡️');
      const title = isBackhaul ? 'AI Backhaul Paired' : (isDossier ? 'ProDocuX Dossier' : 'HOS Compliant');

      const calloutHtml = `
        <div class="relative cursor-pointer group animate-bounce" style="animation-duration: 2.5s;">
          <div class="flex items-center space-x-1.5 px-2.5 py-1.5 rounded-lg border-2 shadow-2xl backdrop-blur-md ${bgGlow} transition hover:scale-105">
            <span class="text-sm">${icon}</span>
            <div class="leading-tight">
              <div class="flex items-center space-x-1">
                <span class="text-[9px] font-black uppercase tracking-wider text-white">${title}</span>
                <span class="text-[9px] font-mono font-bold text-amber-300">${inv.financial_delta}</span>
              </div>
              <div class="text-[8px] font-mono text-slate-300 truncate max-w-[150px]">
                ${inv.truck} · ${inv.location_name}
              </div>
            </div>
          </div>
          <div class="w-2 h-2 bg-emerald-500 rotate-45 mx-auto -mt-1 shadow"></div>
        </div>
      `;

      const divIcon = L.divIcon({
        className: 'floating-intervention-callout',
        html: calloutHtml,
        iconSize: [200, 42],
        iconAnchor: [100, 48]
      });

      if (!calloutMarkersRef.current[key]) {
        const marker = L.marker([inv.lat, inv.lng], { icon: divIcon, zIndexOffset: 1000 })
          .addTo(leafletMap.current!)
          .on('click', () => onSelectIntervention(inv));
        calloutMarkersRef.current[key] = marker;
      } else {
        calloutMarkersRef.current[key].setLatLng([inv.lat, inv.lng]);
      }
    });

    // Clean up expired callout markers
    Object.keys(calloutMarkersRef.current).forEach(k => {
      if (!activeKeys.has(k)) {
        leafletMap.current?.removeLayer(calloutMarkersRef.current[k]);
        delete calloutMarkersRef.current[k];
      }
    });
  }, [interventions, simMinute, onSelectIntervention]);

  return (
    <div className="relative w-full h-full bg-slate-900 overflow-hidden border-b border-slate-800">
      <div ref={mapRef} className="w-full h-full" />

      {/* Control Overlay */}
      <div className="absolute top-2 left-2 z-[500] flex items-center space-x-2 bg-slate-950/90 backdrop-blur-md px-2.5 py-1 rounded-lg border border-slate-800 shadow">
        <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-slate-800 text-slate-300">
          🗺️ Bundled OSM Map
        </span>
        <span className="text-[10px] text-emerald-400 font-bold border-l border-slate-700 pl-2">
          🟢 PDX Autonomous Intervention Track
        </span>
      </div>

      {/* Legend & Callout Hint */}
      <div className="absolute bottom-2 left-2 z-[500] bg-slate-950/90 backdrop-blur-md px-2.5 py-1.5 rounded-lg border border-slate-800 text-[9px] text-slate-300 space-y-0.5 pointer-events-none shadow">
        <div className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping"></span>
          <span className="text-emerald-300 font-bold">Floating On-Map Callouts Active (Click to verify)</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
          <span>🤖 Backhaul Paired · 📜 ProDocuX Dossier</span>
        </div>
      </div>
    </div>
  );
};

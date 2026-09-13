import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import { addLocalBasemap } from './LocalBasemap';

interface Truck {
  truck_id: string;
  driver_id: number;
  driver_name: string;
  lat: number;
  lng: number;
  speed_kmh: number;
  odometer_km: number;
  is_delayed_hwy401: boolean;
  at_dock: boolean;
  geofence: string | null;
  breadcrumbs: { lat: number; lng: number }[];
  hos: any;
  detention: any;
}

interface Geofence {
  id: string;
  name: string;
  city: string;
  lat: number;
  lng: number;
  radius_meters: number;
  facility_type: string;
}

interface DispatchMapProps {
  trucks: Truck[];
  geofences: Geofence[];
  selectedTruckId: string | null;
  onSelectTruck: (truckId: string) => void;
}

export const DispatchMap: React.FC<DispatchMapProps> = ({
  trucks,
  geofences,
  selectedTruckId,
  onSelectTruck
}) => {
  const mapRef = useRef<HTMLDivElement>(null);
  const leafletMap = useRef<L.Map | null>(null);
  const markersRef = useRef<{ [id: string]: L.Marker }>({});
  const circlesRef = useRef<{ [id: string]: L.Circle }>({});
  const polyRef = useRef<{ [id: string]: L.Polyline }>({});

  useEffect(() => {
    if (!mapRef.current || leafletMap.current) return;

    // Centered along Southern Ontario 401 Corridor (between Milton & London)
    const map = L.map(mapRef.current, {
      center: [43.25, -80.55],
      zoom: 9,
      zoomControl: false,
      preferCanvas: true
    });
    L.control.zoom({ position: 'bottomright' }).addTo(map);

    addLocalBasemap(map);

    leafletMap.current = map;

    return () => {
      map.remove();
      leafletMap.current = null;
    };
  }, []);

  // Render Geofences
  useEffect(() => {
    if (!leafletMap.current) return;
    geofences.forEach(gf => {
      if (!circlesRef.current[gf.id]) {
        const isHub = gf.facility_type === 'TERMINAL_HUB';
        const circle = L.circle([gf.lat, gf.lng], {
          radius: gf.radius_meters,
          color: isHub ? '#3b82f6' : '#8b5cf6',
          fillColor: isHub ? '#3b82f6' : '#8b5cf6',
          fillOpacity: 0.18,
          weight: 2,
          dashArray: isHub ? undefined : '4, 6'
        }).addTo(leafletMap.current!);

        circle.bindTooltip(`<b>${gf.name}</b><br/>${gf.city}, ON [Geofence: ${gf.radius_meters}m]`, {
          direction: 'top',
          className: 'bg-slate-900 text-slate-100 border border-slate-700 text-xs rounded p-1.5'
        });
        circlesRef.current[gf.id] = circle;
      }
    });
  }, [geofences]);

  // Render & Update Trucks and Breadcrumbs
  useEffect(() => {
    if (!leafletMap.current) return;

    trucks.forEach(t => {
      const isDetention = t.detention && t.detention.total_wait_hours > 2.0;
      const isSelected = selectedTruckId === t.truck_id;

      const iconHtml = `
        <div class="relative flex items-center justify-center">
          <div class="w-8 h-8 rounded-full flex items-center justify-center shadow-lg border-2 ${
            isDetention ? 'bg-rose-600 border-rose-300 animate-pulse' :
            t.at_dock ? 'bg-amber-600 border-amber-300' :
            t.is_delayed_hwy401 ? 'bg-orange-600 border-orange-300' :
            'bg-emerald-600 border-emerald-300'
          } ${isSelected ? 'ring-4 ring-cyan-400' : ''}">
            <span class="text-white text-xs font-black">🚛</span>
          </div>
          <div class="absolute -bottom-5 whitespace-nowrap bg-slate-900/90 text-slate-200 text-[10px] font-semibold px-1.5 py-0.5 rounded border border-slate-700 shadow">
            ${t.truck_id}
          </div>
        </div>
      `;

      const customIcon = L.divIcon({
        className: 'custom-truck-icon',
        html: iconHtml,
        iconSize: [32, 32],
        iconAnchor: [16, 16]
      });

      if (!markersRef.current[t.truck_id]) {
        const marker = L.marker([t.lat, t.lng], { icon: customIcon }).addTo(leafletMap.current!);
        marker.on('click', () => onSelectTruck(t.truck_id));
        markersRef.current[t.truck_id] = marker;
      } else {
        markersRef.current[t.truck_id].setLatLng([t.lat, t.lng]);
        markersRef.current[t.truck_id].setIcon(customIcon);
      }

      // Breadcrumbs Polyline
      const latlngs = t.breadcrumbs.map(b => [b.lat, b.lng] as [number, number]);
      if (!polyRef.current[t.truck_id]) {
        const poly = L.polyline(latlngs, {
          color: t.truck_id === 'TRK-B3339' ? '#38bdf8' : '#a855f7',
          weight: 3,
          opacity: 0.75,
          dashArray: '2, 4'
        }).addTo(leafletMap.current!);
        polyRef.current[t.truck_id] = poly;
      } else {
        polyRef.current[t.truck_id].setLatLngs(latlngs);
      }
    });
  }, [trucks, selectedTruckId, onSelectTruck]);

  return (
    <div className="relative w-full h-full bg-slate-900 rounded-xl overflow-hidden border border-slate-800 shadow-2xl">
      <div ref={mapRef} className="w-full h-full" />

      {/* Map Control Overlay */}
      <div className="absolute top-4 left-4 z-[500] flex items-center space-x-2 bg-slate-900/90 backdrop-blur-md p-1.5 rounded-lg border border-slate-700 shadow-lg">
        <span className="px-3 py-1.5 text-xs font-bold rounded bg-slate-800 text-slate-300">
          🗺️ Bundled OSM Map
        </span>
        <span className="text-[11px] text-slate-400 px-2 border-l border-slate-700">
          Corridor: Hwy 401 (Milton ⇄ London)
        </span>
      </div>

      {/* Legend Overlay */}
      <div className="absolute bottom-4 left-4 z-[500] bg-slate-900/90 backdrop-blur-md p-2.5 rounded-lg border border-slate-700 text-[11px] text-slate-300 space-y-1 shadow-lg pointer-events-none">
        <div className="font-semibold text-slate-200 mb-1 flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
          <span>Southern Ontario Live Telematics</span>
        </div>
        <div className="flex items-center space-x-2">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
          <span>Cruising (Hwy 401 Normal)</span>
        </div>
        <div className="flex items-center space-x-2">
          <span className="w-2.5 h-2.5 rounded-full bg-orange-500"></span>
          <span>401 Slowdown / Incident</span>
        </div>
        <div className="flex items-center space-x-2">
          <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse"></span>
          <span>Dock Detention Alert (&gt;2h)</span>
        </div>
        <div className="flex items-center space-x-2">
          <span className="w-2.5 h-2.5 border border-blue-500 bg-blue-500/20 rounded-sm"></span>
          <span>Milton &amp; London Hubs</span>
        </div>
      </div>
    </div>
  );
};

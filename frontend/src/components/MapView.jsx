import React, { useEffect, useRef } from 'react'
import { MapContainer, TileLayer, useMapEvents, useMap } from 'react-leaflet'
import L from 'leaflet'
import RouteLayer from './RouteLayer'

// leaflet.heat is a legacy UMD plugin that patches a global L.
// We must expose our L as window.L BEFORE the static import below runs its factory.
window.L = L
import 'leaflet.heat'

const RISK_COLORS = {
  Low: '#10b981',
  Medium: '#f59e0b',
  High: '#f97316',
  Critical: '#ef4444',
}

function createPinIcon(color) {
  return L.divIcon({
    className: '',
    iconAnchor: [16, 40],
    html: `
      <div style="position:relative;width:32px;height:40px">
        <svg viewBox="0 0 32 40" fill="none" xmlns="http://www.w3.org/2000/svg" width="32" height="40">
          <path d="M16 0C7.163 0 0 7.163 0 16c0 10 16 24 16 24S32 26 32 16C32 7.163 24.837 0 16 0z" fill="${color}"/>
          <circle cx="16" cy="16" r="7" fill="white" opacity="0.9"/>
        </svg>
      </div>`,
  })
}

function HeatmapLayer({ points }) {
  const map = useMap()
  const layerRef = useRef(null)

  useEffect(() => {
    // Clean up old layer whenever points change
    if (layerRef.current) {
      map.removeLayer(layerRef.current)
      layerRef.current = null
    }
    if (!points || points.length === 0) return
    if (!L.heatLayer) {
      console.warn('leaflet.heat not loaded yet')
      return
    }
    layerRef.current = L.heatLayer(points, {
      radius: 28,
      blur: 18,
      maxZoom: 18,
      // max > 1 so background grid-point accumulation never saturates —
      // only true hotspot clusters (many high-weight points overlapping) hit peak colour
      max: 3.0,
      minOpacity: 0.0,
      gradient: {
        0.00: 'rgba(0,0,0,0)',            // transparent — safe zones invisible
        0.25: 'rgba(0,0,0,0)',            // extended transparent tail
        0.35: 'rgba(37,99,235,0.55)',     // blue edge of risk
        0.52: 'rgba(124,58,237,0.82)',    // purple — moderate risk
        0.68: 'rgba(220,38,38,0.92)',     // red — high risk
        0.84: 'rgba(249,115,22,1.0)',     // orange
        1.00: 'rgba(251,191,36,1.0)',     // amber peak — hotspot centre
      },
    }).addTo(map)

    return () => {
      if (layerRef.current) {
        map.removeLayer(layerRef.current)
        layerRef.current = null
      }
    }
  }, [points, map])

  return null
}

function MarkerLayer({ position, riskLevel }) {
  const map = useMap()
  const markerRef = useRef(null)

  useEffect(() => {
    if (markerRef.current) {
      markerRef.current.remove()
      markerRef.current = null
    }
    if (!position) return
    const color = RISK_COLORS[riskLevel] || '#60a5fa'
    markerRef.current = L.marker(position, { icon: createPinIcon(color) }).addTo(map)

    return () => {
      if (markerRef.current) {
        markerRef.current.remove()
        markerRef.current = null
      }
    }
  }, [position, riskLevel, map])

  return null
}

function ClickHandler({ onMapClick }) {
  useMapEvents({
    click(e) {
      onMapClick({ lat: e.latlng.lat, lng: e.latlng.lng })
    },
  })
  return null
}

function FlyTo({ target }) {
  const map = useMap()
  useEffect(() => {
    if (target) map.flyTo([target.lat, target.lng], 15, { duration: 1.2 })
  }, [target, map])
  return null
}

export default function MapView({ heatmapPoints, markerPos, riskLevel, onMapClick, flyTarget, routeData }) {
  return (
    <MapContainer
      center={[51.505, -0.09]}
      zoom={13}
      zoomControl={false}
      style={{ width: '100%', height: '100%' }}
      attributionControl={false}
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        maxZoom={19}
      />
      <HeatmapLayer points={heatmapPoints} />
      {!routeData && <MarkerLayer position={markerPos} riskLevel={riskLevel} />}
      <RouteLayer routeData={routeData} />
      <ClickHandler onMapClick={onMapClick} />
      <FlyTo target={flyTarget} />
    </MapContainer>
  )
}

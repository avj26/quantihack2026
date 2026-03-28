import React, { useEffect, useRef } from 'react'
import { MapContainer, TileLayer, useMapEvents, useMap } from 'react-leaflet'
import L from 'leaflet'

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
      blur: 20,
      maxZoom: 17,
      max: 1.0,
      gradient: {
        0.0: '#1e3a5f',
        0.2: '#1d4ed8',
        0.4: '#7c3aed',
        0.6: '#dc2626',
        0.8: '#ea580c',
        1.0: '#fbbf24',
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

export default function MapView({ heatmapPoints, markerPos, riskLevel, onMapClick, flyTarget }) {
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
      <MarkerLayer position={markerPos} riskLevel={riskLevel} />
      <ClickHandler onMapClick={onMapClick} />
      <FlyTo target={flyTarget} />
    </MapContainer>
  )
}

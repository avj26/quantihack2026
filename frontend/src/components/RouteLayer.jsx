import React from 'react'
import { Polyline, CircleMarker } from 'react-leaflet'

function scoreToColor(score) {
  if (score >= 75) return '#10b981'
  if (score >= 50) return '#f59e0b'
  if (score >= 30) return '#f97316'
  return '#ef4444'
}

// Build colored segments by mapping each coordinate to its nearest safety sample
function buildSegments(coords, samples) {
  if (!coords || coords.length < 2 || !samples || samples.length === 0) return []

  const segments = []
  let segPositions = [[coords[0][1], coords[0][0]]]
  let segColor = scoreToColor(samples[0].score)

  for (let i = 1; i < coords.length; i++) {
    const t = i / (coords.length - 1)
    const sIdx = Math.min(samples.length - 1, Math.round(t * (samples.length - 1)))
    const color = scoreToColor(samples[sIdx].score)
    const pos = [coords[i][1], coords[i][0]]

    if (color !== segColor) {
      segPositions.push(pos) // overlap by one point for continuity
      segments.push({ color: segColor, positions: segPositions })
      segPositions = [pos]
      segColor = color
    } else {
      segPositions.push(pos)
    }
  }
  if (segPositions.length >= 2) segments.push({ color: segColor, positions: segPositions })
  return segments
}

function ColoredRoute({ route }) {
  const segments = buildSegments(route.geometry, route.safety_samples)
  const allPositions = route.geometry?.map(c => [c[1], c[0]]) ?? []

  return (
    <>
      {/* Shadow / outline under the route */}
      {allPositions.length >= 2 && (
        <Polyline positions={allPositions} pathOptions={{ color: '#000', weight: 9, opacity: 0.35 }} />
      )}
      {/* Colored safety segments */}
      {segments.map((seg, i) => (
        <Polyline
          key={i}
          positions={seg.positions}
          pathOptions={{ color: seg.color, weight: 5, opacity: 0.92 }}
        />
      ))}
    </>
  )
}

export default function RouteLayer({ routeData }) {
  if (!routeData) return null
  const { routes, fromPos, toPos } = routeData
  const recommended = routes?.find(r => r.is_recommended) || routes?.[0]
  if (!recommended) return null

  return (
    <>
      <ColoredRoute route={recommended} />

      {/* From marker — green */}
      {fromPos && (
        <CircleMarker
          center={fromPos}
          radius={9}
          pathOptions={{ color: '#fff', weight: 2.5, fillColor: '#10b981', fillOpacity: 1 }}
        />
      )}

      {/* To marker — indigo */}
      {toPos && (
        <CircleMarker
          center={toPos}
          radius={9}
          pathOptions={{ color: '#fff', weight: 2.5, fillColor: '#6366f1', fillOpacity: 1 }}
        />
      )}
    </>
  )
}

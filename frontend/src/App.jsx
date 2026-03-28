import React, { useState, useEffect, useCallback } from 'react'
import { Navigation2, Info } from 'lucide-react'
import MapView from './components/MapView'
import MetricsPanel from './components/MetricsPanel'
import SearchBar from './components/SearchBar'
import TimeSlider from './components/TimeSlider'
import axios from 'axios'

export default function App() {
  const [heatmapPoints, setHeatmapPoints] = useState([])
  const [selectedPos, setSelectedPos] = useState(null)
  const [address, setAddress] = useState('')
  const [safetyData, setSafetyData] = useState(null)
  const [socialData, setSocialData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [socialLoading, setSocialLoading] = useState(false)
  const [hour, setHour] = useState(new Date().getHours())
  const [flyTarget, setFlyTarget] = useState(null)

  // Fetch heatmap on mount
  useEffect(() => {
    axios.get('/api/heatmap')
      .then(res => setHeatmapPoints(res.data.points))
      .catch(console.error)
  }, [])

  const fetchSafety = useCallback(async (lat, lng, h = hour) => {
    setLoading(true)
    setSocialLoading(true)
    setSafetyData(null)
    setSocialData(null)
    // Use allSettled so a failing social fetch never blocks the safety panel
    const [safetyResult, socialResult] = await Promise.allSettled([
      axios.get('/api/safety', { params: { lat, lng, hour: h } }),
      axios.get('/api/posts', { params: { lat, lng, hour: h } }),
    ])
    if (safetyResult.status === 'fulfilled') {
      setSafetyData(safetyResult.value.data)
    } else {
      console.error('Safety fetch failed:', safetyResult.reason)
    }
    if (socialResult.status === 'fulfilled') {
      setSocialData(socialResult.value.data)
    } else {
      console.error('Social fetch failed:', socialResult.reason)
    }
    setLoading(false)
    setSocialLoading(false)
  }, [hour])

  const reverseGeocode = async (lat, lng) => {
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json`
      )
      const data = await res.json()
      return data.display_name || `${lat.toFixed(5)}, ${lng.toFixed(5)}`
    } catch {
      return `${lat.toFixed(5)}, ${lng.toFixed(5)}`
    }
  }

  const handleMapClick = async ({ lat, lng }) => {
    setSelectedPos([lat, lng])
    const addr = await reverseGeocode(lat, lng)
    setAddress(addr)
    fetchSafety(lat, lng)
  }

  const handleLocationSelect = async ({ lat, lng, address: addr }) => {
    setSelectedPos([lat, lng])
    setAddress(addr)
    setFlyTarget({ lat, lng })
    fetchSafety(lat, lng)
  }

  const handleHourChange = (h) => {
    setHour(h)
    if (selectedPos) {
      fetchSafety(selectedPos[0], selectedPos[1], h)
    }
  }

  // Re-fetch posts only (after user submits a post)
  const handlePostSubmitted = useCallback(async () => {
    if (!selectedPos) return
    setSocialLoading(true)
    try {
      const res = await axios.get('/api/posts', { params: { lat: selectedPos[0], lng: selectedPos[1], hour } })
      setSocialData(res.data)
    } catch (e) {
      console.error(e)
    } finally {
      setSocialLoading(false)
    }
  }, [selectedPos, hour])

  const handleClose = () => {
    setSelectedPos(null)
    setSafetyData(null)
    setSocialData(null)
    setAddress('')
  }

  // Clamp adjusted score within 1–99
  const adjustedScore = safetyData
    ? Math.max(1, Math.min(99, safetyData.score + (socialData?.total_impact ?? 0)))
    : null

  // Re-derive risk label from adjusted score for the marker colour
  const getRiskFromScore = (s) => {
    if (s >= 75) return 'Low'
    if (s >= 50) return 'Medium'
    if (s >= 30) return 'High'
    return 'Critical'
  }

  const riskLevel = adjustedScore !== null ? getRiskFromScore(adjustedScore) : null

  return (
    <div className="relative w-full h-full bg-[#0a0e1a]">
      {/* Map */}
      <MapView
        heatmapPoints={heatmapPoints}
        markerPos={selectedPos}
        riskLevel={riskLevel}
        onMapClick={handleMapClick}
        flyTarget={flyTarget}
      />

      {/* Logo / Top bar */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[1000] pointer-events-none">
        <div
          className="flex items-center gap-2 px-4 py-2 rounded-full"
          style={{ background: 'rgba(10,14,26,0.85)', border: '1px solid rgba(255,255,255,0.08)', backdropFilter: 'blur(16px)' }}
        >
          <Navigation2 size={16} className="text-blue-400" />
          <span className="text-white font-bold text-sm tracking-wide">Street<span className="text-blue-400">Sense</span></span>
          <span className="text-gray-600 text-xs ml-1">London</span>
        </div>
      </div>

      {/* Left panel */}
      <div
        className="absolute top-4 left-4 z-[1000] pointer-events-auto"
        style={{ width: '300px' }}
      >
        <div
          className="rounded-2xl p-4 flex flex-col gap-4"
          style={{ background: 'rgba(10,14,26,0.92)', border: '1px solid rgba(255,255,255,0.08)', backdropFilter: 'blur(20px)' }}
        >
          <SearchBar onLocationSelect={handleLocationSelect} />
          <div className="border-t border-white/5 pt-3">
            <TimeSlider hour={hour} onChange={handleHourChange} />
          </div>

          {/* Hint */}
          {!selectedPos && (
            <div className="flex items-start gap-2 p-3 rounded-xl bg-blue-950/30 border border-blue-900/30">
              <Info size={13} className="text-blue-400 mt-0.5 flex-shrink-0" />
              <p className="text-xs text-gray-400 leading-relaxed">
                <span className="text-gray-300 font-medium">Click anywhere on the map</span> or search a street to get a real-time safety report.
              </p>
            </div>
          )}

          {/* Loading state */}
          {loading && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-white/5">
              <div className="w-4 h-4 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin" />
              <span className="text-xs text-gray-400">Analysing area...</span>
            </div>
          )}
        </div>

        {/* Legend */}
        <div
          className="mt-3 rounded-xl px-4 py-3"
          style={{ background: 'rgba(10,14,26,0.85)', border: '1px solid rgba(255,255,255,0.06)', backdropFilter: 'blur(16px)' }}
        >
          <div className="text-xs text-gray-500 uppercase tracking-widest font-semibold mb-2">Heatmap Legend</div>
          <div className="flex items-center gap-1.5">
            <div className="flex-1 h-2 rounded-full" style={{ background: 'linear-gradient(to right, #1d4ed8, #7c3aed, #dc2626, #ea580c, #fbbf24)' }} />
          </div>
          <div className="flex justify-between text-xs text-gray-600 mt-1">
            <span>Safer</span>
            <span>Higher Risk</span>
          </div>
        </div>
      </div>

      {/* Right metrics panel */}
      {safetyData && (
        <MetricsPanel
          data={safetyData}
          address={address.split(',').slice(0, 3).join(',')}
          onClose={handleClose}
          socialData={socialData}
          socialLoading={socialLoading}
          adjustedScore={adjustedScore}
          selectedPos={selectedPos}
          onPostSubmitted={handlePostSubmitted}
        />
      )}
    </div>
  )
}

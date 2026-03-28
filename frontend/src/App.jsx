import { useState, useCallback } from 'react'
import { Navigation2, Info, MapPin, Route, Sun, Moon } from 'lucide-react'
import MapView from './components/MapView'
import MetricsPanel from './components/MetricsPanel'
import SearchBar from './components/SearchBar'
import TimeSlider from './components/TimeSlider'
import RoutingPanel from './components/RoutingPanel'
import axios from 'axios'

export default function App() {
  const [selectedPos, setSelectedPos] = useState(null)
  const [address, setAddress] = useState('')
  const [safetyData, setSafetyData] = useState(null)
  const [socialData, setSocialData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [socialLoading, setSocialLoading] = useState(false)
  const [hour, setHour] = useState(new Date().getHours())
  const [flyTarget, setFlyTarget] = useState(null)

  // Routing mode
  const [appMode, setAppMode] = useState('explore') // 'explore' | 'route'
  const [routeData, setRouteData] = useState(null)
  const [nightMode, setNightMode] = useState(true)

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
    if (appMode === 'route') return  // map clicks disabled in routing mode
    setSelectedPos([lat, lng])
    const addr = await reverseGeocode(lat, lng)
    setAddress(addr)
    fetchSafety(lat, lng)
  }

  const handleSwitchMode = (mode) => {
    setAppMode(mode)
    if (mode === 'route') {
      // Clear explore state when switching to route mode
      setSelectedPos(null)
      setSafetyData(null)
      setSocialData(null)
    } else {
      // Clear route when switching back to explore
      setRouteData(null)
    }
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
        markerPos={selectedPos}
        riskLevel={riskLevel}
        onMapClick={handleMapClick}
        flyTarget={flyTarget}
        routeData={routeData}
        nightMode={nightMode}
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
        className="absolute top-4 left-4 bottom-4 z-[1000] pointer-events-auto flex flex-col gap-3"
        style={{ width: '300px' }}
      >
        <div
          className="rounded-2xl flex flex-col overflow-hidden flex-1"
          style={{ background: 'rgba(10,14,26,0.92)', border: '1px solid rgba(255,255,255,0.08)', backdropFilter: 'blur(20px)' }}
        >
          {/* Mode toggle */}
          <div className="p-3 pb-0 flex-shrink-0">
            <div className="flex p-1 gap-1 rounded-xl" style={{ background: 'rgba(255,255,255,0.04)' }}>
              <button
                onClick={() => handleSwitchMode('explore')}
                className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-all"
                style={{
                  background: appMode === 'explore' ? 'rgba(255,255,255,0.10)' : 'transparent',
                  color: appMode === 'explore' ? '#fff' : '#6b7280',
                }}
              >
                <MapPin size={12} />
                <span>Explore</span>
              </button>
              <button
                onClick={() => handleSwitchMode('route')}
                className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-all"
                style={{
                  background: appMode === 'route' ? 'rgba(255,255,255,0.10)' : 'transparent',
                  color: appMode === 'route' ? '#fff' : '#6b7280',
                }}
              >
                <Route size={12} />
                <span>Route</span>
              </button>
            </div>
          </div>

          {/* Panel content — scrollable */}
          <div className="flex-1 overflow-y-auto metrics-scroll p-4 flex flex-col gap-4">
            {appMode === 'explore' ? (
              <>
                <SearchBar onLocationSelect={handleLocationSelect} />
                <div className="border-t border-white/5 pt-1">
                  <TimeSlider hour={hour} onChange={handleHourChange} />
                </div>
                {!selectedPos && (
                  <div className="flex items-start gap-2 p-3 rounded-xl bg-blue-950/30 border border-blue-900/30">
                    <Info size={13} className="text-blue-400 mt-0.5 flex-shrink-0" />
                    <p className="text-xs text-gray-400 leading-relaxed">
                      <span className="text-gray-300 font-medium">Click the map</span> or search to get a safety report.
                    </p>
                  </div>
                )}
                {loading && (
                  <div className="flex items-center gap-2 p-3 rounded-xl bg-white/5">
                    <div className="w-4 h-4 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin" />
                    <span className="text-xs text-gray-400">Analysing area...</span>
                  </div>
                )}
              </>
            ) : (
              <>
                <TimeSlider hour={hour} onChange={handleHourChange} />
                <div className="border-t border-white/5" />
                <RoutingPanel
                  hour={hour}
                  onRouteFound={setRouteData}
                  onClear={() => setRouteData(null)}
                />
              </>
            )}
          </div>
        </div>

        {/* Route legend */}
        {appMode === 'route' && routeData && (
          <div
            className="rounded-xl px-4 py-3 flex-shrink-0"
            style={{ background: 'rgba(10,14,26,0.85)', border: '1px solid rgba(255,255,255,0.06)', backdropFilter: 'blur(16px)' }}
          >
            <div className="text-xs text-gray-500 uppercase tracking-widest font-semibold mb-2">Route Safety</div>
            <div className="flex items-center gap-2">
              {[['#10b981','Safe'],['#f59e0b','Caution'],['#f97316','Risky'],['#ef4444','Danger']].map(([c, l]) => (
                <div key={l} className="flex items-center gap-1">
                  <div className="w-3 h-3 rounded-sm" style={{ background: c }} />
                  <span className="text-xs text-gray-500">{l}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Map toggles — bottom right */}
      <div className="absolute bottom-6 right-6 z-[1000] flex flex-col gap-2 pointer-events-auto">
        <button
          onClick={() => setNightMode(v => !v)}
          title={nightMode ? 'Switch to day map' : 'Switch to night map'}
          className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold transition-all"
          style={{
            background: nightMode ? 'rgba(99,102,241,0.18)' : 'rgba(255,255,255,0.06)',
            border: `1px solid ${nightMode ? 'rgba(99,102,241,0.4)' : 'rgba(255,255,255,0.10)'}`,
            color: nightMode ? '#818cf8' : '#6b7280',
            backdropFilter: 'blur(12px)',
          }}
        >
          {nightMode ? <Moon size={13} /> : <Sun size={13} />}
          <span>{nightMode ? 'Night' : 'Day'}</span>
        </button>
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

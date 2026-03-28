import React, { useState, useRef } from 'react'
import { MapPin, Navigation, Footprints, Bike, Car, Bus, Loader2, ArrowRight, Star, Clock, Ruler, ChevronRight } from 'lucide-react'
import axios from 'axios'

// ── Shared helpers ────────────────────────────────────────────────────────

const RISK_COLORS = {
  Low: '#10b981', Medium: '#f59e0b', High: '#f97316', Critical: '#ef4444',
}

function scoreColor(s) {
  if (s >= 75) return '#10b981'
  if (s >= 50) return '#f59e0b'
  if (s >= 30) return '#f97316'
  return '#ef4444'
}

function formatDuration(s) {
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.round(s / 60)} min`
  return `${(s / 3600).toFixed(1)} hr`
}

function formatDistance(m) {
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${m} m`
}

// ── LocationInput ──────────────────────────────────────────────────────────

function LocationInput({ placeholder, value, onSelect, Icon, color }) {
  const [query, setQuery] = useState(value?.address || '')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const debounce = useRef(null)

  const search = async (q) => {
    if (q.length < 3) { setResults([]); return }
    setSearching(true)
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=4&countrycodes=gb`
      )
      setResults(await res.json())
    } catch { setResults([]) }
    finally { setSearching(false) }
  }

  const handleChange = (e) => {
    setQuery(e.target.value)
    onSelect(null)
    clearTimeout(debounce.current)
    debounce.current = setTimeout(() => search(e.target.value), 350)
  }

  const handleSelect = (item) => {
    const address = item.display_name.split(',').slice(0, 2).join(',')
    setQuery(address)
    setResults([])
    onSelect({ lat: parseFloat(item.lat), lng: parseFloat(item.lon), address })
  }

  return (
    <div className="relative">
      <div
        className="flex items-center gap-2 px-3 py-2.5 rounded-xl"
        style={{ background: 'rgba(255,255,255,0.06)', border: `1px solid ${value ? color + '40' : 'rgba(255,255,255,0.10)'}` }}
      >
        <Icon size={13} style={{ color: value ? color : '#6b7280' }} className="flex-shrink-0" />
        <input
          type="text"
          value={query}
          onChange={handleChange}
          placeholder={placeholder}
          className="flex-1 bg-transparent text-sm text-white placeholder-gray-600 outline-none"
        />
        {searching
          ? <Loader2 size={12} className="text-gray-500 animate-spin flex-shrink-0" />
          : value && <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: color }} />
        }
      </div>
      {results.length > 0 && (
        <div
          className="absolute top-full left-0 right-0 mt-1 rounded-xl overflow-hidden z-50"
          style={{ background: 'rgba(10,14,26,0.98)', border: '1px solid rgba(255,255,255,0.08)', backdropFilter: 'blur(16px)' }}
        >
          {results.map(item => (
            <button
              key={item.place_id}
              onClick={() => handleSelect(item)}
              className="w-full text-left px-3 py-2.5 text-xs hover:bg-white/8 border-b border-white/5 last:border-0 transition-colors"
            >
              <span className="font-medium text-white">{item.display_name.split(',')[0]}</span>
              <span className="text-gray-500 ml-1">{item.display_name.split(',').slice(1, 3).join(',')}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Mode selector ──────────────────────────────────────────────────────────

const MODES = [
  { id: 'foot', label: 'Walk', Icon: Footprints },
  { id: 'bike', label: 'Cycle', Icon: Bike },
  { id: 'car', label: 'Drive', Icon: Car },
  { id: 'bus', label: 'Bus', Icon: Bus },
]

function ModeSelector({ selected, onChange }) {
  return (
    <div className="flex gap-1.5">
      {MODES.map(({ id, label, Icon }) => {
        const active = selected === id
        return (
          <button
            key={id}
            onClick={() => onChange(id)}
            className="flex-1 flex flex-col items-center gap-1 py-2.5 rounded-xl text-xs font-semibold transition-all"
            style={{
              background: active ? 'rgba(96,165,250,0.12)' : 'rgba(255,255,255,0.04)',
              border: `1px solid ${active ? 'rgba(96,165,250,0.30)' : 'rgba(255,255,255,0.06)'}`,
              color: active ? '#60a5fa' : '#6b7280',
            }}
          >
            <Icon size={15} />
            <span>{label}</span>
          </button>
        )
      })}
    </div>
  )
}

// ── Safety bar (mini route risk profile) ──────────────────────────────────

function SafetyBar({ samples }) {
  if (!samples || samples.length === 0) return null
  return (
    <div className="flex gap-0.5 h-2 rounded-full overflow-hidden">
      {samples.map((s, i) => (
        <div key={i} className="flex-1" style={{ background: scoreColor(s.score) }} />
      ))}
    </div>
  )
}

// ── Mode comparison table ─────────────────────────────────────────────────

function ModeComparison({ comparison, currentMode }) {
  return (
    <div className="flex flex-col gap-1.5">
      {comparison.map((m, i) => {
        const isBest = i === 0
        const isCurrent = m.mode === currentMode
        const color = scoreColor(m.effective_safety)
        return (
          <div
            key={m.mode}
            className="flex items-center gap-2.5 px-3 py-2 rounded-xl"
            style={{
              background: isBest ? `${color}12` : 'rgba(255,255,255,0.04)',
              border: `1px solid ${isBest ? color + '30' : 'rgba(255,255,255,0.06)'}`,
            }}
          >
            <span className="text-base">{m.icon}</span>
            <div className="flex-1">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-semibold text-white">{m.label}</span>
                {isBest && (
                  <span className="text-xs px-1.5 py-0.5 rounded-full font-bold" style={{ background: `${color}20`, color }}>
                    safest
                  </span>
                )}
                {isCurrent && !isBest && (
                  <span className="text-xs text-gray-500">selected</span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-bold" style={{ color }}>{m.effective_safety}</span>
              <span className="text-xs text-gray-600">/100</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Main RoutingPanel ──────────────────────────────────────────────────────

export default function RoutingPanel({ hour, onRouteFound, onClear }) {
  const [from, setFrom] = useState(null)
  const [to, setTo] = useState(null)
  const [mode, setMode] = useState('foot')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  const canRoute = from && to

  const handleFindRoute = async () => {
    if (!canRoute) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const res = await axios.get('/api/route', {
        params: {
          from_lat: from.lat, from_lng: from.lng,
          to_lat: to.lat,   to_lng: to.lng,
          mode, hour,
        },
      })
      setResult(res.data)
      onRouteFound({
        routes: res.data.routes,
        fromPos: [from.lat, from.lng],
        toPos:   [to.lat,   to.lng],
      })
    } catch {
      setError('Routing failed — check your connection or try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleClear = () => {
    setFrom(null)
    setTo(null)
    setResult(null)
    setError('')
    onClear()
  }

  const recommended = result?.routes?.find(r => r.is_recommended) || result?.routes?.[0]

  return (
    <div className="flex flex-col gap-3">
      {/* Location inputs */}
      <div className="flex flex-col gap-1.5">
        <LocationInput
          placeholder="From — search a place..."
          value={from}
          onSelect={setFrom}
          Icon={Navigation}
          color="#10b981"
        />
        <div className="flex items-center gap-2 px-3">
          <div className="flex-1 border-t border-white/10" />
          <ArrowRight size={11} className="text-gray-600" />
          <div className="flex-1 border-t border-white/10" />
        </div>
        <LocationInput
          placeholder="To — search a place..."
          value={to}
          onSelect={setTo}
          Icon={MapPin}
          color="#6366f1"
        />
      </div>

      {/* Mode selector */}
      <ModeSelector selected={mode} onChange={(m) => { setMode(m); setResult(null) }} />

      {/* Action buttons */}
      <div className="flex gap-2">
        <button
          onClick={handleFindRoute}
          disabled={!canRoute || loading}
          className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-bold transition-all"
          style={{
            background: canRoute && !loading ? 'rgba(96,165,250,0.18)' : 'rgba(255,255,255,0.05)',
            border: `1px solid ${canRoute && !loading ? 'rgba(96,165,250,0.35)' : 'rgba(255,255,255,0.08)'}`,
            color: canRoute && !loading ? '#60a5fa' : '#4b5563',
            cursor: canRoute && !loading ? 'pointer' : 'not-allowed',
          }}
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Navigation size={14} />}
          {loading ? 'Finding safest route...' : 'Find Safest Route'}
        </button>
        {(result || from || to) && (
          <button
            onClick={handleClear}
            className="px-3 py-2.5 rounded-xl text-xs text-gray-500 hover:text-gray-300 transition-colors"
            style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}
          >
            Clear
          </button>
        )}
      </div>

      {error && <p className="text-xs text-red-400 px-1">{error}</p>}

      {/* ── Results ── */}
      {recommended && (
        <div className="flex flex-col gap-3 fade-up">
          <div className="border-t border-white/5" />

          {/* Main route card */}
          <div
            className="rounded-2xl p-4 flex flex-col gap-3"
            style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}
          >
            {/* Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Star size={12} className="text-yellow-400" />
                <span className="text-xs font-bold text-white">Recommended Route</span>
              </div>
              <div
                className="text-xs font-bold px-2 py-0.5 rounded-full"
                style={{
                  color: scoreColor(recommended.effective_safety),
                  background: `${scoreColor(recommended.effective_safety)}20`,
                }}
              >
                {recommended.risk_level} Risk
              </div>
            </div>

            {/* Score + stats row */}
            <div className="flex items-center gap-4">
              <div className="flex flex-col items-center">
                <span className="text-3xl font-extrabold" style={{ color: scoreColor(recommended.effective_safety) }}>
                  {recommended.effective_safety}
                </span>
                <span className="text-xs text-gray-500">/ 100</span>
              </div>
              <div className="flex-1 flex flex-col gap-1.5">
                <div className="flex items-center gap-1.5 text-xs text-gray-400">
                  <Clock size={11} className="text-gray-500" />
                  <span>{formatDuration(recommended.duration_s)}</span>
                  <span className="text-gray-600">·</span>
                  <Ruler size={11} className="text-gray-500" />
                  <span>{formatDistance(recommended.distance_m)}</span>
                </div>
                <SafetyBar samples={recommended.safety_samples} />
                <div className="flex justify-between text-xs text-gray-600">
                  <span>Safer</span>
                  <span>Riskier</span>
                </div>
              </div>
            </div>

            {result?.recommended_mode !== mode && (
              <div
                className="flex items-center gap-2 p-2.5 rounded-xl text-xs"
                style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)' }}
              >
                <span className="text-lg">
                  {result.mode_comparison[0]?.icon}
                </span>
                <p className="text-gray-300">
                  <span className="text-indigo-300 font-semibold">
                    {result.mode_comparison[0]?.label}
                  </span>{' '}
                  would be safer ({result.mode_comparison[0]?.effective_safety}/100)
                </p>
              </div>
            )}
          </div>

          {/* Mode comparison */}
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-widest font-semibold mb-2">Mode Comparison</p>
            <ModeComparison comparison={result.mode_comparison} currentMode={mode} />
          </div>
        </div>
      )}
    </div>
  )
}

import React, { useState, useRef } from 'react'
import { Search, Loader2 } from 'lucide-react'

export default function SearchBar({ onLocationSelect }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const debounceRef = useRef(null)

  const search = async (q) => {
    if (q.length < 3) { setResults([]); return }
    setLoading(true)
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=5&countrycodes=gb`
      )
      const data = await res.json()
      setResults(data)
    } catch {
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  const handleChange = (e) => {
    const val = e.target.value
    setQuery(val)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => search(val), 350)
  }

  const handleSelect = (item) => {
    setQuery(item.display_name.split(',').slice(0, 2).join(','))
    setResults([])
    onLocationSelect({
      lat: parseFloat(item.lat),
      lng: parseFloat(item.lon),
      address: item.display_name,
    })
  }

  return (
    <div className="relative w-full">
      <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl" style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.10)' }}>
        {loading
          ? <Loader2 size={15} className="text-gray-400 animate-spin flex-shrink-0" />
          : <Search size={15} className="text-gray-400 flex-shrink-0" />
        }
        <input
          type="text"
          value={query}
          onChange={handleChange}
          placeholder="Search any street or postcode..."
          className="flex-1 bg-transparent text-sm text-white placeholder-gray-500 outline-none"
        />
      </div>

      {results.length > 0 && (
        <div
          className="absolute top-full left-0 right-0 mt-1.5 rounded-xl overflow-hidden z-50"
          style={{ background: 'rgba(13,21,38,0.98)', border: '1px solid rgba(255,255,255,0.08)', backdropFilter: 'blur(20px)' }}
        >
          {results.map((item) => (
            <button
              key={item.place_id}
              onClick={() => handleSelect(item)}
              className="w-full text-left px-3 py-2.5 text-sm text-gray-300 hover:bg-white/8 hover:text-white transition-colors border-b border-white/5 last:border-0"
            >
              <span className="font-medium text-white">
                {item.display_name.split(',')[0]}
              </span>
              <span className="text-gray-500 text-xs ml-1">
                {item.display_name.split(',').slice(1, 3).join(',')}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

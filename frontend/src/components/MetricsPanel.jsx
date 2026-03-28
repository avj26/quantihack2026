import React, { useState } from 'react'
import { Lightbulb, Users, AlertTriangle, Clock, Camera, MapPin, X, ShieldCheck, Radio, Cloud, Wind, Thermometer } from 'lucide-react'
import SafetyGauge from './SafetyGauge'
import MetricCard from './MetricCard'
import SocialFeed from './SocialFeed'

function WeatherRow({ weather }) {
  if (!weather) return null
  const modColor = weather.modifier < -0.10 ? '#f97316' : weather.modifier < -0.04 ? '#f59e0b' : '#10b981'
  return (
    <div
      className="flex items-center gap-3 px-3 py-2.5 rounded-xl"
      style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)' }}
    >
      <Cloud size={13} className="text-blue-300 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-xs font-semibold text-white leading-tight truncate">{weather.condition}</div>
        <div className="flex items-center gap-2 mt-0.5 text-xs text-gray-500">
          <Thermometer size={10} />
          <span>{weather.temp_c != null ? `${Math.round(weather.temp_c)}°C` : '—'}</span>
          <Wind size={10} />
          <span>{weather.wind_kmh != null ? `${Math.round(weather.wind_kmh)} km/h` : '—'}</span>
        </div>
      </div>
      <div className="text-xs font-bold" style={{ color: modColor }}>
        {weather.modifier >= 0 ? '+' : ''}{Math.round(weather.modifier * 100)}
      </div>
    </div>
  )
}

function ScoreBreakdown({ breakdown }) {
  if (!breakdown) return null
  const rows = [
    { label: 'Base score', value: breakdown.base, color: '#60a5fa' },
    { label: 'Crime data', value: breakdown.crime, color: breakdown.crime < 0 ? '#f97316' : '#10b981' },
    { label: 'Weather', value: breakdown.weather, color: breakdown.weather < 0 ? '#f59e0b' : '#10b981' },
    { label: 'Road condition', value: breakdown.road, color: breakdown.road < 0 ? '#f97316' : '#10b981' },
  ]
  return (
    <div className="flex flex-col gap-1.5">
      {rows.map(r => (
        <div key={r.label} className="flex items-center justify-between text-xs">
          <span className="text-gray-500">{r.label}</span>
          <span className="font-bold" style={{ color: r.color }}>
            {r.label === 'Base score' ? r.value : (r.value >= 0 ? `+${r.value}` : r.value)}
          </span>
        </div>
      ))}
    </div>
  )
}

function DataSources({ sources }) {
  if (!sources || sources.length === 0) return null
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {sources.map(s => (
        <span
          key={s}
          className="text-xs px-2 py-0.5 rounded-full"
          style={{ background: 'rgba(96,165,250,0.1)', color: '#60a5fa', border: '1px solid rgba(96,165,250,0.2)' }}
        >
          {s}
        </span>
      ))}
    </div>
  )
}

const TABS = [
  { id: 'report', label: 'Safety Report', Icon: ShieldCheck },
  { id: 'social', label: 'Social Pulse', Icon: Radio },
]

export default function MetricsPanel({
  data,
  address,
  onClose,
  socialData,
  socialLoading,
  adjustedScore,
  selectedPos,
  onPostSubmitted,
}) {
  const [activeTab, setActiveTab] = useState('report')

  if (!data) return null

  const { risk_level, summary, metrics, weather, road_flags, score_breakdown, data_sources } = data
  const displayScore = adjustedScore ?? data.score
  const userPostCount = socialData?.user_post_count ?? 0

  return (
    <div className="slide-in absolute top-4 right-4 bottom-4 w-80 flex flex-col gap-3 z-[1000] pointer-events-auto">
      {/* ── Header: address + gauge ── */}
      <div
        className="rounded-2xl overflow-hidden flex-shrink-0"
        style={{ background: 'rgba(10,14,26,0.95)', backdropFilter: 'blur(20px)', border: '1px solid rgba(255,255,255,0.08)' }}
      >
        {/* Address row */}
        <div className="flex items-start justify-between p-4 pb-2">
          <div className="flex-1 min-w-0">
            <div className="text-xs text-gray-500 uppercase tracking-widest font-semibold">Safety Report</div>
            {address && (
              <div className="flex items-center gap-1.5 mt-1.5">
                <MapPin size={12} className="text-blue-400 flex-shrink-0" />
                <span className="text-sm text-gray-200 font-medium leading-tight line-clamp-2">{address}</span>
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="ml-2 p-1.5 rounded-lg hover:bg-white/10 transition-colors flex-shrink-0"
          >
            <X size={14} className="text-gray-400" />
          </button>
        </div>

        {/* Gauge */}
        <div className="px-4 pb-3">
          <SafetyGauge
            score={displayScore}
            riskLevel={risk_level}
            socialDelta={socialData?.total_impact}
          />
        </div>

        {/* Tab bar */}
        <div className="px-3 pb-3">
          <div className="flex p-1 gap-1 rounded-xl" style={{ background: 'rgba(255,255,255,0.04)' }}>
            {TABS.map(({ id, label, Icon }) => {
              const active = activeTab === id
              const badge = id === 'social' && socialData?.post_count
              return (
                <button
                  key={id}
                  onClick={() => setActiveTab(id)}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-all"
                  style={{
                    background: active ? 'rgba(255,255,255,0.10)' : 'transparent',
                    color: active ? '#fff' : '#6b7280',
                  }}
                >
                  <Icon size={12} />
                  <span>{label}</span>
                  {badge ? (
                    <span
                      className="text-xs px-1.5 rounded-full font-bold"
                      style={{ background: 'rgba(96,165,250,0.2)', color: '#60a5fa' }}
                    >
                      {badge}
                    </span>
                  ) : null}
                  {id === 'social' && userPostCount > 0 && !badge ? (
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
                  ) : null}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* ── Tab content (scrollable) ── */}
      <div
        className="rounded-2xl flex-1 overflow-y-auto metrics-scroll"
        style={{ background: 'rgba(10,14,26,0.95)', backdropFilter: 'blur(20px)', border: '1px solid rgba(255,255,255,0.08)' }}
      >
        <div className="p-4">
          {activeTab === 'report' && (
            <div className="flex flex-col gap-5 fade-up">
              {/* Summary */}
              <div>
                <div className="text-xs text-gray-500 uppercase tracking-widest font-semibold mb-2">Summary</div>
                <p className="text-sm text-gray-300 leading-relaxed">{summary}</p>
              </div>

              <div className="border-t border-white/5" />

              {/* Weather */}
              {weather && (
                <>
                  <div>
                    <div className="text-xs text-gray-500 uppercase tracking-widest font-semibold mb-2">Current Weather</div>
                    <WeatherRow weather={weather} />
                  </div>
                  <div className="border-t border-white/5" />
                </>
              )}

              {/* Road flags */}
              {road_flags && road_flags.length > 0 && (
                <>
                  <div>
                    <div className="text-xs text-gray-500 uppercase tracking-widest font-semibold mb-2">Road Conditions</div>
                    <div className="flex flex-col gap-1.5">
                      {road_flags.map(f => (
                        <div key={f} className="flex items-center gap-2 text-xs text-orange-300">
                          <AlertTriangle size={11} className="flex-shrink-0" />
                          <span>{f}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="border-t border-white/5" />
                </>
              )}

              {/* Metrics */}
              <div>
                <div className="text-xs text-gray-500 uppercase tracking-widest font-semibold mb-3">Area Metrics</div>
                <div className="flex flex-col gap-2">
                  <MetricCard icon={Lightbulb} label="Street Lighting" value={metrics.lighting} />
                  <MetricCard icon={Users} label="Foot Traffic" value={metrics.foot_traffic} />
                  <MetricCard icon={AlertTriangle} label="Incidents (30d)" value={metrics.incidents_30d} isNumber />
                  <MetricCard icon={Clock} label="Avg Response Time" value={metrics.response_time_min} subtext="mins" isNumber />
                  <MetricCard icon={Camera} label="CCTV Coverage" value={metrics.cctv_coverage} />
                </div>
              </div>

              {/* Score breakdown */}
              {score_breakdown && (
                <>
                  <div className="border-t border-white/5" />
                  <div>
                    <div className="text-xs text-gray-500 uppercase tracking-widest font-semibold mb-2">Score Breakdown</div>
                    <ScoreBreakdown breakdown={score_breakdown} />
                  </div>
                </>
              )}

              {/* Data sources */}
              {data_sources && data_sources.length > 0 && (
                <>
                  <div className="border-t border-white/5" />
                  <div>
                    <div className="text-xs text-gray-500 uppercase tracking-widest font-semibold mb-2">Live Data Sources</div>
                    <DataSources sources={data_sources} />
                  </div>
                </>
              )}
            </div>
          )}

          {activeTab === 'social' && (
            <div className="fade-up">
              <SocialFeed
                posts={socialData?.posts}
                totalImpact={socialData?.total_impact}
                loading={socialLoading}
                selectedPos={selectedPos}
                onPosted={onPostSubmitted}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

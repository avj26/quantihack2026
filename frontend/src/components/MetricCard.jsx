import React from 'react'

const VALUE_COLORS = {
  Good: '#10b981',
  High: '#10b981',
  Low: '#6b7280',
  Medium: '#f59e0b',
  Fair: '#f59e0b',
  Poor: '#ef4444',
  Critical: '#ef4444',
}

export default function MetricCard({ icon: Icon, label, value, subtext, isNumber }) {
  const color = isNumber ? '#60a5fa' : (VALUE_COLORS[value] || '#e5e7eb')

  return (
    <div className="flex items-center gap-3 p-3 rounded-xl bg-white/5 border border-white/5 hover:bg-white/8 transition-colors">
      <div className="flex-shrink-0 w-9 h-9 rounded-lg bg-white/5 flex items-center justify-center">
        <Icon size={16} color="#9ca3af" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-xs text-gray-500 font-medium uppercase tracking-wider">{label}</div>
        <div className="flex items-baseline gap-1 mt-0.5">
          <span className="text-sm font-bold" style={{ color }}>
            {value}
          </span>
          {subtext && <span className="text-xs text-gray-500">{subtext}</span>}
        </div>
      </div>
      {/* Dot indicator */}
      {!isNumber && (
        <div
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ background: color, boxShadow: `0 0 6px ${color}` }}
        />
      )}
    </div>
  )
}

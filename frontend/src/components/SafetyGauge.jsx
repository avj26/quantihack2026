import React from 'react'
import { TrendingUp, TrendingDown } from 'lucide-react'

const COLORS = {
  Low: { stroke: '#10b981', glow: '#10b98140', label: 'SAFE', bg: 'from-emerald-900/30 to-emerald-800/10' },
  Medium: { stroke: '#f59e0b', glow: '#f59e0b40', label: 'CAUTION', bg: 'from-amber-900/30 to-amber-800/10' },
  High: { stroke: '#f97316', glow: '#f9731640', label: 'RISKY', bg: 'from-orange-900/30 to-orange-800/10' },
  Critical: { stroke: '#ef4444', glow: '#ef444440', label: 'DANGER', bg: 'from-red-900/30 to-red-800/10' },
}

export default function SafetyGauge({ score, riskLevel, socialDelta }) {
  const radius = 54
  const circumference = 2 * Math.PI * radius
  const progress = (score / 100) * circumference
  const color = COLORS[riskLevel] || COLORS.Medium

  const hasDelta = socialDelta !== undefined && socialDelta !== null && socialDelta !== 0
  const deltaPositive = socialDelta > 0
  const DeltaIcon = deltaPositive ? TrendingUp : TrendingDown
  const deltaColor = deltaPositive ? '#10b981' : '#ef4444'

  return (
    <div className={`flex flex-col items-center p-5 rounded-2xl bg-gradient-to-b ${color.bg} border border-white/5`}>
      <div className="relative">
        {/* Pulse ring */}
        <div
          className="absolute inset-0 rounded-full"
          style={{
            background: `radial-gradient(circle, ${color.glow} 0%, transparent 70%)`,
            animation: 'pulse-ring 2.5s ease-in-out infinite',
          }}
        />
        <svg width="140" height="140" viewBox="0 0 140 140">
          {/* Track */}
          <circle cx="70" cy="70" r={radius} fill="none" stroke="#1f2937" strokeWidth="10" />
          {/* Progress */}
          <circle
            cx="70"
            cy="70"
            r={radius}
            fill="none"
            stroke={color.stroke}
            strokeWidth="10"
            strokeDasharray={`${progress} ${circumference}`}
            strokeLinecap="round"
            transform="rotate(-90 70 70)"
            style={{
              transition: 'stroke-dasharray 0.8s cubic-bezier(0.4,0,0.2,1)',
              filter: `drop-shadow(0 0 6px ${color.stroke})`,
            }}
          />
          {/* Score text */}
          <text x="70" y="64" textAnchor="middle" fill="white" fontSize="30" fontWeight="800" fontFamily="Inter">
            {score}
          </text>
          <text x="70" y="82" textAnchor="middle" fill="#6b7280" fontSize="11" fontFamily="Inter">
            out of 100
          </text>
        </svg>
      </div>

      <div className="flex items-center gap-2 mt-1">
        <div
          className="text-xs font-bold tracking-widest px-3 py-1 rounded-full"
          style={{ color: color.stroke, background: `${color.glow}` }}
        >
          {color.label}
        </div>

        {/* Social delta badge */}
        {hasDelta && (
          <div
            className="flex items-center gap-0.5 text-xs font-bold px-2 py-1 rounded-full"
            style={{ color: deltaColor, background: `${deltaColor}20` }}
            title="Adjusted by social media analysis"
          >
            <DeltaIcon size={10} />
            <span>{deltaPositive ? '+' : ''}{socialDelta}</span>
          </div>
        )}
      </div>

      {hasDelta && (
        <p className="text-xs text-gray-600 mt-1.5">
          social reports applied
        </p>
      )}
    </div>
  )
}

import React from 'react'
import { Moon, Sun } from 'lucide-react'

function formatHour(h) {
  if (h === 0) return '12 AM'
  if (h === 12) return '12 PM'
  return h < 12 ? `${h} AM` : `${h - 12} PM`
}

function getTimeGradientColor(h) {
  if (h >= 6 && h < 18) return '#f59e0b'
  if (h >= 18 && h < 21) return '#f97316'
  return '#818cf8'
}

export default function TimeSlider({ hour, onChange }) {
  const color = getTimeGradientColor(hour)
  const isDay = hour >= 6 && hour < 20

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500 uppercase tracking-wider font-semibold">Time of Day</span>
        <div className="flex items-center gap-1.5">
          {isDay ? <Sun size={13} color={color} /> : <Moon size={13} color={color} />}
          <span className="text-sm font-bold" style={{ color }}>{formatHour(hour)}</span>
        </div>
      </div>
      <div className="relative">
        <input
          type="range"
          min={0}
          max={23}
          value={hour}
          onChange={(e) => onChange(parseInt(e.target.value))}
          className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
          style={{
            background: `linear-gradient(to right, ${color} 0%, ${color} ${(hour / 23) * 100}%, rgba(255,255,255,0.1) ${(hour / 23) * 100}%, rgba(255,255,255,0.1) 100%)`,
          }}
        />
        <style>{`
          input[type=range]::-webkit-slider-thumb {
            -webkit-appearance: none;
            width: 16px;
            height: 16px;
            border-radius: 50%;
            background: ${color};
            box-shadow: 0 0 8px ${color};
            cursor: pointer;
          }
          input[type=range]::-moz-range-thumb {
            width: 16px;
            height: 16px;
            border-radius: 50%;
            background: ${color};
            box-shadow: 0 0 8px ${color};
            cursor: pointer;
            border: none;
          }
        `}</style>
      </div>
      <div className="flex justify-between text-gray-600 text-xs">
        <span>12 AM</span>
        <span>6 AM</span>
        <span>12 PM</span>
        <span>6 PM</span>
        <span>11 PM</span>
      </div>
    </div>
  )
}

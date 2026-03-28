/**
 * HeatmapCanvas — smooth dynamic viewport-filling heatmap
 *
 * Perf strategy:
 *   - STRIDE=6: renders at 1/36 pixel count, browser bilinear upscale = smooth
 *   - Wider σ=2.8km: hotspot Gaussians spread naturally, no jagged edges
 *   - Contrast stretch: maps actual [min,max] → [0,1] so full gradient always used
 *   - Web Worker offload: danger grid computed off main thread, no UI jank
 */
import { useEffect, useRef } from 'react'
import { useMap, useMapEvents } from 'react-leaflet'

// ── Danger model constants (shared with worker via inline blob) ─────────────

const HOTSPOTS = [
  [51.4613, -0.1156, 0.96], [51.4740, -0.0551, 0.94], [51.5431, -0.0559, 0.92],
  [51.4958, -0.1002, 0.90], [51.5074, -0.0680, 0.88], [51.5588, -0.0744, 0.87],
  [51.4816, -0.0072, 0.86], [51.5308, -0.1238, 0.82], [51.5200, -0.0800, 0.80],
  [51.5233, -0.0777, 0.78], [51.5459, -0.0751, 0.77], [51.4721, -0.1222, 0.76],
  [51.5295, -0.0809, 0.75], [51.5080, -0.0879, 0.74], [51.4892,  0.0648, 0.73],
  [51.5036, -0.1138, 0.72], [51.5396,  0.0798, 0.71], [51.3762, -0.0982, 0.70],
  [51.4893, -0.1774, 0.68], [51.5362, -0.1033, 0.66], [51.5390, -0.1426, 0.65],
  [51.5416, -0.0014, 0.64], [51.5130, -0.1340, 0.63], [51.4769,  0.0012, 0.62],
  [51.5590,  0.0680, 0.61], [51.5880, -0.0197, 0.60], [51.4613, -0.0133, 0.59],
  [51.5054, -0.0235, 0.58], [51.5134, -0.0886, 0.57], [51.4958, -0.1774, 0.55],
  [51.5054, -0.1132, 0.54],
]

const SAFE_ZONES = [
  [51.5000, -0.1950, 0.10], [51.4613, -0.3037, 0.11], [51.4241, -0.2054, 0.10],
  [51.4862, -0.2408, 0.09], [51.5074, -0.2900, 0.10], [51.4527, -0.3017, 0.10],
  [51.4480, -0.3360, 0.09], [51.4755, -0.2610, 0.09], [51.5136, -0.2162, 0.09],
  [51.4161, -0.1865, 0.09], [51.4300, -0.2450, 0.08], [51.5565, -0.1783, 0.10],
  [51.6252, -0.1517, 0.09], [51.5981, -0.3077, 0.09], [51.6538, -0.1798, 0.08],
  [51.5712, -0.2731, 0.08], [51.6050, -0.0780, 0.08], [51.4400,  0.0800, 0.08],
  [51.4650,  0.1150, 0.08], [51.5150, -0.1420, 0.07], [51.5050, -0.1750, 0.07],
  [51.4950, -0.1750, 0.08], [51.4820, -0.1940, 0.07], [51.5500, -0.1000, 0.07],
]

// ── Worker source (stringified so we can make an inline blob URL) ───────────

const WORKER_SRC = `
const HOTSPOTS = ${JSON.stringify(HOTSPOTS)};
const SAFE_ZONES = ${JSON.stringify(SAFE_ZONES)};

// Wider sigma = smoother natural falloff between hotspots
const SIGMA2_H = 2 * 2.8 * 2.8;
const SIGMA2_S = 2 * 3.5 * 3.5;

function haversine(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 +
    Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLng/2)**2;
  return R * 2 * Math.asin(Math.sqrt(a));
}

function octaveNoise(lat, lng) {
  const s = Math.sin, c = Math.cos;
  // Three octaves: neighbourhood ~2km, block ~400m, street ~100m
  return (
    s(lat*312.7)  * c(lng*198.3)  * 0.10 +
    s(lat*1573.1) * c(lng*991.7)  * 0.07 +
    s(lat*6271.3) * c(lng*3947.9) * 0.04 +
    s(lat*445.1  + lng*312.9)     * 0.03 +
    s(lat*1821.7 - lng*1134.3)    * 0.02
  );
}

function getDanger(lat, lng) {
  let danger = 0;
  for (const [hlat, hlng, intensity] of HOTSPOTS) {
    const d = haversine(lat, lng, hlat, hlng);
    danger += intensity * Math.exp(-(d*d) / SIGMA2_H);
  }
  let safePull = 0;
  for (const [slat, slng, intensity] of SAFE_ZONES) {
    const d = haversine(lat, lng, slat, slng);
    safePull += intensity * Math.exp(-(d*d) / SIGMA2_S);
  }
  const raw = 0.12 + danger * 0.72 - safePull * 0.75 + octaveNoise(lat, lng);
  return Math.max(0.02, Math.min(0.98, raw));
}

self.onmessage = function({ data: { points, id } }) {
  // points: Float32Array of [lat, lng, lat, lng, ...]
  const n = points.length / 2;
  const result = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    result[i] = getDanger(points[i*2], points[i*2+1]);
  }
  // No contrast stretch — values are absolute danger scores so colours
  // stay consistent across zoom levels and match the click-based score.
  self.postMessage({ result, id }, [result.buffer]);
};
`

// ── LUT builder ───────────────────────────────────────────────────────────

const CMAPS = {
  // Night: soft teal for safe areas, then blue→purple→crimson→amber for danger
  night: [
    [0.00,  10,  40,  80, 100],   // safe — soft dark teal
    [0.10,  12,  50, 100, 130],   // safe — slightly brighter teal
    [0.18,  15,  60, 130, 155],   // safe-ish — deeper teal-blue
    [0.28,  29,  78, 216, 175],   // blue  — low risk
    [0.40,  59, 130, 246, 195],   // sky blue — medium-low
    [0.52, 139,  92, 246, 210],   // violet
    [0.62, 192,  38, 211, 220],   // purple-pink
    [0.70, 220,  38,  38, 230],   // crimson — high risk
    [0.80, 249, 115,  22, 242],   // orange
    [0.90, 251, 191,  36, 250],   // amber
    [1.00, 255, 255, 180, 255],   // white-hot peak
  ],
  // Day: soft sage green for safe areas, then yellow→orange→deep red for danger
  day: [
    [0.00,  30, 100,  60, 100],   // safe — soft sage green
    [0.10,  25, 120,  65, 130],   // safe — medium sage
    [0.18,  22, 145,  75, 155],   // safe-ish — richer green
    [0.28,  34, 197,  94, 175],   // green — low risk
    [0.40, 101, 213,  60, 195],   // yellow-green
    [0.52, 234, 210,   8, 210],   // yellow
    [0.62, 249, 160,  22, 220],   // amber-orange
    [0.70, 249, 115,  22, 230],   // orange — high risk
    [0.80, 239,  68,  68, 242],   // red
    [0.90, 185,  28,  28, 250],   // deep red
    [1.00, 100,   0,   0, 255],   // near-black crimson peak
  ],
}

function buildLUT(palette) {
  const cmap = CMAPS[palette] || CMAPS.night
  const lut = new Uint8Array(256 * 4)
  for (let i = 0; i < 256; i++) {
    const v = i / 255
    let r = 0, g = 0, b = 0, a = 0
    for (let j = 0; j < cmap.length - 1; j++) {
      const [v0, r0, g0, b0, a0] = cmap[j]
      const [v1, r1, g1, b1, a1] = cmap[j + 1]
      if (v >= v0 && v <= v1) {
        let t = (v - v0) / (v1 - v0)
        t = t * t * (3 - 2 * t) // smoothstep easing
        r = r0 + t * (r1 - r0)
        g = g0 + t * (g1 - g0)
        b = b0 + t * (b1 - b0)
        a = a0 + t * (a1 - a0)
        break
      }
    }
    lut[i*4] = r; lut[i*4+1] = g; lut[i*4+2] = b; lut[i*4+3] = a
  }
  return lut
}

const LUTS = { night: buildLUT('night'), day: buildLUT('day') }

// ── Rendering ─────────────────────────────────────────────────────────────

const STRIDE = 6  // sample every 6px — fast + smooth after bilinear upscale

function applyGrid(canvas, W, H, values, palette, viewW, viewH) {
  const lut = LUTS[palette] || LUTS.night
  const imgData = new ImageData(W, H)
  const pixels = imgData.data

  for (let i = 0; i < values.length; i++) {
    const idx = Math.min(255, Math.round(values[i] * 255)) * 4
    const p = i * 4
    pixels[p]   = lut[idx];   pixels[p+1] = lut[idx+1]
    pixels[p+2] = lut[idx+2]; pixels[p+3] = lut[idx+3]
  }

  const off = document.createElement('canvas')
  off.width = W; off.height = H
  off.getContext('2d').putImageData(imgData, 0, 0)

  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, viewW, viewH)
  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = 'high'
  ctx.globalAlpha = palette === 'day' ? 0.65 : 0.75
  ctx.drawImage(off, 0, 0, viewW, viewH)
}

// ── React component ───────────────────────────────────────────────────────

let workerInstance = null
function getWorker() {
  if (!workerInstance) {
    const blob = new Blob([WORKER_SRC], { type: 'application/javascript' })
    workerInstance = new Worker(URL.createObjectURL(blob))
  }
  return workerInstance
}

let renderSeq = 0  // sequence number — drops stale results

export default function HeatmapCanvas({ show, nightMode }) {
  const mapInst   = useMap()
  const canvasRef = useRef(null)
  const palette   = nightMode ? 'night' : 'day'
  const pendingRef = useRef(null)

  // Mount canvas once into Leaflet overlay pane
  useEffect(() => {
    const canvas = document.createElement('canvas')
    canvas.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none;z-index:200;'
    mapInst.getPanes().overlayPane.appendChild(canvas)
    canvasRef.current = canvas
    return () => { canvas.remove(); canvasRef.current = null }
  }, [mapInst])

  const scheduleRender = () => {
    if (pendingRef.current) cancelAnimationFrame(pendingRef.current)
    pendingRef.current = requestAnimationFrame(() => {
      const canvas = canvasRef.current
      if (!canvas) return

      const size = mapInst.getSize()
      canvas.width  = size.x
      canvas.height = size.y
      canvas.style.width  = size.x + 'px'
      canvas.style.height = size.y + 'px'

      if (!show) {
        canvas.getContext('2d').clearRect(0, 0, size.x, size.y)
        return
      }

      const W = Math.ceil(size.x / STRIDE)
      const H = Math.ceil(size.y / STRIDE)

      // Build flat lat/lng array for worker
      const points = new Float32Array(W * H * 2)
      let idx = 0
      for (let row = 0; row < H; row++) {
        for (let col = 0; col < W; col++) {
          const ll = mapInst.containerPointToLatLng([col * STRIDE, row * STRIDE])
          points[idx++] = ll.lat
          points[idx++] = ll.lng
        }
      }

      const seq = ++renderSeq
      const worker = getWorker()

      worker.onmessage = ({ data: { result, id } }) => {
        if (id !== seq) return  // stale — discard
        applyGrid(canvas, W, H, result, palette, size.x, size.y)
      }
      worker.postMessage({ points, id: seq }, [points.buffer])
    })
  }

  useEffect(() => { scheduleRender() }, [show, palette])

  useMapEvents({
    moveend: scheduleRender,
    zoomend: scheduleRender,
    resize:  scheduleRender,
  })

  return null
}

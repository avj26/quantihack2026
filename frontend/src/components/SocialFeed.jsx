import React from 'react'
import { TrendingDown, TrendingUp, Minus, Radio, Navigation2 } from 'lucide-react'
import ComposeForm from './ComposeForm'

const PLATFORM_COLORS = {
  twitter: '#1d9bf0',
  reddit: '#ff4500',
  nextdoor: '#8bc34a',
  streetsense: '#60a5fa',
}

const PLATFORM_LABELS = {
  twitter: 'X',
  reddit: 'Reddit',
  nextdoor: 'Nextdoor',
  streetsense: 'StreetSense',
}

const SENTIMENT = {
  positive: {
    color: '#10b981',
    bg: 'rgba(16,185,129,0.08)',
    border: 'rgba(16,185,129,0.18)',
    label: 'Safe',
    Icon: TrendingUp,
  },
  neutral: {
    color: '#6b7280',
    bg: 'rgba(107,114,128,0.07)',
    border: 'rgba(107,114,128,0.15)',
    label: 'Neutral',
    Icon: Minus,
  },
  negative: {
    color: '#ef4444',
    bg: 'rgba(239,68,68,0.08)',
    border: 'rgba(239,68,68,0.18)',
    label: 'Alert',
    Icon: TrendingDown,
  },
}

const TAG_COLORS = {
  'incident reported': { bg: 'rgba(239,68,68,0.15)', color: '#fca5a5' },
  'police activity': { bg: 'rgba(96,165,250,0.15)', color: '#93c5fd' },
  'poor lighting': { bg: 'rgba(107,114,128,0.15)', color: '#9ca3af' },
  'good lighting': { bg: 'rgba(251,191,36,0.15)', color: '#fcd34d' },
  'active area': { bg: 'rgba(16,185,129,0.15)', color: '#6ee7b7' },
  'quiet area': { bg: 'rgba(107,114,128,0.15)', color: '#9ca3af' },
  'avoid advised': { bg: 'rgba(239,68,68,0.15)', color: '#fca5a5' },
  'feels safe': { bg: 'rgba(16,185,129,0.15)', color: '#6ee7b7' },
  'threatening behaviour': { bg: 'rgba(249,115,22,0.15)', color: '#fdba74' },
}

function formatTime(mins) {
  if (mins < 60) return `${mins}m ago`
  const h = Math.floor(mins / 60)
  return `${h}h ${mins % 60}m ago`
}

function PostCard({ post, index }) {
  const s = SENTIMENT[post.sentiment]
  const { Icon } = s
  const platformColor = PLATFORM_COLORS[post.platform] || '#6b7280'
  const platformLabel = PLATFORM_LABELS[post.platform] || post.platform
  const isUserPost = post.is_user_post && post.platform === 'streetsense'

  return (
    <div
      className="p-3 rounded-xl border fade-up"
      style={{
        background: isUserPost ? 'rgba(59,130,246,0.07)' : s.bg,
        borderColor: isUserPost ? 'rgba(59,130,246,0.25)' : s.border,
        animationDelay: `${index * 60}ms`,
        animationFillMode: 'both',
      }}
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          {/* Avatar */}
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0"
            style={{ background: `${s.color}30`, border: `1px solid ${s.color}40` }}
          >
            {post.username[0].toUpperCase()}
          </div>
          <div className="flex flex-col leading-none gap-0.5">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-white">@{post.username}</span>
              {isUserPost && (
                <span className="text-xs px-1.5 py-0.5 rounded-full font-semibold" style={{ background: 'rgba(59,130,246,0.2)', color: '#93c5fd' }}>
                  you
                </span>
              )}
            </div>
            <div className="flex items-center gap-1">
              {isUserPost
                ? <Navigation2 size={9} color={platformColor} />
                : null
              }
              <span className="text-xs font-medium" style={{ color: platformColor }}>
                {platformLabel}
              </span>
              <span className="text-gray-600 text-xs">·</span>
              <span className="text-gray-500 text-xs">{formatTime(post.minutes_ago)}</span>
            </div>
          </div>
        </div>

        {/* Sentiment badge */}
        <div
          className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold flex-shrink-0"
          style={{ background: `${s.color}20`, color: s.color }}
        >
          <Icon size={10} />
          <span>{s.label}</span>
        </div>
      </div>

      {/* Content */}
      <p className="text-xs text-gray-300 leading-relaxed">{post.content}</p>

      {/* Semantic tags */}
      {post.tags.length > 0 && (
        <div className="flex gap-1.5 mt-2 flex-wrap">
          {post.tags.map((tag, i) => {
            const tc = TAG_COLORS[tag] || { bg: 'rgba(255,255,255,0.08)', color: '#9ca3af' }
            return (
              <span
                key={i}
                className="text-xs px-2 py-0.5 rounded-full font-medium"
                style={{ background: tc.bg, color: tc.color }}
              >
                {tag}
              </span>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function SocialFeed({ posts, totalImpact, loading, selectedPos, onPosted }) {
  const impactColor = !totalImpact || Math.abs(totalImpact) <= 3
    ? '#6b7280'
    : totalImpact > 3 ? '#10b981' : '#ef4444'
  const ImpactIcon = totalImpact > 3 ? TrendingUp : totalImpact < -3 ? TrendingDown : Minus
  const impactPositive = totalImpact >= 0

  return (
    <div className="flex flex-col gap-3">
      {/* AI impact banner */}
      {posts && posts.length > 0 && (
        <div className="flex items-start gap-2 px-2.5 py-2 rounded-lg bg-blue-950/25 border border-blue-900/25">
          <span className="text-blue-400 text-xs font-bold mt-0.5 flex-shrink-0">AI</span>
          <p className="text-xs text-gray-400 leading-relaxed">
            Semantic analysis of {posts.length} posts detected{' '}
            <span style={{ color: impactColor }} className="font-semibold">
              {totalImpact > 3 ? 'predominantly positive signals' : totalImpact < -3 ? 'safety concerns' : 'mixed signals'}
            </span>
            {'. '}Score adjusted{' '}
            <span className="text-white font-semibold">
              {impactPositive ? '+' : ''}{totalImpact} pts
            </span>.
          </p>
        </div>
      )}

      {/* Posts list */}
      {loading ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 py-1">
            <div className="w-3.5 h-3.5 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin flex-shrink-0" />
            <span className="text-xs text-gray-500">Scanning social signals...</span>
          </div>
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-16 rounded-xl bg-white/5 animate-pulse" style={{ animationDelay: `${i * 80}ms` }} />
          ))}
        </div>
      ) : posts && posts.length > 0 ? (
        <div className="flex flex-col gap-2">
          {posts.map((post, i) => (
            <PostCard key={post.id} post={post} index={i} />
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-600 text-center py-4">No posts nearby yet — be the first!</p>
      )}

      {/* Divider + compose */}
      <div className="border-t border-white/5 pt-3">
        <p className="text-xs text-gray-500 font-semibold uppercase tracking-widest mb-2">Report what you see</p>
        {selectedPos
          ? <ComposeForm lat={selectedPos[0]} lng={selectedPos[1]} onPosted={onPosted} />
          : <p className="text-xs text-gray-600">Select a location to post.</p>
        }
      </div>
    </div>
  )
}

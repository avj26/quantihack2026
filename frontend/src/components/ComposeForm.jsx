import React, { useState } from 'react'
import { Send, CheckCircle, Loader2 } from 'lucide-react'
import axios from 'axios'

export default function ComposeForm({ lat, lng, onPosted }) {
  const [username, setUsername] = useState('')
  const [content, setContent] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [posted, setPosted] = useState(false)
  const [error, setError] = useState('')

  const canSubmit = username.trim().length > 0 && content.trim().length > 5 && !submitting

  const handleSubmit = async () => {
    if (!canSubmit) return
    setSubmitting(true)
    setError('')
    try {
      await axios.post('/api/posts', { lat, lng, username: username.trim(), content: content.trim() })
      setContent('')
      setPosted(true)
      setTimeout(() => setPosted(false), 3000)
      onPosted()
    } catch {
      setError('Failed to post. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit()
  }

  return (
    <div
      className="rounded-xl p-3 flex flex-col gap-2.5"
      style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}
    >
      <div className="flex items-center gap-2">
        {/* Avatar placeholder */}
        <div className="w-7 h-7 rounded-full bg-blue-500/20 border border-blue-500/30 flex items-center justify-center flex-shrink-0">
          <span className="text-blue-400 text-xs font-bold">
            {username ? username[0].toUpperCase() : '?'}
          </span>
        </div>
        <input
          type="text"
          value={username}
          onChange={e => setUsername(e.target.value)}
          placeholder="Your name or handle..."
          maxLength={40}
          className="flex-1 bg-transparent text-sm text-white placeholder-gray-600 outline-none font-medium"
        />
      </div>

      <textarea
        value={content}
        onChange={e => setContent(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="What's happening here right now?"
        maxLength={280}
        rows={3}
        className="w-full bg-transparent text-sm text-gray-300 placeholder-gray-600 outline-none resize-none leading-relaxed"
      />

      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-600">
          {content.length > 0 && `${content.length}/280`}
          {content.length === 0 && <span className="text-gray-700">⌘ Enter to post</span>}
        </span>

        <div className="flex items-center gap-2">
          {posted && (
            <div className="flex items-center gap-1 text-emerald-400 text-xs font-semibold fade-up">
              <CheckCircle size={12} />
              <span>Posted!</span>
            </div>
          )}
          {error && <span className="text-red-400 text-xs">{error}</span>}
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all"
            style={{
              background: canSubmit ? 'rgba(59,130,246,0.2)' : 'rgba(255,255,255,0.05)',
              color: canSubmit ? '#60a5fa' : '#4b5563',
              border: `1px solid ${canSubmit ? 'rgba(59,130,246,0.3)' : 'rgba(255,255,255,0.05)'}`,
              cursor: canSubmit ? 'pointer' : 'not-allowed',
            }}
          >
            {submitting
              ? <Loader2 size={12} className="animate-spin" />
              : <Send size={12} />
            }
            <span>{submitting ? 'Posting...' : 'Post'}</span>
          </button>
        </div>
      </div>
    </div>
  )
}

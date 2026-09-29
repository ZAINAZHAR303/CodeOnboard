import { useEffect, useRef, useState } from 'react'
import { chatWithRepo } from '../api/client.js'
import FileLink from '../components/FileLink.jsx'
import { Icon } from '../components/Icons.jsx'
import Markdown from '../components/Markdown.jsx'
import { useRepo } from '../components/RepoContext.jsx'

export default function ChatPanel({ messages, setMessages, draft, setDraft, suggestions }) {
  const { repoId, analysis } = useRepo()
  const [loading, setLoading] = useState(false)
  const endRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, loading])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const send = async (text) => {
    const question = (text ?? draft).trim()
    if (!question || loading) return
    const history = messages.map(({ role, content }) => ({ role, content }))
    setMessages((m) => [...m, { role: 'user', content: question }])
    setDraft('')
    setLoading(true)
    try {
      const res = await chatWithRepo(repoId, question, history)
      setMessages((m) => [...m, { role: 'assistant', content: res.answer, files: res.relevant_files }])
    } catch (err) {
      setMessages((m) => [...m, { role: 'assistant', content: `Sorry, that failed: ${err.message}`, error: true }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="section chat">
      <header className="section-head">
        <div>
          <h2>Ask the codebase</h2>
          <p className="muted">Answers are grounded in {analysis.repo_name}'s source: relevant files are retrieved first and cited.</p>
        </div>
        {messages.length > 0 && (
          <button type="button" className="btn btn-small" onClick={() => setMessages([])}>Clear chat</button>
        )}
      </header>

      <div className="card chat-card">
        <div className="chat-log" aria-live="polite">
          {messages.length === 0 && (
            <div className="chat-empty">
              <Icon name="chat" size={28} />
              <p>Ask anything about how this codebase works. Try one of these:</p>
              <div className="suggestions">
                {suggestions.map((q) => (
                  <button key={q} type="button" className="chip" onClick={() => send(q)}>{q}</button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`msg msg-${m.role} ${m.error ? 'msg-error' : ''}`}>
              {m.role === 'assistant' ? <Markdown>{m.content}</Markdown> : <p>{m.content}</p>}
              {m.files?.length > 0 && (
                <div className="msg-files">
                  <span className="muted small">Sources:</span>
                  {m.files.map((f) => <FileLink key={f} path={f} />)}
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="msg msg-assistant typing" aria-label="Thinking">
              <span /><span /><span />
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form
          className="chat-input"
          onSubmit={(e) => {
            e.preventDefault()
            send()
          }}
        >
          <textarea
            ref={inputRef}
            rows={2}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
            placeholder="Ask a question... (Enter to send, Shift+Enter for a new line)"
            aria-label="Question"
            disabled={loading}
          />
          <button type="submit" className="btn btn-primary" disabled={loading || !draft.trim()} aria-label="Send">
            <Icon name="send" />
          </button>
        </form>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { mapTicket } from '../api/client.js'
import FileLink from '../components/FileLink.jsx'
import { Icon } from '../components/Icons.jsx'
import { useRepo } from '../components/RepoContext.jsx'

const MAX = 6000

function scoreTone(score) {
  if (score >= 0.8) return 'high'
  if (score >= 0.5) return 'mid'
  return 'low'
}

const AUX_PATH = /(^|\/)(examples?|tests?|__tests__|docs?|spec|benchmarks?)\//

function sampleTicket(analysis) {
  const endpoint = analysis.api_endpoints
    .filter((e) => !AUX_PATH.test(e.file_path) && e.route.length > 1)
    .sort((a, b) => b.route.length - a.route.length)[0]
  if (endpoint) {
    return `Add rate limiting to the ${endpoint.method} ${endpoint.route} endpoint.\n\nRequests should be limited to 60 per minute per client. When the limit is exceeded, respond with HTTP 429 and a Retry-After header. The limit must be configurable, and the behaviour must be covered by tests.`
  }
  return 'Add structured logging across the project.\n\nReplace ad-hoc print/console statements with a configurable logger, include a request/operation id in each log line, and make the log level configurable via an environment variable. Update the tests and docs accordingly.'
}

export default function TicketMapper({ state, setState }) {
  const { repoId, analysis } = useRepo()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const { text, result } = state

  const submit = async () => {
    if (text.trim().length < 5) {
      setError('Describe the ticket in a sentence or two first.')
      return
    }
    setLoading(true)
    setError('')
    setState((s) => ({ ...s, result: null }))
    try {
      const res = await mapTicket(repoId, text.trim())
      setState((s) => ({ ...s, result: res }))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="section">
      <header className="section-head">
        <div>
          <h2>Ticket mapper</h2>
          <p className="muted">Paste a Jira or GitHub issue. Get the files to touch, tests to update, APIs affected and a step-by-step plan.</p>
        </div>
      </header>

      <div className="card ticket-input">
        <textarea
          rows={7}
          maxLength={MAX}
          value={text}
          onChange={(e) => setState((s) => ({ ...s, text: e.target.value }))}
          placeholder={'Paste your ticket here...\n\nExample: "Add a password reset flow that emails the user a link that expires after 24 hours."'}
          aria-label="Ticket description"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit()
          }}
        />
        <div className="ticket-actions">
          <button type="button" className="link-btn" onClick={() => setState((s) => ({ ...s, text: sampleTicket(analysis) }))}>
            Use a sample ticket for this repo
          </button>
          <span className="muted small">{text.length}/{MAX}</span>
          <button type="button" className="btn btn-primary" onClick={submit} disabled={loading}>
            {loading ? 'Mapping...' : 'Map to files'}
          </button>
        </div>
        {error && <div className="form-error" role="alert">{error}</div>}
      </div>

      {loading && (
        <div className="card thinking">
          <div className="spinner small" /> Searching the codebase and planning the change...
        </div>
      )}

      {result && (
        <div className="ticket-result">
          {result.summary && (
            <div className="card summary-card">
              <p>{result.summary}</p>
              {result.estimated_effort && <span className="effort"><Icon name="clock" size={14} /> {result.estimated_effort}</span>}
            </div>
          )}

          <div className="card">
            <h3 className="card-title">Files to touch</h3>
            {result.relevant_files.length === 0 && <p className="muted">No matching files found. Try adding more detail to the ticket.</p>}
            <ul className="mapped-list">
              {result.relevant_files.map((f) => (
                <li key={f.path} className="mapped-item">
                  <div className="mapped-head">
                    <span className={`dot tone-${scoreTone(f.relevance_score)}`} />
                    {f.exists ? <FileLink path={f.path} /> : <code className="file-chip is-static">{f.path}</code>}
                    <span className={`change change-${f.change_type}`}>{f.exists ? f.change_type : 'new file'}</span>
                    <span className="score">{Math.round(f.relevance_score * 100)}%</span>
                  </div>
                  <div className="score-bar"><span className={`tone-${scoreTone(f.relevance_score)}`} style={{ width: `${f.relevance_score * 100}%` }} /></div>
                  <p>{f.reason}</p>
                </li>
              ))}
            </ul>
          </div>

          {result.implementation_steps.length > 0 && (
            <div className="card">
              <h3 className="card-title">Implementation plan</h3>
              <ol className="steps">
                {result.implementation_steps.map((step, i) => (
                  <li key={i}><span className="step-num">{i + 1}</span><span>{step.replace(/^step\s*\d+[:.]\s*/i, '')}</span></li>
                ))}
              </ol>
            </div>
          )}

          <div className="ticket-cols">
            <div className="card">
              <h3 className="card-title">Tests</h3>
              {result.suggested_tests.length ? (
                <ul className="plain-list">{result.suggested_tests.map((t) => <li key={t}><FileLink path={t} /></li>)}</ul>
              ) : <p className="muted">No test suggestions.</p>}
            </div>
            <div className="card">
              <h3 className="card-title">APIs affected</h3>
              {result.related_apis.length ? (
                <ul className="plain-list">
                  {result.related_apis.map((a) => {
                    const [method, ...rest] = a.split(' ')
                    return <li key={a}><span className={`method method-${method.toLowerCase()}`}>{method}</span> <span className="mono">{rest.join(' ')}</span></li>
                  })}
                </ul>
              ) : <p className="muted">No API changes expected.</p>}
            </div>
            {result.risks.length > 0 && (
              <div className="card">
                <h3 className="card-title">Watch out for</h3>
                <ul className="bullets">{result.risks.map((r) => <li key={r}>{r}</li>)}</ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

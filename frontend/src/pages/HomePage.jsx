import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { analyzeRepo, getHealth, getJob, listAnalyses } from '../api/client.js'
import AnalyzeProgress from '../components/AnalyzeProgress.jsx'
import { Icon } from '../components/Icons.jsx'

const SAMPLES = [
  { label: 'pallets/flask', url: 'https://github.com/pallets/flask' },
  { label: 'expressjs/express', url: 'https://github.com/expressjs/express' },
  { label: 'fastapi/full-stack-fastapi-template', url: 'https://github.com/fastapi/full-stack-fastapi-template' },
]

const FEATURES = [
  { icon: 'overview', title: 'Architecture in minutes', text: 'An AI-written architecture overview, data-flow walkthrough and reading plan grounded in the real files.' },
  { icon: 'graph', title: 'Live dependency map', text: 'Static analysis of every import builds an interactive graph and surfaces the files everything depends on.' },
  { icon: 'ticket', title: 'Ticket to files', text: 'Paste an issue and get the exact files to change, tests to update, APIs affected and an implementation plan.' },
  { icon: 'chat', title: 'Ask the codebase', text: 'A Q&A agent that retrieves the relevant source files before answering, and cites them.' },
]

const GITHUB_RE = /^https?:\/\/(www\.)?github\.com\/[\w.-]+\/[\w.-]+/

export default function HomePage() {
  const navigate = useNavigate()
  const [url, setUrl] = useState('')
  const [branch, setBranch] = useState('')
  const [force, setForce] = useState(false)
  const [error, setError] = useState('')
  const [job, setJob] = useState(null)
  const [recent, setRecent] = useState([])
  const [health, setHealth] = useState(null)
  const pollRef = useRef(null)

  useEffect(() => {
    listAnalyses().then(setRecent).catch(() => {})
    getHealth().then(setHealth).catch(() => setHealth({ status: 'down' }))
    return () => clearTimeout(pollRef.current)
  }, [])

  const poll = (jobId) => {
    getJob(jobId)
      .then((status) => {
        setJob(status)
        if (status.status === 'completed') {
          navigate(`/repo/${status.repo_id}`)
        } else if (status.status === 'failed') {
          setError(status.error || 'Analysis failed')
          setJob(null)
        } else {
          pollRef.current = setTimeout(() => poll(jobId), 1200)
        }
      })
      .catch((err) => {
        setError(err.message)
        setJob(null)
      })
  }

  const submit = async (e) => {
    e?.preventDefault()
    setError('')
    const trimmed = url.trim()
    if (!GITHUB_RE.test(trimmed)) {
      setError('Enter a public GitHub repository URL, e.g. https://github.com/owner/repo')
      return
    }
    try {
      setJob({ status: 'queued', progress: 0, message: 'Starting analysis', log: [] })
      const res = await analyzeRepo(trimmed, branch.trim(), force)
      if (res.cached) {
        navigate(`/repo/${res.repo_id}`)
        return
      }
      poll(res.job_id)
    } catch (err) {
      setError(err.message)
      setJob(null)
    }
  }

  return (
    <main className="home">
      {job && <AnalyzeProgress job={job} repoUrl={url} />}

      <section className="hero">
        <p className="eyebrow">Developer onboarding, automated</p>
        <h1>Understand any codebase in minutes, not weeks.</h1>
        <p className="lede">
          Paste a GitHub repository. CodeOnboard maps its structure, dependencies and APIs, then a team of AI agents
          writes the onboarding guide a senior engineer would give you on day one.
        </p>

        {health && health.status !== 'ok' && (
          <div className="banner banner-error"><Icon name="warning" /> The API is not reachable. Start the backend on port 8000.</div>
        )}
        {health?.status === 'ok' && !health.llm_configured && (
          <div className="banner banner-warn"><Icon name="warning" /> No Gemini API key configured: AI sections will fall back to static analysis.</div>
        )}

        <form className="repo-form" onSubmit={submit}>
          <div className="repo-form-row">
            <label className="field grow">
              <span className="field-label">Repository URL</span>
              <input
                type="url"
                inputMode="url"
                placeholder="https://github.com/owner/repo"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                autoFocus
              />
            </label>
            <label className="field branch">
              <span className="field-label">Branch <em>(optional)</em></span>
              <input placeholder="default" value={branch} onChange={(e) => setBranch(e.target.value)} />
            </label>
            <button className="btn btn-primary btn-lg" type="submit" disabled={Boolean(job)}>
              Analyze repository
            </button>
          </div>
          <div className="repo-form-foot">
            <div className="samples">
              <span>Try:</span>
              {SAMPLES.map((s) => (
                <button key={s.url} type="button" className="chip" onClick={() => setUrl(s.url)}>
                  {s.label}
                </button>
              ))}
            </div>
            <label className="checkbox">
              <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
              Re-run even if analysed before
            </label>
          </div>
          {error && <div className="form-error" role="alert">{error}</div>}
        </form>
      </section>

      <section className="feature-grid">
        {FEATURES.map((f) => (
          <article key={f.title} className="feature-card">
            <span className="feature-icon"><Icon name={f.icon} size={20} /></span>
            <h3>{f.title}</h3>
            <p>{f.text}</p>
          </article>
        ))}
      </section>

      {recent.length > 0 && (
        <section className="recent">
          <h2>Recent onboarding packages</h2>
          <div className="recent-list">
            {recent.map((r) => (
              <Link key={r.repo_id} to={`/repo/${r.repo_id}`} className="recent-item">
                <span className="recent-name"><Icon name="github" /> {r.repo_name}{r.branch ? ` @ ${r.branch}` : ''}</span>
                <span className="recent-meta">
                  {r.tech_stack.slice(0, 4).join(' · ')} · {r.total_files} files · {new Date(r.created_at).toLocaleDateString()}
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      <footer className="app-footer">Built with IBM Bob 2.0 · CodeOnboard, the codebase onboarding accelerator</footer>
    </main>
  )
}

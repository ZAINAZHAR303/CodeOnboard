import { useEffect, useState } from 'react'
import { Icon } from '../components/Icons.jsx'
import { useRepo } from '../components/RepoContext.jsx'

function loadDone(key) {
  try {
    return JSON.parse(localStorage.getItem(key) || '[]')
  } catch {
    return []
  }
}

export default function LearningPath({ steps }) {
  const { repoId, openFile } = useRepo()
  const storageKey = `codeonboard:path:${repoId}`
  const [done, setDone] = useState(() => loadDone(storageKey))

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(done))
    } catch {
      /* storage unavailable: progress is kept for this session only */
    }
  }, [done, storageKey])

  const toggle = (path) => setDone((d) => (d.includes(path) ? d.filter((p) => p !== path) : [...d, path]))
  const totalMinutes = steps.reduce((sum, s) => sum + s.minutes, 0)
  const doneCount = steps.filter((s) => done.includes(s.path)).length
  const pct = steps.length ? Math.round((doneCount / steps.length) * 100) : 0

  return (
    <div className="section">
      <header className="section-head">
        <div>
          <h2>Day-1 reading plan</h2>
          <p className="muted">Read these files in order: big picture first, then the core, then the tests. About {totalMinutes} minutes in total.</p>
        </div>
        <div className="path-progress">
          <span>{doneCount}/{steps.length} read</span>
          <div className="progress-bar small"><div className="progress-fill" style={{ width: `${pct}%` }} /></div>
        </div>
      </header>

      {steps.length === 0 && <p className="muted">No reading plan was generated for this repository.</p>}

      <ol className="timeline">
        {steps.map((step) => {
          const isDone = done.includes(step.path)
          return (
            <li key={step.path} className={`timeline-item ${isDone ? 'is-done' : ''}`}>
              <button type="button" className="timeline-dot" onClick={() => toggle(step.path)} aria-label={isDone ? 'Mark as unread' : 'Mark as read'}>
                {isDone ? <Icon name="check" size={14} /> : step.order}
              </button>
              <div className="card timeline-card">
                <div className="timeline-head">
                  <h3>{step.title}</h3>
                  <span className="muted small"><Icon name="clock" size={13} /> {step.minutes} min</span>
                </div>
                <button type="button" className="file-chip" onClick={() => openFile(step.path)}>{step.path}</button>
                <p>{step.why}</p>
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

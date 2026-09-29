import { useEffect, useState } from 'react'
import { Icon } from './Icons.jsx'

const STAGES = [
  { key: 'cloning', label: 'Clone repository' },
  { key: 'scanning', label: 'Scan source files' },
  { key: 'analyzing', label: 'Static analysis: imports, modules, APIs' },
  { key: 'generating', label: '5 AI agents write the guide in parallel' },
  { key: 'saving', label: 'Package onboarding kit' },
]

export default function AnalyzeProgress({ job, repoUrl }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const started = Date.now()
    const id = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000)
    return () => clearInterval(id)
  }, [])

  const activeIndex = Math.max(0, STAGES.findIndex((s) => s.key === job.stage))
  const repoName = repoUrl.replace(/^https?:\/\/(www\.)?github\.com\//, '').replace(/\/$/, '')

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Analysis in progress">
      <div className="progress-card">
        <div className="progress-head">
          <div>
            <p className="eyebrow">Building onboarding package</p>
            <h2>{repoName || 'Repository'}</h2>
          </div>
          <span className="elapsed"><Icon name="clock" /> {elapsed}s</span>
        </div>

        <div className="progress-bar" aria-hidden="true">
          <div className="progress-fill" style={{ width: `${job.progress || 2}%` }} />
        </div>
        <p className="progress-message">{job.message}</p>

        <ol className="stage-list">
          {STAGES.map((stage, i) => {
            const state = job.stage === 'done' || i < activeIndex ? 'done' : i === activeIndex ? 'active' : 'pending'
            return (
              <li key={stage.key} className={`stage stage-${state}`}>
                <span className="stage-dot">{state === 'done' ? <Icon name="check" size={12} /> : i + 1}</span>
                {stage.label}
              </li>
            )
          })}
        </ol>

        {job.log?.length > 0 && (
          <div className="progress-log">
            {job.log.slice(-6).map((line, i) => (
              <div key={`${i}-${line}`}>› {line}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

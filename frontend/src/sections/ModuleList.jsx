import { useState } from 'react'
import FileLink from '../components/FileLink.jsx'
import { Icon } from '../components/Icons.jsx'

function ModuleCard({ module }) {
  const [open, setOpen] = useState(false)
  return (
    <article className="card module-card">
      <header className="module-head">
        <h3><Icon name="folder" /> {module.path === '.' ? '(repository root)' : module.path}</h3>
        <span className="count-pill">{module.files.length} files</span>
      </header>
      <p>{module.description}</p>
      {module.key_files.length > 0 && (
        <div className="module-key">
          <span className="muted small">Open first:</span>
          {module.key_files.map((p) => <FileLink key={p} path={p} label={p.split('/').pop()} />)}
        </div>
      )}
      <button type="button" className="link-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <Icon name="chevron" size={14} className={open ? 'rot-90' : ''} /> {open ? 'Hide' : 'Show'} all files
      </button>
      {open && (
        <ul className="module-files">
          {module.files.map((p) => <li key={p}><FileLink path={p} /></li>)}
        </ul>
      )}
    </article>
  )
}

export default function ModuleList({ modules }) {
  return (
    <div className="section">
      <header className="section-head">
        <div>
          <h2>Modules</h2>
          <p className="muted">{modules.length} modules, grouped by folder and described by the module agent.</p>
        </div>
      </header>
      {modules.length === 0 ? (
        <p className="muted">No modules detected.</p>
      ) : (
        <div className="module-grid">
          {modules.map((m) => <ModuleCard key={m.path} module={m} />)}
        </div>
      )}
    </div>
  )
}

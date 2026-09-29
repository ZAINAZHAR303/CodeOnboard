import { useMemo, useState } from 'react'
import FileLink from '../components/FileLink.jsx'

export default function ApiEndpoints({ endpoints }) {
  const [query, setQuery] = useState('')
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return endpoints
    return endpoints.filter((e) => `${e.method} ${e.route} ${e.file_path}`.toLowerCase().includes(q))
  }, [endpoints, query])

  return (
    <div className="section">
      <header className="section-head">
        <div>
          <h2>API endpoints</h2>
          <p className="muted">Routes detected statically across FastAPI, Flask, Django, Express, NestJS, Next.js and Spring.</p>
        </div>
        <input className="search-input" placeholder="Filter routes..." value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Filter routes" />
      </header>

      {endpoints.length === 0 ? (
        <div className="card empty">No HTTP routes were detected. This may be a library, CLI or frontend-only project.</div>
      ) : (
        <div className="card table-card">
          <table className="table">
            <thead>
              <tr><th>Method</th><th>Route</th><th>Defined in</th><th>Framework</th></tr>
            </thead>
            <tbody>
              {filtered.map((e) => (
                <tr key={`${e.file_path}-${e.line}-${e.method}-${e.route}`}>
                  <td><span className={`method method-${e.method.toLowerCase()}`}>{e.method}</span></td>
                  <td className="mono">{e.route}</td>
                  <td><FileLink path={e.file_path} label={`${e.file_path}:${e.line}`} line={e.line} /></td>
                  <td className="muted">{e.framework}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && <p className="muted empty">No routes match "{query}".</p>}
        </div>
      )}
    </div>
  )
}

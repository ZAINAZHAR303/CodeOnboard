import FileLink from '../components/FileLink.jsx'
import { Icon } from '../components/Icons.jsx'
import Markdown from '../components/Markdown.jsx'

const LANG_COLORS = ['#0f62fe', '#8a3ffc', '#009d9a', '#ee538b', '#ff832b', '#24a148', '#6f6f6f']

function Stat({ value, label }) {
  return (
    <div className="stat">
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  )
}

export default function OverviewSection({ analysis, goTo }) {
  const { stats } = analysis
  const langEntries = Object.entries(stats.languages || {})
  const langTotal = langEntries.reduce((sum, [, n]) => sum + n, 0) || 1
  const readingMinutes = analysis.learning_path.reduce((sum, s) => sum + (s.minutes || 0), 0)

  return (
    <div className="section">
      {analysis.warnings.length > 0 && (
        <div className="banner banner-warn">
          <Icon name="warning" /> Some sections used static-analysis fallbacks because the AI model was unavailable: {analysis.warnings.join('; ')}.
          Re-run the analysis from the home page to regenerate them.
        </div>
      )}

      <div className="stats-grid">
        <Stat value={stats.analyzed_files.toLocaleString()} label="files analysed" />
        <Stat value={stats.total_lines.toLocaleString()} label="lines of code" />
        <Stat value={analysis.modules.length} label="modules" />
        <Stat value={analysis.dependencies.length} label="internal imports" />
        <Stat value={analysis.api_endpoints.length} label="API endpoints" />
        <Stat value={`${stats.analysis_seconds}s`} label="to generate" />
      </div>

      {langEntries.length > 0 && (
        <div className="card lang-card">
          <div className="lang-bar" role="img" aria-label="Language breakdown">
            {langEntries.map(([lang, n], i) => (
              <span key={lang} style={{ width: `${(n / langTotal) * 100}%`, background: LANG_COLORS[i % LANG_COLORS.length] }} />
            ))}
          </div>
          <ul className="lang-legend">
            {langEntries.map(([lang, n], i) => (
              <li key={lang}>
                <span className="swatch" style={{ background: LANG_COLORS[i % LANG_COLORS.length] }} />
                {lang} <span className="muted">{n} files</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="overview-grid">
        <article className="card">
          <h2 className="card-title">Architecture overview</h2>
          <Markdown>{analysis.architecture_summary}</Markdown>
        </article>

        <aside className="overview-side">
          <div className="card cta-card">
            <h3>Start here</h3>
            <p>A {analysis.learning_path.length}-step reading plan (~{readingMinutes} min) picked for this codebase.</p>
            <button type="button" className="btn btn-primary" onClick={() => goTo('path')}>Open day-1 reading plan</button>
            <button type="button" className="btn btn-ghost" onClick={() => goTo('ticket')}>Map my first ticket</button>
          </div>

          <div className="card">
            <h3 className="side-title"><Icon name="star" /> Entry points</h3>
            {analysis.entry_points.length ? (
              <ul className="plain-list">
                {analysis.entry_points.map((p) => <li key={p}><FileLink path={p} /></li>)}
              </ul>
            ) : <p className="muted">None detected</p>}
          </div>

          <div className="card">
            <h3 className="side-title"><Icon name="graph" /> Most-imported files</h3>
            <p className="muted small">Change these with care: many files depend on them.</p>
            {analysis.hotspots.length ? (
              <ul className="plain-list">
                {analysis.hotspots.slice(0, 8).map((h) => (
                  <li key={h.path} className="hotspot">
                    <FileLink path={h.path} />
                    <span className="count-pill" title={`Imported by ${h.imported_by} files`}>{h.imported_by}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="muted">No internal imports detected</p>}
          </div>

          {Object.keys(analysis.patterns).length > 0 && (
            <div className="card">
              <h3 className="side-title"><Icon name="spark" /> Detected patterns</h3>
              <dl className="pattern-list">
                {Object.entries(analysis.patterns).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key.replace(/_/g, ' ')}</dt>
                    <dd>{Array.isArray(value) ? value.join(', ') : value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}

import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { getAnalysis } from '../api/client.js'
import { Icon } from '../components/Icons.jsx'
import { RepoContext, buildPathResolver } from '../components/RepoContext.jsx'
import FileViewer from '../components/FileViewer.jsx'
import TechStackBadges from '../components/TechStackBadges.jsx'
import OverviewSection from '../sections/OverviewSection.jsx'
import LearningPath from '../sections/LearningPath.jsx'
import ModuleList from '../sections/ModuleList.jsx'
import FileExplorer from '../sections/FileExplorer.jsx'
import ApiEndpoints from '../sections/ApiEndpoints.jsx'
import DocSection from '../sections/DocSection.jsx'
import TicketMapper from '../sections/TicketMapper.jsx'
import ChatPanel from '../sections/ChatPanel.jsx'

const DependencyGraph = lazy(() => import('../sections/DependencyGraph.jsx'))

const SECTIONS = [
  { id: 'overview', label: 'Overview', icon: 'overview' },
  { id: 'path', label: 'Day-1 reading plan', icon: 'path' },
  { id: 'modules', label: 'Modules', icon: 'modules' },
  { id: 'graph', label: 'Dependency graph', icon: 'graph' },
  { id: 'files', label: 'File explorer', icon: 'files' },
  { id: 'apis', label: 'API endpoints', icon: 'api' },
  { id: 'howto', label: 'Add a feature', icon: 'build' },
  { id: 'conventions', label: 'Conventions', icon: 'rules' },
  { id: 'ticket', label: 'Ticket mapper', icon: 'ticket', highlight: true },
  { id: 'chat', label: 'Ask the codebase', icon: 'chat', highlight: true },
]

function collectPaths(tree, prefix = '', out = []) {
  for (const [name, child] of Object.entries(tree || {})) {
    const path = prefix ? `${prefix}/${name}` : name
    if (child === null) out.push(path)
    else collectPaths(child, path, out)
  }
  return out
}

export default function DashboardPage() {
  const { repoId } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const [analysis, setAnalysis] = useState(null)
  const [error, setError] = useState('')
  const [viewer, setViewer] = useState(null)
  const [chatMessages, setChatMessages] = useState([])
  const [chatDraft, setChatDraft] = useState('')
  const [ticketState, setTicketState] = useState({ text: '', result: null })
  const [navOpen, setNavOpen] = useState(false)

  const active = SECTIONS.some((s) => s.id === searchParams.get('tab')) ? searchParams.get('tab') : 'overview'

  useEffect(() => {
    setAnalysis(null)
    setError('')
    getAnalysis(repoId).then(setAnalysis).catch((err) => setError(err.message))
  }, [repoId])

  useEffect(() => {
    if (analysis) document.title = `${analysis.repo_name} · CodeOnboard`
    return () => { document.title = 'CodeOnboard' }
  }, [analysis])

  const goTo = useCallback(
    (id) => {
      setSearchParams({ tab: id })
      setNavOpen(false)
      window.scrollTo({ top: 0 })
    },
    [setSearchParams],
  )

  const allPaths = useMemo(() => (analysis ? collectPaths(analysis.file_tree) : []), [analysis])
  const resolvePath = useMemo(() => buildPathResolver(allPaths), [allPaths])

  const ctx = useMemo(
    () => ({
      repoId,
      analysis,
      resolvePath,
      openFile: (path, line) => setViewer({ path, line }),
      askAbout: (question) => {
        setChatDraft(question)
        setViewer(null)
        goTo('chat')
      },
    }),
    [repoId, analysis, resolvePath, goTo],
  )

  if (error) {
    return (
      <main className="page-center">
        <h1>Analysis not found</h1>
        <p className="muted">{error}</p>
        <Link to="/" className="btn btn-primary">Analyze a repository</Link>
      </main>
    )
  }

  if (!analysis) {
    return (
      <main className="page-center">
        <div className="spinner" aria-label="Loading" />
        <p className="muted">Loading onboarding package...</p>
      </main>
    )
  }

  const section = (() => {
    switch (active) {
      case 'path': return <LearningPath steps={analysis.learning_path} />
      case 'modules': return <ModuleList modules={analysis.modules} />
      case 'graph':
        return (
          <Suspense fallback={<div className="page-center"><div className="spinner" /></div>}>
            <DependencyGraph dependencies={analysis.dependencies} modules={analysis.modules} />
          </Suspense>
        )
      case 'files': return <FileExplorer tree={analysis.file_tree} />
      case 'apis': return <ApiEndpoints endpoints={analysis.api_endpoints} />
      case 'howto':
        return (
          <DocSection
            title="How to add a new feature"
            intro="Generated from this repository's existing structure and patterns. File names are clickable."
            markdown={analysis.how_to_add_feature}
          />
        )
      case 'conventions':
        return (
          <DocSection
            title="Coding conventions"
            intro="Conventions inferred from representative source files, with the evidence cited."
            markdown={analysis.conventions}
          />
        )
      case 'ticket': return <TicketMapper state={ticketState} setState={setTicketState} />
      case 'chat':
        return (
          <ChatPanel
            messages={chatMessages}
            setMessages={setChatMessages}
            draft={chatDraft}
            setDraft={setChatDraft}
            suggestions={analysis.suggested_questions}
          />
        )
      default: return <OverviewSection analysis={analysis} goTo={goTo} />
    }
  })()

  return (
    <RepoContext.Provider value={ctx}>
      <div className="dashboard">
        <div className="repo-bar">
          <div className="repo-bar-main">
            <button type="button" className="icon-btn nav-toggle" onClick={() => setNavOpen((o) => !o)} aria-label="Toggle navigation">
              <Icon name="menu" size={18} />
            </button>
            <div>
              <h1 className="repo-title">
                <a href={analysis.repo_url} target="_blank" rel="noreferrer"><Icon name="github" size={18} /> {analysis.repo_name}</a>
                {analysis.branch && <span className="branch-pill">{analysis.branch}</span>}
              </h1>
              <TechStackBadges stack={analysis.tech_stack} />
            </div>
          </div>
          <Link to="/" className="btn btn-ghost">New analysis</Link>
        </div>

        <div className="dashboard-body">
          <nav className={`sidebar ${navOpen ? 'is-open' : ''}`} aria-label="Onboarding sections">
            {SECTIONS.map((s) => (
              <button
                key={s.id}
                type="button"
                className={`nav-item ${active === s.id ? 'is-active' : ''} ${s.highlight ? 'is-highlight' : ''}`}
                onClick={() => goTo(s.id)}
                aria-current={active === s.id ? 'page' : undefined}
              >
                <Icon name={s.icon} />
                <span>{s.label}</span>
              </button>
            ))}
            <div className="sidebar-foot">
              Generated {new Date(analysis.created_at).toLocaleString()}
              <br />in {analysis.stats.analysis_seconds}s
            </div>
          </nav>
          <main className="dashboard-main">{section}</main>
        </div>
      </div>
      {viewer && <FileViewer path={viewer.path} line={viewer.line} onClose={() => setViewer(null)} />}
    </RepoContext.Provider>
  )
}

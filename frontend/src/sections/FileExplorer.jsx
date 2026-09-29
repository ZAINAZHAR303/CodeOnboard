import { useMemo, useState } from 'react'
import { Icon } from '../components/Icons.jsx'
import { useRepo } from '../components/RepoContext.jsx'

function countFiles(node) {
  if (node === null) return 1
  return Object.values(node).reduce((sum, child) => sum + countFiles(child), 0)
}

function filterTree(node, query, prefix = '') {
  const out = {}
  for (const [name, child] of Object.entries(node)) {
    const path = prefix ? `${prefix}/${name}` : name
    if (child === null) {
      if (path.toLowerCase().includes(query)) out[name] = null
    } else {
      const sub = filterTree(child, query, path)
      if (Object.keys(sub).length) out[name] = sub
    }
  }
  return out
}

function sortedEntries(node) {
  return Object.entries(node).sort(([a, av], [b, bv]) => {
    if ((av === null) !== (bv === null)) return av === null ? 1 : -1
    return a.localeCompare(b)
  })
}

function TreeNode({ name, node, path, depth, expanded, toggle, marks, forceOpen }) {
  const { openFile, resolvePath } = useRepo()
  if (node === null) {
    const mark = marks.get(path)
    const readable = Boolean(resolvePath(path))
    return (
      <li>
        <button
          type="button"
          className={`tree-row tree-file ${mark ? `mark-${mark}` : ''}`}
          style={{ paddingLeft: depth * 16 + 24 }}
          onClick={() => readable && openFile(path)}
          disabled={!readable}
          title={readable ? path : `${path} (not analysed: binary or too large)`}
        >
          <Icon name="file" size={14} />
          <span>{name}</span>
          {mark === 'entry' && <span className="tag">entry</span>}
          {mark === 'key' && <span className="tag tag-key">key</span>}
        </button>
      </li>
    )
  }
  const isOpen = forceOpen || expanded.has(path)
  return (
    <li>
      <button type="button" className="tree-row tree-dir" style={{ paddingLeft: depth * 16 + 6 }} onClick={() => toggle(path)} aria-expanded={isOpen}>
        <Icon name="chevron" size={14} className={isOpen ? 'rot-90' : ''} />
        <Icon name="folder" size={14} />
        <span>{name}</span>
        <span className="muted small">{countFiles(node)}</span>
      </button>
      {isOpen && (
        <ul>
          {sortedEntries(node).map(([childName, child]) => (
            <TreeNode
              key={childName}
              name={childName}
              node={child}
              path={`${path}/${childName}`}
              depth={depth + 1}
              expanded={expanded}
              toggle={toggle}
              marks={marks}
              forceOpen={forceOpen}
            />
          ))}
        </ul>
      )}
    </li>
  )
}

function allDirs(node, prefix = '', out = []) {
  for (const [name, child] of Object.entries(node)) {
    if (child !== null) {
      const path = prefix ? `${prefix}/${name}` : name
      out.push(path)
      allDirs(child, path, out)
    }
  }
  return out
}

export default function FileExplorer({ tree }) {
  const { analysis } = useRepo()
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState(() => {
    const main = ['src', 'app', 'lib', 'backend', 'server'].find((d) => tree[d])
    return new Set(main ? [main] : [])
  })

  const marks = useMemo(() => {
    const map = new Map()
    analysis.key_files.forEach((p) => map.set(p, 'key'))
    analysis.entry_points.forEach((p) => map.set(p, 'entry'))
    return map
  }, [analysis])

  const q = query.trim().toLowerCase()
  const visible = useMemo(() => (q ? filterTree(tree, q) : tree), [tree, q])
  const total = useMemo(() => countFiles(tree), [tree])
  const dirs = useMemo(() => allDirs(tree), [tree])

  const toggle = (path) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })

  return (
    <div className="section">
      <header className="section-head">
        <div>
          <h2>File explorer</h2>
          <p className="muted">{total} files in {dirs.length} folders. Entry points and key files are tagged; click any file to read it.</p>
        </div>
        <div className="toolbar">
          <input className="search-input" placeholder="Filter files..." value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Filter files" />
          <button type="button" className="btn btn-small" onClick={() => setExpanded(new Set(dirs))}>Expand all</button>
          <button type="button" className="btn btn-small" onClick={() => setExpanded(new Set())}>Collapse all</button>
        </div>
      </header>
      <div className="card tree-card">
        {Object.keys(visible).length === 0 ? (
          <p className="muted empty">No files match "{query}".</p>
        ) : (
          <ul className="tree">
            {sortedEntries(visible).map(([name, node]) => (
              <TreeNode key={name} name={name} node={node} path={name} depth={0} expanded={expanded} toggle={toggle} marks={marks} forceOpen={Boolean(q)} />
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

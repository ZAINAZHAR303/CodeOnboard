import { useMemo, useState } from 'react'
import { Background, Controls, MarkerType, MiniMap, ReactFlow } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import dagre from '@dagrejs/dagre'
import { useRepo } from '../components/RepoContext.jsx'

const PALETTE = ['#0f62fe', '#8a3ffc', '#009d9a', '#ee538b', '#ff832b', '#24a148', '#1192e8', '#b28600', '#fa4d56', '#6f6f6f']
const MAX_NODES = 60
const NODE_H = 34

function moduleIndex(modules) {
  const map = new Map()
  modules.forEach((m) => m.files.forEach((f) => map.set(f, m.path)))
  return map
}

function layout(nodes, edges) {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', nodesep: 14, ranksep: 90, marginx: 20, marginy: 20 })
  g.setDefaultEdgeLabel(() => ({}))
  nodes.forEach((n) => g.setNode(n.id, { width: n.width, height: NODE_H }))
  edges.forEach((e) => g.setEdge(e.source, e.target))
  dagre.layout(g)
  return nodes.map((n) => {
    const pos = g.node(n.id)
    return { ...n, position: { x: pos.x - n.width / 2, y: pos.y - NODE_H / 2 } }
  })
}

export default function DependencyGraph({ dependencies, modules }) {
  const { openFile } = useRepo()
  const [moduleFilter, setModuleFilter] = useState('all')
  const [selected, setSelected] = useState(null)

  const fileModule = useMemo(() => moduleIndex(modules), [modules])
  const moduleColors = useMemo(() => {
    const map = new Map()
    modules.forEach((m, i) => map.set(m.path, PALETTE[i % PALETTE.length]))
    return map
  }, [modules])

  const graph = useMemo(() => {
    const scoped = moduleFilter === 'all'
      ? dependencies
      : dependencies.filter((d) => fileModule.get(d.source) === moduleFilter || fileModule.get(d.target) === moduleFilter)
    const degree = new Map()
    scoped.forEach((d) => {
      degree.set(d.source, (degree.get(d.source) || 0) + 1)
      degree.set(d.target, (degree.get(d.target) || 0) + 1)
    })
    const ranked = [...degree.entries()].sort((a, b) => b[1] - a[1])
    const kept = new Set(ranked.slice(0, MAX_NODES).map(([id]) => id))
    const keptEdges = scoped.filter((d) => kept.has(d.source) && kept.has(d.target))

    const rawNodes = [...kept].map((id) => {
      const label = id.split('/').pop()
      return {
        id,
        width: Math.max(90, label.length * 7.4 + 28),
        data: { label, module: fileModule.get(id) || '(other)', degree: degree.get(id) },
      }
    })
    const positioned = layout(rawNodes, keptEdges)
    return { nodes: positioned, edges: keptEdges, truncated: ranked.length > MAX_NODES, total: ranked.length }
  }, [dependencies, fileModule, moduleFilter])

  const neighbours = useMemo(() => {
    if (!selected) return null
    const set = new Set([selected])
    graph.edges.forEach((e) => {
      if (e.source === selected) set.add(e.target)
      if (e.target === selected) set.add(e.source)
    })
    return set
  }, [selected, graph.edges])

  const nodes = graph.nodes.map((n) => {
    const color = moduleColors.get(n.data.module) || '#6f6f6f'
    const dim = neighbours && !neighbours.has(n.id)
    return {
      id: n.id,
      position: n.position,
      data: { label: n.data.label },
      className: `graph-node ${selected === n.id ? 'is-selected' : ''}`,
      style: { width: n.width, borderLeftColor: color, opacity: dim ? 0.25 : 1 },
      sourcePosition: 'right',
      targetPosition: 'left',
    }
  })

  const edges = graph.edges.map((e) => {
    const active = selected && (e.source === selected || e.target === selected)
    return {
      id: `${e.source}->${e.target}`,
      source: e.source,
      target: e.target,
      animated: Boolean(active),
      markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
      style: { stroke: active ? 'var(--primary)' : 'var(--edge)', strokeWidth: active ? 2 : 1, opacity: selected && !active ? 0.15 : 1 },
    }
  })

  const selectedInfo = selected && {
    path: selected,
    module: fileModule.get(selected) || '(other)',
    imports: graph.edges.filter((e) => e.source === selected).length,
    importedBy: graph.edges.filter((e) => e.target === selected).length,
  }

  const modulesWithEdges = modules.filter((m) => dependencies.some((d) => fileModule.get(d.source) === m.path || fileModule.get(d.target) === m.path))

  return (
    <div className="section">
      <header className="section-head">
        <div>
          <h2>Dependency graph</h2>
          <p className="muted">
            {graph.nodes.length} files · {graph.edges.length} imports
            {graph.truncated && ` · showing the ${MAX_NODES} most-connected of ${graph.total} files`}. Click a file to trace its connections.
          </p>
        </div>
        <select className="select" value={moduleFilter} onChange={(e) => { setModuleFilter(e.target.value); setSelected(null) }} aria-label="Filter by module">
          <option value="all">All modules</option>
          {modulesWithEdges.map((m) => <option key={m.path} value={m.path}>{m.path}</option>)}
        </select>
      </header>

      {dependencies.length === 0 ? (
        <div className="card empty">
          No internal imports were detected. The project may use a language whose imports are not parsed yet (supported: Python, JavaScript/TypeScript, Java/Kotlin, C/C++), or wire modules together at runtime.
        </div>
      ) : (
        <div className="graph-wrap card">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            minZoom={0.1}
            nodesDraggable
            nodesConnectable={false}
            onNodeClick={(_, node) => setSelected((s) => (s === node.id ? null : node.id))}
            onPaneClick={() => setSelected(null)}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={18} size={1} />
            <Controls showInteractive={false} />
            <MiniMap pannable zoomable nodeColor={(n) => n.style?.borderLeftColor || '#999'} />
          </ReactFlow>

          {selectedInfo && (
            <div className="graph-info">
              <strong title={selectedInfo.path}>{selectedInfo.path}</strong>
              <span className="muted small">module: {selectedInfo.module}</span>
              <span className="small">imports {selectedInfo.imports} · imported by {selectedInfo.importedBy}</span>
              <button type="button" className="btn btn-small btn-primary" onClick={() => openFile(selectedInfo.path)}>Open file</button>
            </div>
          )}
        </div>
      )}

      <ul className="legend">
        {modulesWithEdges.slice(0, 12).map((m) => (
          <li key={m.path}><span className="swatch" style={{ background: moduleColors.get(m.path) }} />{m.path}</li>
        ))}
      </ul>
    </div>
  )
}

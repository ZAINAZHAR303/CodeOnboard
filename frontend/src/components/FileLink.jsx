import { useRepo } from './RepoContext.jsx'

export default function FileLink({ path, label, line }) {
  const { openFile, resolvePath } = useRepo()
  const resolved = resolvePath(path)
  const text = label || path
  if (!resolved) return <code className="file-chip is-static">{text}</code>
  return (
    <button type="button" className="file-chip" onClick={() => openFile(resolved, line)} title={`Open ${resolved}`}>
      {text}
    </button>
  )
}

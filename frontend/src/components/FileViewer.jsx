import { useEffect, useRef, useState } from 'react'
import { getFile } from '../api/client.js'
import { Icon } from './Icons.jsx'
import { useRepo } from './RepoContext.jsx'

export default function FileViewer({ path, line, onClose }) {
  const { repoId, openFile, askAbout } = useRepo()
  const [file, setFile] = useState(null)
  const [error, setError] = useState('')
  const codeRef = useRef(null)

  useEffect(() => {
    setFile(null)
    setError('')
    getFile(repoId, path).then(setFile).catch((err) => setError(err.message))
  }, [repoId, path])

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    if (file && line && codeRef.current) {
      codeRef.current.querySelector(`[data-line="${line}"]`)?.scrollIntoView({ block: 'center' })
    }
  }, [file, line])

  const lines = file ? file.content.split('\n') : []

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={path} onClick={(e) => e.stopPropagation()}>
        <header className="drawer-head">
          <div className="drawer-title">
            <Icon name="file" />
            <span title={path}>{path}</span>
          </div>
          <div className="drawer-actions">
            <button type="button" className="btn btn-small" onClick={() => askAbout(`Explain \`${path}\`: what is it responsible for, and how does it fit into the rest of the codebase?`)}>
              <Icon name="chat" size={14} /> Ask AI about this file
            </button>
            <button type="button" className="icon-btn" onClick={onClose} aria-label="Close file viewer"><Icon name="close" size={18} /></button>
          </div>
        </header>

        {error && <div className="banner banner-warn drawer-banner">{error}</div>}
        {!file && !error && <div className="drawer-loading"><div className="spinner" /></div>}

        {file && (
          <>
            <div className="drawer-meta">
              <span>{file.language}</span>
              <span>{lines.length} lines</span>
              <span>{(file.size / 1024).toFixed(1)} KB</span>
            </div>
            {(file.imports.length > 0 || file.imported_by.length > 0) && (
              <div className="drawer-deps">
                {file.imports.length > 0 && (
                  <div>
                    <h4>Imports ({file.imports.length})</h4>
                    {file.imports.map((p) => <button key={p} type="button" className="file-chip" onClick={() => openFile(p)}>{p}</button>)}
                  </div>
                )}
                {file.imported_by.length > 0 && (
                  <div>
                    <h4>Imported by ({file.imported_by.length})</h4>
                    {file.imported_by.map((p) => <button key={p} type="button" className="file-chip" onClick={() => openFile(p)}>{p}</button>)}
                  </div>
                )}
              </div>
            )}
            <pre className="code-view" ref={codeRef}>
              {lines.map((text, i) => (
                <div key={i} data-line={i + 1} className={`code-line ${line === i + 1 ? 'is-target' : ''}`}>
                  <span className="ln">{i + 1}</span>
                  <span className="lc">{text || ' '}</span>
                </div>
              ))}
            </pre>
          </>
        )}
      </aside>
    </div>
  )
}

import { createContext, useContext } from 'react'

export const RepoContext = createContext(null)

export function useRepo() {
  const ctx = useContext(RepoContext)
  if (!ctx) throw new Error('useRepo must be used inside RepoContext')
  return ctx
}

export function buildPathResolver(filePaths) {
  const known = new Set(filePaths)
  const byBase = new Map()
  for (const p of filePaths) {
    const base = p.split('/').pop()
    byBase.set(base, byBase.has(base) ? null : p)
  }
  return (raw) => {
    if (!raw || raw.length > 200 || /\s/.test(raw)) return null
    const cleaned = raw.replace(/^\.?\//, '').replace(/:\d+(-\d+)?$/, '').replace(/\/$/, '')
    if (known.has(cleaned)) return cleaned
    if (cleaned.includes('.') && !cleaned.includes('/')) return byBase.get(cleaned) || null
    for (const p of known) if (p.endsWith('/' + cleaned) && cleaned.includes('/')) return p
    return null
  }
}

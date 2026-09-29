function formatDetail(detail) {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
  return JSON.stringify(detail)
}

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(`/api${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    })
  } catch {
    throw new Error('Cannot reach the CodeOnboard API. Is the backend running on port 8000?')
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(formatDetail(data.detail) || `Request failed (${res.status})`)
  return data
}

export const getHealth = () => request('/health')

export const analyzeRepo = (repoUrl, branch, force = false) =>
  request('/analyze', {
    method: 'POST',
    body: JSON.stringify({ repo_url: repoUrl, branch: branch || null, force }),
  })

export const getJob = (jobId) => request(`/jobs/${encodeURIComponent(jobId)}`)

export const listAnalyses = () => request('/analyses')

export const getAnalysis = (repoId) => request(`/analysis/${encodeURIComponent(repoId)}`)

export const getFile = (repoId, path) =>
  request(`/analysis/${encodeURIComponent(repoId)}/file?path=${encodeURIComponent(path)}`)

export const chatWithRepo = (repoId, question, history) =>
  request('/chat', {
    method: 'POST',
    body: JSON.stringify({ repo_id: repoId, question, history }),
  })

export const mapTicket = (repoId, ticketDescription) =>
  request('/map-ticket', {
    method: 'POST',
    body: JSON.stringify({ repo_id: repoId, ticket_description: ticketDescription }),
  })

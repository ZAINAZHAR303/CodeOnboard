import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useRepo } from './RepoContext.jsx'

function InlineCode({ children, className, ...rest }) {
  const { openFile, resolvePath } = useRepo()
  const text = String(children ?? '')
  const isBlock = Boolean(className) || text.includes('\n')
  if (!isBlock) {
    const resolved = resolvePath(text)
    if (resolved) {
      const line = Number((text.match(/:(\d+)$/) || [])[1]) || undefined
      return (
        <button type="button" className="file-chip" onClick={() => openFile(resolved, line)} title={`Open ${resolved}`}>
          {text}
        </button>
      )
    }
  }
  return <code className={className} {...rest}>{children}</code>
}

export default function Markdown({ children }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code: InlineCode,
          a: ({ children: kids, ...props }) => <a {...props} target="_blank" rel="noreferrer">{kids}</a>,
        }}
      >
        {children || ''}
      </ReactMarkdown>
    </div>
  )
}

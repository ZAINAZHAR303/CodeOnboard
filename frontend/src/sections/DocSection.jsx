import { Icon } from '../components/Icons.jsx'
import Markdown from '../components/Markdown.jsx'

export default function DocSection({ title, intro, markdown }) {
  return (
    <div className="section">
      <header className="section-head">
        <div>
          <h2>{title}</h2>
          <p className="muted"><Icon name="spark" size={14} /> {intro}</p>
        </div>
      </header>
      <article className="card">
        <Markdown>{markdown}</Markdown>
      </article>
    </div>
  )
}

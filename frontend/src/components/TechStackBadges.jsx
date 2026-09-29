const TONES = {
  blue: ['Python', 'TypeScript', 'Docker', 'Docker Compose', 'Go', 'Kubernetes', 'FastAPI', 'Flask', 'C#', 'Dart'],
  green: ['Node.js', 'Vue', 'Nuxt', 'Django', 'Spring Boot', 'Express', 'MongoDB', 'Celery', 'NestJS'],
  purple: ['React', 'Next.js', 'Redux', 'GraphQL', 'Vite', 'Tailwind CSS', 'Svelte', 'SvelteKit', 'Angular'],
  orange: ['JavaScript', 'Java', 'Rust', 'Kotlin', 'Swift', 'Scala', 'PHP', 'Ruby', 'Ruby on Rails', 'Laravel'],
  teal: ['SQLAlchemy', 'Prisma', 'PostgreSQL', 'Redis', 'TypeORM', 'Sequelize', 'Alembic', 'Pydantic'],
}

const toneFor = (name) => Object.keys(TONES).find((tone) => TONES[tone].includes(name)) || 'gray'

export default function TechStackBadges({ stack = [] }) {
  if (!stack.length) return null
  return (
    <ul className="badges" aria-label="Detected tech stack">
      {stack.map((tech) => (
        <li key={tech} className={`badge tone-${toneFor(tech)}`}>{tech}</li>
      ))}
    </ul>
  )
}

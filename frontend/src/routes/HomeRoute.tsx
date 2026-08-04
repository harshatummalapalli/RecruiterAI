import { Brain, Search, TriangleAlert } from 'lucide-react'
import { RoleCard } from '../components/shell/RoleCard'

const workingRoles = [
  {
    title: 'Senior Full Stack Engineer',
    location: 'Remote · US',
    status: '8 matches',
    details: 'Strong React, Node, and product engineering background. 3 candidates already shortlisted.',
    actionLabel: 'Open role',
  },
  {
    title: 'Product Designer',
    location: 'New York, NY',
    status: '5 matches',
    details: 'Design systems and B2B SaaS experience stand out. 2 candidates need review.',
    actionLabel: 'Open role',
  },
  {
    title: 'Data Engineer',
    location: 'Austin, TX',
    status: '12 matches',
    details: 'Pipeline and analytics expertise are strong. Search scope can be widened if needed.',
    actionLabel: 'Open role',
  },
]

const attentionItems = [
  {
    title: 'JD still needs a location decision',
    detail: 'Leaving the role remote-only is narrowing the pool more than expected.',
    level: 'Warning',
  },
  {
    title: '2 candidates are missing resume data',
    detail: 'Resume enrichment has not completed for two promising profiles.',
    level: 'Needs review',
  },
  {
    title: 'Search brief has not been edited',
    detail: 'The current brief still mirrors the pasted JD. Narrow the requirements before sourcing.',
    level: 'Action needed',
  },
]

function getGreeting() {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning, Harsha.'
  if (hour < 18) return 'Good afternoon, Harsha.'
  return 'Good evening, Harsha.'
}

export function HomeRoute() {
  return (
    <section className="home-screen" aria-label="Home">
      <header className="home-screen__hero">
        <div>
          <p className="home-screen__eyebrow">Recruiter Workbench</p>
          <h1>{getGreeting()}</h1>
          <p>
            Start from a JD, review the brief, and move through sourcing without losing control of the process.
          </p>
        </div>
        <div className="home-screen__signal">
          <Brain size={18} aria-hidden="true" />
          <span>AI assists. You decide.</span>
        </div>
      </header>

      <section className="home-card home-card--composer" aria-labelledby="hiring-title">
        <div className="home-card__header">
          <div>
            <p className="home-card__eyebrow">Search intake</p>
            <h2 id="hiring-title">What are you hiring for?</h2>
          </div>
          <div className="home-card__badge">
            <Search size={14} aria-hidden="true" />
            <span>Global search is available above</span>
          </div>
        </div>

        <label className="home-card__field" htmlFor="home-jd">
          <span>Paste the job description or describe the role in plain language.</span>
          <textarea
            id="home-jd"
            placeholder="Paste the JD here or type the requirements, must-haves, nice-to-haves, and constraints..."
            rows={10}
            defaultValue=""
          />
        </label>

        <div className="home-card__actions">
          <button type="button" className="button button--primary">
            Start Search
          </button>
          <button type="button" className="button button--secondary">
            Continue Last Search
          </button>
        </div>
      </section>

      <section className="home-section" aria-labelledby="working-title">
        <div className="home-section__header">
          <div>
            <p className="home-card__eyebrow">Continue Working</p>
            <h2 id="working-title">3 roles in progress</h2>
          </div>
          <span className="home-section__meta">Static preview data</span>
        </div>

        <div className="home-section__grid">
          {workingRoles.map((role) => (
            <RoleCard key={role.title} {...role} />
          ))}
        </div>
      </section>

      <section className="home-section" aria-labelledby="attention-title">
        <div className="home-section__header">
          <div>
            <p className="home-card__eyebrow">Needs Attention</p>
            <h2 id="attention-title">Items that need a recruiter decision</h2>
          </div>
          <span className="home-section__meta">3 alerts</span>
        </div>

        <div className="home-attention">
          {attentionItems.map((item) => (
            <article key={item.title} className="home-attention__item">
              <div className="home-attention__icon" aria-hidden="true">
                <TriangleAlert size={16} />
              </div>
              <div className="home-attention__content">
                <div className="home-attention__meta">{item.level}</div>
                <h3>{item.title}</h3>
                <p>{item.detail}</p>
              </div>
            </article>
          ))}
        </div>
      </section>
    </section>
  )
}

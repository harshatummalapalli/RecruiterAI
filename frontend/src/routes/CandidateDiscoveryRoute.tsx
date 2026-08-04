import { Check, Filter, Plus, Search, SlidersHorizontal, X } from 'lucide-react'
import { useMemo, useState } from 'react'

type Candidate = {
  id: string
  name: string
  title: string
  location: string
  experience: number
  match: number
  status: string
  skills: string[]
  bio: string
  companies: string[]
  availability: string
}

const candidates: Candidate[] = [
  {
    id: 'cand-1',
    name: 'Avery Chen',
    title: 'Senior Product Designer',
    location: 'New York, NY',
    experience: 8,
    match: 96,
    status: 'Ready to contact',
    skills: ['Product Design', 'Figma', 'Design Systems', 'Accessibility'],
    bio: 'Led design for a workflow-heavy B2B platform and improved task completion by simplifying dense interactions.',
    companies: ['Notion', 'Ramp'],
    availability: '2 weeks',
  },
  {
    id: 'cand-2',
    name: 'Jordan Patel',
    title: 'Lead UX Designer',
    location: 'Remote · US',
    experience: 10,
    match: 92,
    status: 'Strong fit',
    skills: ['UX Research', 'SaaS', 'Prototyping', 'Information Architecture'],
    bio: 'Built design systems and product flows for internal tools used by recruiting and operations teams.',
    companies: ['Linear', 'Gusto'],
    availability: 'Immediately',
  },
  {
    id: 'cand-3',
    name: 'Mia Rodriguez',
    title: 'Product Designer',
    location: 'Austin, TX',
    experience: 6,
    match: 89,
    status: 'Needs review',
    skills: ['B2B SaaS', 'Figma', 'Interaction Design', 'Research'],
    bio: 'Strong visual craft and fast iteration on admin workflows, analytics pages, and search experiences.',
    companies: ['Webflow', 'Intercom'],
    availability: '3 weeks',
  },
  {
    id: 'cand-4',
    name: 'Noah Brooks',
    title: 'Staff Product Designer',
    location: 'San Francisco, CA',
    experience: 12,
    match: 85,
    status: 'Broadening needed',
    skills: ['Systems Thinking', 'Design Ops', 'SaaS', 'Accessibility'],
    bio: 'Experience with high-scale workflow tools, but background leans toward platform and ops rather than product UI.',
    companies: ['Stripe', 'Asana'],
    availability: '1 month',
  },
  {
    id: 'cand-5',
    name: 'Sofia Turner',
    title: 'Senior UX Designer',
    location: 'Remote · Canada',
    experience: 7,
    match: 91,
    status: 'Ready to contact',
    skills: ['Workflow Design', 'Design Systems', 'B2B SaaS', 'Content Strategy'],
    bio: 'Designs compact data-heavy interfaces and collaborates closely with engineering on edge cases.',
    companies: ['Shopify', 'Airtable'],
    availability: '2 weeks',
  },
  {
    id: 'cand-6',
    name: 'Ethan Kim',
    title: 'Senior Interaction Designer',
    location: 'Boston, MA',
    experience: 9,
    match: 88,
    status: 'Potential fit',
    skills: ['Interaction Design', 'Figma', 'Research', 'Prototyping'],
    bio: 'Good interaction work, though some experience is in consumer products rather than internal operations software.',
    companies: ['HubSpot', 'Dropbox'],
    availability: '4 weeks',
  },
]

const locationFilters = ['All locations', 'Remote', 'New York, NY', 'Austin, TX', 'San Francisco, CA']
const skillFilters = ['All skills', 'Figma', 'Design Systems', 'UX Research', 'B2B SaaS', 'Accessibility']
const sortOptions = [
  { label: 'Best match', value: 'match' },
  { label: 'Most experience', value: 'experience' },
  { label: 'Name', value: 'name' },
]

export function CandidateDiscoveryRoute() {
  const [query, setQuery] = useState('')
  const [location, setLocation] = useState('All locations')
  const [skill, setSkill] = useState('All skills')
  const [sortBy, setSortBy] = useState('match')
  const [selectedCandidates, setSelectedCandidates] = useState<string[]>([])
  const [activeCandidateId, setActiveCandidateId] = useState<string | null>(candidates[0]?.id ?? null)

  const activeCandidate = candidates.find((candidate) => candidate.id === activeCandidateId) ?? null

  const filteredCandidates = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()

    const filtered = candidates.filter((candidate) => {
      const queryMatch =
        !normalizedQuery ||
        [candidate.name, candidate.title, candidate.location, candidate.bio, ...candidate.skills]
          .join(' ')
          .toLowerCase()
          .includes(normalizedQuery)

      const locationMatch =
        location === 'All locations' ||
        candidate.location === location ||
        (location === 'Remote' && candidate.location.startsWith('Remote'))

      const skillMatch = skill === 'All skills' || candidate.skills.includes(skill)

      return queryMatch && locationMatch && skillMatch
    })

    return filtered.sort((left, right) => {
      if (sortBy === 'experience') return right.experience - left.experience
      if (sortBy === 'name') return left.name.localeCompare(right.name)
      return right.match - left.match
    })
  }, [location, query, skill, sortBy])

  const compareCount = selectedCandidates.length

  function toggleCompare(candidateId: string) {
    setSelectedCandidates((current) =>
      current.includes(candidateId) ? current.filter((id) => id !== candidateId) : [...current, candidateId],
    )
  }

  function openCandidate(candidateId: string) {
    setActiveCandidateId(candidateId)
  }

  return (
    <section className="candidate-discovery" aria-label="Candidate Discovery">
      <header className="candidate-discovery__hero">
        <div>
          <p className="candidate-discovery__eyebrow">Candidate sourcing</p>
          <h1>Candidate Discovery</h1>
          <p>Review placeholder talent data, compare candidates, and open a profile drawer without leaving the page.</p>
        </div>
        <div className="candidate-discovery__actions">
          <button type="button" className="button button--secondary">
            <Filter size={16} aria-hidden="true" />
            Filters
          </button>
          <button type="button" className="button button--primary">
            <Plus size={16} aria-hidden="true" />
            Add to Pipeline
          </button>
        </div>
      </header>

      <section className="candidate-discovery__toolbar" aria-label="Search and filters">
        <label className="candidate-discovery__search" htmlFor="candidate-search">
          <Search size={16} aria-hidden="true" />
          <input
            id="candidate-search"
            type="search"
            placeholder="Search candidates, skills, companies, or titles"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>

        <label className="candidate-discovery__select">
          <span>Location</span>
          <select value={location} onChange={(event) => setLocation(event.target.value)}>
            {locationFilters.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>

        <label className="candidate-discovery__select">
          <span>Skill</span>
          <select value={skill} onChange={(event) => setSkill(event.target.value)}>
            {skillFilters.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>

        <label className="candidate-discovery__select">
          <span>Sort by</span>
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
            {sortOptions.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="candidate-discovery__content">
        <div className="candidate-discovery__grid">
          {filteredCandidates.map((candidate) => {
            const isSelected = selectedCandidates.includes(candidate.id)

            return (
              <article
                key={candidate.id}
                className="candidate-card"
                role="button"
                tabIndex={0}
                onClick={() => openCandidate(candidate.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    openCandidate(candidate.id)
                  }
                }}
              >
                <div className="candidate-card__header">
                  <label
                    className="candidate-card__compare"
                    onClick={(event) => event.stopPropagation()}
                    onKeyDown={(event) => event.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleCompare(candidate.id)}
                    />
                    <span>Compare</span>
                  </label>
                  <span className="candidate-card__match">{candidate.match}% match</span>
                </div>

                <div className="candidate-card__body">
                  <div>
                    <h2>{candidate.name}</h2>
                    <p>{candidate.title}</p>
                  </div>
                  <div className="candidate-card__meta">
                    <span>{candidate.location}</span>
                    <span>{candidate.experience} years</span>
                    <span>{candidate.availability}</span>
                  </div>
                  <p className="candidate-card__bio">{candidate.bio}</p>
                  <div className="candidate-card__tags">
                    {candidate.skills.slice(0, 4).map((item) => (
                      <span key={item}>{item}</span>
                    ))}
                  </div>
                </div>

                <div className="candidate-card__footer" onClick={(event) => event.stopPropagation()}>
                  <button type="button" className="candidate-card__link" onClick={() => openCandidate(candidate.id)}>
                    View profile
                  </button>
                  <button type="button" className="candidate-card__pipeline" onClick={() => toggleCompare(candidate.id)}>
                    {isSelected ? <Check size={14} aria-hidden="true" /> : <Plus size={14} aria-hidden="true" />}
                    {isSelected ? 'Selected' : 'Select'}
                  </button>
                </div>
              </article>
            )
          })}
        </div>

        <aside className="candidate-discovery__drawer" aria-label="Candidate drawer">
          {activeCandidate ? (
            <>
              <div className="candidate-drawer__header">
                <div>
                  <p className="candidate-discovery__eyebrow">Candidate drawer</p>
                  <h2>{activeCandidate.name}</h2>
                  <p>{activeCandidate.title}</p>
                </div>
                <button type="button" className="candidate-drawer__close" onClick={() => setActiveCandidateId(null)}>
                  <X size={16} aria-hidden="true" />
                </button>
              </div>

              <div className="candidate-drawer__section">
                <div className="candidate-drawer__metrics">
                  <div>
                    <span>Match</span>
                    <strong>{activeCandidate.match}%</strong>
                  </div>
                  <div>
                    <span>Experience</span>
                    <strong>{activeCandidate.experience} years</strong>
                  </div>
                </div>
              </div>

              <div className="candidate-drawer__section">
                <h3>Details</h3>
                <ul>
                  <li>{activeCandidate.location}</li>
                  <li>{activeCandidate.status}</li>
                  <li>{activeCandidate.availability}</li>
                </ul>
              </div>

              <div className="candidate-drawer__section">
                <h3>Skills</h3>
                <div className="candidate-card__tags candidate-card__tags--drawer">
                  {activeCandidate.skills.map((item) => (
                    <span key={item}>{item}</span>
                  ))}
                </div>
              </div>

              <div className="candidate-drawer__section">
                <h3>Recent companies</h3>
                <ul>
                  {activeCandidate.companies.map((company) => (
                    <li key={company}>{company}</li>
                  ))}
                </ul>
              </div>

              <button type="button" className="button button--primary candidate-drawer__pipeline">
                <Plus size={16} aria-hidden="true" />
                Add to Pipeline
              </button>
            </>
          ) : (
            <div className="candidate-drawer__empty">
              <SlidersHorizontal size={18} aria-hidden="true" />
              <p>Select a candidate card to open the drawer.</p>
            </div>
          )}
        </aside>
      </section>

      {compareCount > 0 ? (
        <div className="candidate-comparebar" aria-label="Compare selection">
          <div>
            <strong>{compareCount} selected for compare</strong>
            <span>Placeholder compare queue only</span>
          </div>
          <button type="button" className="button button--secondary" onClick={() => setSelectedCandidates([])}>
            Clear selection
          </button>
          <button type="button" className="button button--primary">
            Add to Pipeline
          </button>
        </div>
      ) : null}
    </section>
  )
}

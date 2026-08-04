const parsedJD = `Senior Product Designer

We are looking for a product designer who can shape workflows for a fast-moving internal tool.

Responsibilities:
- Translate messy recruiter requirements into clear UX patterns
- Partner with product and engineering on design direction
- Create scalable interaction patterns for dense data views

Qualifications:
- 5+ years of product design experience
- Strong systems thinking and collaboration skills
- Experience designing B2B SaaS tools`

const requiredCriteria = [
  '5+ years of product design experience',
  'Strong systems thinking and information hierarchy skills',
  'Experience shipping B2B SaaS products',
  'Comfort working with dense operational workflows',
]

const preferredCriteria = [
  'Experience with recruiter, ATS, or talent workflows',
  'Working knowledge of modern design systems',
  'Ability to prototype quickly in Figma or similar tools',
]

const companyFilters = [
  { label: 'Industry', value: 'B2B SaaS' },
  { label: 'Company stage', value: 'Series A to Series C' },
  { label: 'Team size', value: '50 to 500' },
]

const skills = ['Product Design', 'UX Research', 'Figma', 'Design Systems', 'B2B SaaS', 'Accessibility']

export function RoleReviewRoute() {
  return (
    <section className="role-review" aria-label="Role Review">
      <header className="role-review__hero">
        <div>
          <p className="role-review__eyebrow">Search brief review</p>
          <h1>Parsed JD editor</h1>
          <p>
            Review the parsed job description, tighten the criteria, and prepare the search before candidate sourcing.
          </p>
        </div>
        <div className="role-review__summary">
          <div>
            <span>Search quality</span>
            <strong>Draft brief</strong>
          </div>
          <div>
            <span>Estimated matches</span>
            <strong>34 candidates</strong>
          </div>
        </div>
      </header>

      <div className="role-review__layout">
        <section className="role-review__main">
          <article className="role-review-card role-review-card--editor">
            <div className="role-review-card__header">
              <div>
                <p className="role-review-card__eyebrow">Parsed JD</p>
                <h2>Editable search brief</h2>
              </div>
              <span className="role-review-card__badge">Placeholder data</span>
            </div>
            <textarea aria-label="Parsed JD editor" defaultValue={parsedJD} />
          </article>

          <article className="role-review-card">
            <div className="role-review-card__header">
              <div>
                <p className="role-review-card__eyebrow">Criteria</p>
                <h2>Required criteria</h2>
              </div>
              <span className="role-review-card__count">{requiredCriteria.length} items</span>
            </div>
            <ul className="role-review-list">
              {requiredCriteria.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </article>

          <article className="role-review-card">
            <div className="role-review-card__header">
              <div>
                <p className="role-review-card__eyebrow">Criteria</p>
                <h2>Preferred criteria</h2>
              </div>
              <span className="role-review-card__count">{preferredCriteria.length} items</span>
            </div>
            <ul className="role-review-list role-review-list--soft">
              {preferredCriteria.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </article>
        </section>

        <aside className="role-review__sidebar">
          <article className="role-review-card">
            <div className="role-review-card__header">
              <div>
                <p className="role-review-card__eyebrow">Filters</p>
                <h2>Company filters</h2>
              </div>
            </div>
            <div className="role-review-filters">
              {companyFilters.map((item) => (
                <label key={item.label} className="role-review-field">
                  <span>{item.label}</span>
                  <input type="text" defaultValue={item.value} aria-label={item.label} />
                </label>
              ))}
            </div>
          </article>

          <article className="role-review-card">
            <div className="role-review-card__header">
              <div>
                <p className="role-review-card__eyebrow">Filters</p>
                <h2>Experience range</h2>
              </div>
            </div>
            <div className="role-review-range">
              <div>
                <span>Minimum</span>
                <strong>5 years</strong>
              </div>
              <div>
                <span>Maximum</span>
                <strong>8 years</strong>
              </div>
            </div>
          </article>

          <article className="role-review-card">
            <div className="role-review-card__header">
              <div>
                <p className="role-review-card__eyebrow">Filters</p>
                <h2>Location</h2>
              </div>
            </div>
            <label className="role-review-field">
              <span>Target location</span>
              <input type="text" defaultValue="Remote · US time zones" aria-label="Target location" />
            </label>
          </article>

          <article className="role-review-card">
            <div className="role-review-card__header">
              <div>
                <p className="role-review-card__eyebrow">Filters</p>
                <h2>Skills</h2>
              </div>
            </div>
            <div className="role-review-tags">
              {skills.map((skill) => (
                <span key={skill}>{skill}</span>
              ))}
            </div>
          </article>

          <button type="button" className="button button--primary role-review__submit">
            Find Candidates
          </button>
        </aside>
      </div>
    </section>
  )
}

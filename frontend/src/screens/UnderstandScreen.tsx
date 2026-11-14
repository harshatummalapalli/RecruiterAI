import { useEffect, useState } from 'react'
import { Check, Lock } from 'lucide-react'
import type { SearchBoundary } from '../models/searchBoundary'
import './UnderstandScreen.css'

// The "Understand" step of the 3-step flow (Ask -> Understand -> Review): shown
// while the reader works through the role (~30s), so the wait reads as the agent
// doing work, not a spinner. Mirrors the locked mockup's Step 2: "what you wrote"
// beside "planning the search" (the enforced non-negotiables + an animated
// checklist). The checklist advances on timers — an honest "work in progress"
// signal; the real qualifications appear on the brief once the read completes.

const STEPS = ['Read the role', 'Locked the non-negotiables', 'Setting the qualifications to judge on']

function titleCase(value: string): string {
  return value ? value[0].toUpperCase() + value.slice(1) : value
}

// The enforced hard filters, as plain chips — from the recruiter's boundary, never
// inferred from the description. No vendor names, no counts.
function fenceChips(boundary: SearchBoundary): string[] {
  const chips: string[] = []
  const cities = (boundary.cities ?? []).map((c) => c.trim()).filter(Boolean)
  if (cities.length) {
    chips.push(...cities)
  } else {
    const place = boundary.city?.trim() || boundary.state?.trim() || boundary.country?.trim()
    if (place) chips.push(place)
  }
  if (boundary.work_mode) chips.push(titleCase(boundary.work_mode))
  if (boundary.min_years != null) chips.push(`${boundary.min_years}+ yrs`)
  for (const company of boundary.exclude_companies ?? []) {
    if (company.trim()) chips.push(`not ${company.trim()}`)
  }
  return chips
}

export function UnderstandScreen({ jd, title, boundary }: { jd: string; title: string; boundary: SearchBoundary }) {
  // How many checklist steps are fully done; the next one shows as in-progress.
  const [done, setDone] = useState(0)
  useEffect(() => {
    const t1 = setTimeout(() => setDone(1), 800)
    const t2 = setTimeout(() => setDone(2), 1700)
    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
    }
  }, [])

  const chips = fenceChips(boundary)

  return (
    <div className="understand">
      <div className="understand__grid">
        <section className="understand__panel">
          <h3 className="understand__h">What you wrote</h3>
          {title.trim() ? <p className="understand__title">{title.trim()}</p> : null}
          <div className="understand__jd">{jd}</div>
          <p className="understand__note">
            I'm reading this to learn what to look for — you'll see and can correct every qualification I set.
          </p>
        </section>

        <section className="understand__panel">
          <h3 className="understand__h">Planning the search</h3>
          {chips.length ? (
            <div className="understand__fence">
              <div className="understand__fence-cap">
                <Lock size={13} aria-hidden="true" /> Non-negotiables · enforced
              </div>
              <div className="understand__chips">
                {chips.map((chip) => (
                  <span key={chip} className="understand__chip">
                    {chip}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          <ul className="understand__check">
            {STEPS.map((label, index) => {
              const isDone = index < done
              const isActive = index === done
              return (
                <li key={label} className={`understand__item${isDone || isActive ? ' is-on' : ''}`}>
                  <span className={`understand__tick${isDone ? ' is-done' : ''}${isActive ? ' is-spin' : ''}`} aria-hidden="true">
                    {isDone ? <Check size={11} /> : null}
                  </span>
                  <span>
                    {label}
                    {isActive ? '…' : ''}
                  </span>
                </li>
              )
            })}
          </ul>
          <p className="understand__reading" aria-live="polite">
            Reading the role… this usually takes a minute or two.
          </p>
        </section>
      </div>
    </div>
  )
}

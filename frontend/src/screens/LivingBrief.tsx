import { useEffect, useMemo, useState } from 'react'
import type { IntakeIssue, IntakeResult } from '../models/intake'
import { pendingAskIssues, tellInsights } from '../models/intake'

type LivingBriefProps = {
  result: IntakeResult
  onAnswer: (issue: IntakeIssue, value: string, label: string) => void
  onSearch: () => void
  onEdit: () => void
  isAnswering: boolean
  isConfirming: boolean
}

function ProvenanceTag({ source }: { source: string | null }) {
  if (!source) return null
  const label = source === 'explicit' ? 'From JD' : 'AI interpretation'
  return <span className={`brief-provenance brief-provenance--${source}`}>{label}</span>
}

function TierTag({ tierSignal }: { tierSignal: string | null }) {
  if (!tierSignal) return null
  const labels: Record<string, string> = {
    required: 'Required',
    proportion_dominant: 'Primary focus',
    proportion_minor: 'Secondary focus',
    preferred: 'Preferred',
    future_direction: 'Future direction',
    contextual: 'Context',
    mentioned_alongside_required: 'Supporting',
  }
  return <span className="brief-provenance brief-provenance--tier">{labels[tierSignal] ?? tierSignal}</span>
}

function CapabilityList({ title, items }: { title: string; items: { value: string; tier_signal: string | null }[] }) {
  if (!items.length) return null
  return (
    <div className="brief-field">
      <span className="brief-field__label">{title}</span>
      <ul className="living-brief__capability-list">
        {items.map((item) => (
          <li key={item.value}>
            <span>{item.value}</span>
            <TierTag tierSignal={item.tier_signal} />
          </li>
        ))}
      </ul>
    </div>
  )
}

// Every other option is a plain, self-contained choice — this is the one
// value that needs a follow-up free-text answer rather than being usable as
// a label on its own (see backend/services/intake_reasoning.py's
// `detect_missing_location`).
const FREE_TEXT_OPTION_VALUE = 'specify_location'

export function LivingBrief({ result, onAnswer, onSearch, onEdit, isAnswering, isConfirming }: LivingBriefProps) {
  const { role_understanding: role, decision } = result
  const insights = useMemo(() => tellInsights(result), [result])
  const pending = useMemo(() => pendingAskIssues(result), [result])
  const nextIssue = pending[0] ?? null
  const isContradiction = Boolean(nextIssue?.injected_by_backstop)
  const canSearch = result.status === 'ready'
  const [freeTextDraft, setFreeTextDraft] = useState('')
  const [awaitingFreeText, setAwaitingFreeText] = useState(false)

  useEffect(() => {
    setAwaitingFreeText(false)
    setFreeTextDraft('')
  }, [nextIssue?.id])

  const experience = role.explicit_constraints.experience_minimum_years
    ? role.explicit_constraints.experience_maximum_years
      ? `${role.explicit_constraints.experience_minimum_years}–${role.explicit_constraints.experience_maximum_years} years`
      : `${role.explicit_constraints.experience_minimum_years}+ years`
    : null

  return (
    <div className="living-brief-wrap">
      <section className="brief-panel living-brief" aria-label="Living brief">
        {/* Original title vs AI interpretation — visually distinct, never merged */}
        <div className="brief-section living-brief__header">
          <p className="workspace__preview-label">Living brief</p>
          {role.posted_title ? (
            <div className="living-brief__posted-title-row">
              <span className="living-brief__posted-title-label">Original title</span>
              <span className="living-brief__posted-title">"{role.posted_title}"</span>
              <span className="brief-provenance brief-provenance--explicit">As posted</span>
            </div>
          ) : null}
          <p className="living-brief__interp-eyebrow">AI-derived candidate identity <span className="living-brief__interp-eyebrow-note">— not the posted title</span></p>
          <h2 className="living-brief__title">{role.primary_candidate_identity.value ?? 'Understanding this role…'}</h2>
        </div>

        {/* How we read this role — meaning only, never search mechanics */}
        {role.role_interpretation.value ? (
          <div className="brief-section living-brief__read-block">
            <h3 className="living-brief__section-title">How we read this role</h3>
            <p className="living-brief__interpretation">{role.role_interpretation.value}</p>
          </div>
        ) : null}

        <div className="brief-section brief-field-grid brief-field-grid--two">
          {role.seniority_scope.value ? (
            <div className="brief-field">
              <span className="brief-field__label">Seniority</span>
              <span>
                {role.seniority_scope.value} <ProvenanceTag source={role.seniority_scope.source} />
              </span>
            </div>
          ) : null}
          {experience ? (
            <div className="brief-field">
              <span className="brief-field__label">Experience</span>
              <span>{experience} <span className="brief-provenance brief-provenance--explicit">From JD</span></span>
            </div>
          ) : null}
          {role.explicit_constraints.location ? (
            <div className="brief-field">
              <span className="brief-field__label">Location</span>
              <span>{role.explicit_constraints.location}</span>
            </div>
          ) : null}
          {role.leadership_type.value && role.leadership_type.value !== 'none' ? (
            <div className="brief-field">
              <span className="brief-field__label">Leadership</span>
              <span>{role.leadership_type.value}</span>
            </div>
          ) : null}
        </div>

        {/* Technologies mentioned — purely factual inventory, never tiered */}
        {role.technologies_mentioned.length ? (
          <div className="brief-section">
            <h4 className="living-brief__section-title">Technologies mentioned</h4>
            <div className="tech-grid">
              {role.technologies_mentioned.map((group) => (
                <div key={group.category} className="tech-group">
                  <h5>{group.category}</h5>
                  <div className="tech-chips">
                    {group.items.map((item) => (
                      <span key={item} className="tech-chip">{item}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {/* What matters for this search — the interpretive, tiered view */}
        <div className="brief-section">
          <h4 className="living-brief__section-title">What matters for this search</h4>
          <div className="living-brief__tiers">
            <CapabilityList title="Core" items={role.core_capabilities} />
            <CapabilityList title="Supporting" items={role.supporting_capabilities} />
            <CapabilityList title="Differentiators" items={role.differentiators} />
          </div>
        </div>

        {insights.length ? (
          <div className="brief-section living-brief__insights">
            {insights.map((issue) => (
              <div key={issue.issue} className="living-brief__insight">
                <span className="living-brief__insight-label">Recruiter insight</span>
                <p>{issue.insight_text}</p>
              </div>
            ))}
          </div>
        ) : null}

        {decision.warnings.length ? (
          <div className="brief-section living-brief__warnings">
            {decision.warnings.map((warning) => (
              <div key={warning} className="living-brief__warning">
                <span aria-hidden="true">⚠</span>
                <p>{warning}</p>
              </div>
            ))}
          </div>
        ) : null}
      </section>

      {nextIssue ? (
        <section
          className={`brief-panel living-brief__decision${isContradiction ? ' living-brief__decision--contradiction' : ''}`}
          aria-label={isContradiction ? 'Contradiction to resolve' : 'Decision needed'}
        >
          <p className="living-brief__decision-label">
            <span aria-hidden="true">⚠</span> {isContradiction ? 'Contradiction to resolve' : 'One decision needs your input'}
          </p>
          <p className="living-brief__decision-question">{nextIssue.question}</p>
          {awaitingFreeText ? (
            <div className="living-brief__free-text">
              <input
                type="text"
                className="brief-input"
                value={freeTextDraft}
                onChange={(event) => setFreeTextDraft(event.target.value)}
                placeholder="e.g. Austin, TX"
                autoFocus
                aria-label="Location"
              />
              <button
                type="button"
                className="workspace__parse"
                disabled={isAnswering || !freeTextDraft.trim()}
                onClick={() => {
                  onAnswer(nextIssue, freeTextDraft.trim(), freeTextDraft.trim())
                  setAwaitingFreeText(false)
                  setFreeTextDraft('')
                }}
              >
                Confirm
              </button>
            </div>
          ) : (
            <div className="brief-segmented" role="radiogroup" aria-label={nextIssue.question ?? undefined}>
              {nextIssue.options.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className="brief-segmented__option"
                  disabled={isAnswering}
                  onClick={() => {
                    if (option.value === FREE_TEXT_OPTION_VALUE) {
                      setAwaitingFreeText(true)
                      return
                    }
                    onAnswer(nextIssue, option.value, option.label)
                  }}
                >
                  {option.label}
                </button>
              ))}
            </div>
          )}
        </section>
      ) : (
        <section className="brief-panel living-brief__ready">
          <p className="living-brief__ready-text">Nothing else needs clarification before searching.</p>
          <div className="brief-actions">
            <button type="button" className="brief-back" onClick={onEdit}>
              Edit brief
            </button>
            <button
              type="button"
              className={`workspace__parse${isConfirming ? ' workspace__parse--busy' : ''}`}
              onClick={onSearch}
              disabled={!canSearch || isConfirming}
            >
              {isConfirming ? (
                <>
                  <span className="workspace__spinner" aria-hidden="true" />
                  <span>Preparing search…</span>
                </>
              ) : (
                <span>Search candidates</span>
              )}
            </button>
          </div>
        </section>
      )}
    </div>
  )
}

// The Living Brief: "here is how I understand the role", in one column, in a fixed order:
//   1 Header  2 Decision card  3 How I read this role  4 Boundary  5 Level  6 Requirements  7 Technologies mentioned
//   8 Recruiter notes  9 Warnings and limitations  10 Confirmation  11 Adjust before searching
// Every claim carries where it came from (Stated in JD / Inferred / Confirmed by you / Warning / System limitation).
import { useState } from 'react'
import { AlertTriangle, Check } from 'lucide-react'
import { BoundaryEditor } from '../components/BoundaryEditor'
import type { IntakeIssue, IntakeResult, Reconciliation } from '../models/intake'
import { offeredDecisions } from '../models/intake'
import {
  PROVENANCE_LABEL,
  fieldProvenance,
  readyStatus,
  requirementGroups,
  titleView,
  type ProvenanceKind,
  type RequirementTier,
} from '../models/livingBrief'
import type { SearchBoundary } from '../models/searchBoundary'
import type { SearchBrief } from '../models/searchBrief'
import '../components/LivingBrief.css'

type FieldChange = (path: string, updater: (current: SearchBrief) => SearchBrief) => void


// The tier a requirement sits in → the token the backend retier expects.
const TIER_TOKEN: Record<RequirementTier, string> = { core: 'core', supporting: 'supporting', preferred: 'differentiator' }
const TIER_CHOICES: Array<{ value: string; label: string }> = [
  { value: 'core', label: 'Core' },
  { value: 'supporting', label: 'Supporting' },
  { value: 'differentiator', label: 'Differentiator' },
]

const TAG_HINT: Record<ProvenanceKind, string> = {
  stated: 'The job description says this.',
  inferred: 'RecruiterAI concluded this. The job description does not say it outright.',
  confirmed: 'You answered a question that set this.',
  hm: 'The hiring manager raised this. It is not in the published JD.',
  warning: 'Something argues against the brief as written.',
  limitation: 'The search cannot enforce this.',
}

export function ProvenanceTag({ kind }: { kind: ProvenanceKind | null }) {
  if (!kind) return null
  return (
    <span className={`lb-tag lb-tag--${kind}`} title={TAG_HINT[kind]}>
      {PROVENANCE_LABEL[kind]}
    </span>
  )
}

type LivingBriefProps = {
  result: IntakeResult
  /** Present only when an HM brief was supplied; used to label HM-surfaced requirements correctly. */
  reconciliation?: Reconciliation | null
  boundary: SearchBoundary
  /** The "Adjust before searching" panel's working copy. */
  brief: SearchBrief
  onChangeBrief: FieldChange
  onAnswer: (issue: IntakeIssue, value: string, label: string) => void
  /** Option A editable brief: the recruiter moves a requirement between tiers. The
   * full {requirement: tier} assignment is sent, applied over the original read. */
  onRetier: (assignments: Record<string, string>) => void
  isAnswering: boolean
  onApplyBoundary: (boundary: SearchBoundary) => Promise<void>
  onSearch: (campaignDays?: 1 | 3) => void
  isSearching: boolean
  /** Why the last attempt to search was refused, in plain sentences. */
  searchErrors?: string[]
}

function DecisionCard({ issue, onAnswer, isAnswering, onReconsider }: { issue: IntakeIssue; onAnswer: LivingBriefProps['onAnswer']; isAnswering: boolean; onReconsider: () => void }) {
  const contradiction = Boolean(issue.injected_by_backstop && issue.backstop_category !== 'location_boundary_conflict')
  return (
    <section className={`lb-card lb-decision${contradiction ? ' lb-decision--contradiction' : ''}`} aria-label={contradiction ? 'Contradiction to resolve' : 'Decision needed'}>
      <p className="lb-decision__label">
        <AlertTriangle size={14} aria-hidden="true" /> {contradiction ? 'Contradiction to resolve' : 'One decision needs your input'}
      </p>
      <p className="lb-decision__question">{issue.question}</p>
      <div className="lb-options" role="group" aria-label={issue.question ?? 'Options'}>
        {issue.options.map((option) => (
          <button
            key={option.value}
            type="button"
            className="lb-button"
            disabled={isAnswering}
            onClick={() => (option.value === 'recruiter_will_clarify' ? onReconsider() : onAnswer(issue, option.value, option.label))}
          >
            {option.label}
          </button>
        ))}
      </div>
      {issue.options.length === 2 && issue.consequence_if_answer_a && issue.consequence_if_answer_b ? (
        <ul className="lb-decision__why">
          <li>
            <strong>{issue.options[0].label}:</strong> {issue.consequence_if_answer_a}
          </li>
          <li>
            <strong>{issue.options[1].label}:</strong> {issue.consequence_if_answer_b}
          </li>
        </ul>
      ) : null}
    </section>
  )
}

export function LivingBrief({ result, reconciliation, boundary, onAnswer, onRetier, isAnswering, onApplyBoundary, onSearch, isSearching, searchErrors = [] }: LivingBriefProps) {
  const [campaignDays, setCampaignDays] = useState<1 | 3>(1)
  const [boundaryOpen, setBoundaryOpen] = useState(false)
  const role = result.role_understanding
  const title = titleView(result)
  const status = readyStatus(result, boundary)
  const nextQuestion = status.questions[0] ?? null
  const offers = offeredDecisions(result)
  const groups = requirementGroups(result, reconciliation)
  const warnings = result.decision.warnings
  const limitations = result.decision.limitations ?? []
  const zeroCore = groups[0].items.length === 0
  const provisional = status.state === 'draft'

  // Move a requirement between Core / Supporting / Differentiator. We send the FULL
  // current assignment (applied over the original read), so the map is self-consistent.
  const changeTier = (text: string, tier: string) => {
    const assignments: Record<string, string> = {}
    for (const group of groups) for (const item of group.items) assignments[item.text] = TIER_TOKEN[group.tier]
    assignments[text] = tier
    onRetier(assignments)
  }

  return (
    <div className={`lb${provisional ? ' lb--draft' : ''}`}>
      {/* 1 Header */}
      <header className="lb-header">
        <div className="lb-header__row">
          <p className="lb-eyebrow">Search brief</p>
          <span className={`lb-state lb-state--${status.state}`}>{provisional ? 'Draft' : 'Ready to search'}</span>
        </div>
        {title.posted ? (
          <div className="lb-title-block">
            <p className="lb-label">Posted title</p>
            <h2 className="lb-title">{title.posted}</h2>
            <p className="lb-note-line">{title.postedNote}</p>
          </div>
        ) : null}
        {title.identity && (title.identityDiffers || !title.posted) ? (
          <div className="lb-title-block">
            <p className="lb-label">
              Candidate identity <ProvenanceTag kind={title.identityProvenance} />
            </p>
            <p className="lb-identity">{title.identity}</p>
            {title.identityDiffers ? (
              <p className="lb-note-line">
                Searched for instead of the posted title{title.identityReason ? `, because “${title.identityReason}”` : ''}.
              </p>
            ) : null}
          </div>
        ) : null}
        <p className="lb-company">
          Hiring company <strong>{boundary.hiring_company}</strong>
        </p>
      </header>

      {/* 2 Decision card */}
      {nextQuestion ? (
        <DecisionCard issue={nextQuestion} onAnswer={onAnswer} isAnswering={isAnswering} onReconsider={() => setBoundaryOpen(true)} />
      ) : null}
      {status.questions.length > 1 ? (
        <p className="lb-more">
          {status.questions.length - 1} more decision{status.questions.length - 1 === 1 ? '' : 's'} after this one.
        </p>
      ) : null}

      {/* Optional refinements — answerable, but never block Search. */}
      {offers.length ? (
        <section className="lb-offers" aria-label="Optional refinements">
          <p className="lb-offers__lead">Refine the search (optional)</p>
          {offers.map((issue) => (
            <DecisionCard key={issue.id ?? issue.issue} issue={issue} onAnswer={onAnswer} isAnswering={isAnswering} onReconsider={() => setBoundaryOpen(true)} />
          ))}
        </section>
      ) : null}

      {/* 3 How I read this role */}
      {role.role_interpretation.value ? (
        <section className="lb-section" aria-labelledby="lb-read">
          <h3 id="lb-read" className="lb-heading">
            How I read this role <ProvenanceTag kind={fieldProvenance(role.role_interpretation)} />
          </h3>
          <p className="lb-prose">{role.role_interpretation.value}</p>
        </section>
      ) : null}

      {/* Requirements */}
      <section className="lb-section" aria-labelledby="lb-requirements">
        <h3 id="lb-requirements" className="lb-heading">
          Requirements
        </h3>
        {zeroCore ? <p className="lb-muted">No core requirements were identified. The search can still run.</p> : null}
        {groups.map((group) =>
          group.items.length ? (
            <div key={group.tier} className="lb-tier">
              <h4 className="lb-subheading">
                {group.label} <span className="lb-count">{group.items.length}</span>
              </h4>
              <ul className="lb-list">
                {group.items.map((item) => (
                  <li key={item.text} className="lb-req" title={item.evidence ?? undefined}>
                    <span className="lb-req__text">{item.text}</span>
                    <span className="lb-req__meta">
                      <ProvenanceTag kind={item.provenance} />
                      <select
                        className="lb-tier"
                        aria-label={`Tier for ${item.text}`}
                        value={TIER_TOKEN[group.tier]}
                        disabled={isAnswering}
                        onClick={(event) => event.stopPropagation()}
                        onChange={(event) => changeTier(item.text, event.target.value)}
                      >
                        {TIER_CHOICES.map((choice) => (
                          <option key={choice.value} value={choice.value}>
                            {choice.label}
                          </option>
                        ))}
                      </select>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null,
        )}
      </section>

      {/* Exclusions — makes Tighten-to-track / company excludes visible (previously
          applied silently). "current: X" means not currently at X. */}
      {role.explicit_constraints.exclusions.length ? (
        <section className="lb-section" aria-labelledby="lb-exclusions">
          <h3 id="lb-exclusions" className="lb-heading">Excluding</h3>
          <div className="lb-chips">
            {role.explicit_constraints.exclusions.map((item) => (
              <span key={item} className="lb-chip">{item}</span>
            ))}
          </div>
        </section>
      ) : null}

      {/* Warnings and limitations */}
      {warnings.length || limitations.length > 1 ? (
        <section className="lb-section" aria-labelledby="lb-warnings">
          <h3 id="lb-warnings" className="lb-heading">
            Warnings and limitations
          </h3>
          <ul className="lb-notes">
            {warnings.map((warning) => (
              <li key={warning}>
                <ProvenanceTag kind="warning" /> {warning}
              </li>
            ))}
            {limitations.slice(1).map((limitation) => (
              <li key={limitation}>
                <ProvenanceTag kind="limitation" /> {limitation}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* Search boundary + confirm — one section now. The hard limits ARE what will be
          searched, so the boundary and the old "this is what I'll search for" are folded together. */}
      <section className={`lb-card lb-confirm lb-confirm--${status.state}`} id="lb-confirm" aria-labelledby="lb-boundary">
        <h3 id="lb-boundary" className="lb-heading">
          Search boundary <ProvenanceTag kind="confirmed" />
        </h3>
        <p className="lb-muted lb-confirm__hint">The hard limits, enforced at search time — only people inside them are ever pulled.</p>
        <BoundaryEditor boundary={boundary} onApply={onApplyBoundary} limitation={limitations[0] ?? null} open={boundaryOpen} onOpenChange={setBoundaryOpen} />

        {provisional ? (
          <div className="lb-confirm__state">
            <p className="lb-confirm__title">Not ready to search yet</p>
            <ul className="lb-notes">
              {status.blockers.map((blocker) => (
                <li key={blocker}>{blocker}</li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="lb-muted lb-confirm__ready">
            <Check size={15} aria-hidden="true" /> {result.decision.stop_reasoning ? `I don't need to ask anything else. ${result.decision.stop_reasoning}` : "I don't need to ask anything else."}
          </p>
        )}

        {searchErrors.length ? (
          <ul className="lb-errors" role="alert">
            {searchErrors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        ) : null}
        <label className="lb-campaign-choice">
          <span>Campaign length</span>
          <select value={campaignDays} onChange={(event) => setCampaignDays(Number(event.target.value) as 1 | 3)} disabled={isSearching}>
            <option value={1}>24 hours</option>
            <option value={3}>3 days</option>
          </select>
          <small>Checks for new candidates every 6 hours, within your 6-credit campaign budget.</small>
        </label>
        <button type="button" className="lb-button lb-button--primary lb-search" onClick={() => onSearch(campaignDays)} disabled={provisional || isSearching} title={provisional ? status.blockers.join(' ') : undefined}>
          {isSearching ? 'Searching the market…' : 'Search'}
        </button>
        {provisional && !isSearching ? <p className="lb-search-hint" role="note">Search is unavailable: {status.blockers.join(' ')}</p> : null}
      </section>
    </div>
  )
}

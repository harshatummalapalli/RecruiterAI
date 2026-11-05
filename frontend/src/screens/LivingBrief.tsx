// The Living Brief: "here is how I understand the role", in one column, in a fixed order:
//   1 Header  2 Decision card  3 How I read this role  4 Boundary  5 Level  6 Requirements  7 Technologies mentioned
//   8 Recruiter notes  9 Warnings and limitations  10 Confirmation  11 Adjust before searching
// Every claim carries where it came from (Stated in JD / Inferred / Confirmed by you / Warning / System limitation).
import { useState } from 'react'
import { AlertTriangle, Check } from 'lucide-react'
import { BoundaryEditor } from '../components/BoundaryEditor'
import type { IntakeIssue, IntakeResult } from '../models/intake'
import { offeredDecisions } from '../models/intake'
import {
  PROVENANCE_LABEL,
  confirmationSummary,
  fieldProvenance,
  readyStatus,
  requirementGroups,
  titleView,
  type ProvenanceKind,
} from '../models/livingBrief'
import type { SearchBoundary } from '../models/searchBoundary'
import type { SearchBrief } from '../models/searchBrief'
import '../components/LivingBrief.css'

type FieldChange = (path: string, updater: (current: SearchBrief) => SearchBrief) => void


const TAG_HINT: Record<ProvenanceKind, string> = {
  stated: 'The job description says this.',
  inferred: 'RecruiterAI concluded this. The job description does not say it outright.',
  confirmed: 'You answered a question that set this.',
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
  onSearch: () => void
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

export function LivingBrief({ result, boundary, brief, onAnswer, isAnswering, onApplyBoundary, onSearch, isSearching, searchErrors = [] }: LivingBriefProps) {
  const [boundaryOpen, setBoundaryOpen] = useState(false)
  const role = result.role_understanding
  const title = titleView(result)
  const status = readyStatus(result, boundary)
  const nextQuestion = status.questions[0] ?? null
  const offers = offeredDecisions(result)
  const groups = requirementGroups(result)
  const warnings = result.decision.warnings
  const limitations = result.decision.limitations ?? []
  const summary = status.state === 'ready' ? confirmationSummary(result, boundary, brief) : []
  const zeroCore = groups[0].items.length === 0
  const provisional = status.state === 'draft'

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
                  <li key={item.text} title={item.evidence ?? undefined}>
                    <span>{item.text}</span>
                    <ProvenanceTag kind={item.provenance} />
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
          <ul className="lb-list">
            {role.explicit_constraints.exclusions.map((item) => (
              <li key={item}><span>{item}</span></li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* Search boundary — moved here (after Requirements/Technologies, before Notes) to follow the approved
          visual ordering; still the same BoundaryEditor, same edit/confirm behavior, unchanged. */}
      <section className="lb-section" aria-labelledby="lb-boundary">
        <h3 id="lb-boundary" className="lb-heading">
          Search boundary <ProvenanceTag kind="confirmed" />
        </h3>
        <BoundaryEditor boundary={boundary} onApply={onApplyBoundary} limitation={limitations[0] ?? null} open={boundaryOpen} onOpenChange={setBoundaryOpen} />
      </section>

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

      {/* 10 Confirmation */}
      <section className={`lb-card lb-confirm lb-confirm--${status.state}`} aria-labelledby="lb-confirm">
        {provisional ? (
          <>
            <h3 id="lb-confirm" className="lb-heading">
              Not ready to search yet
            </h3>
            <ul className="lb-notes">
              {status.blockers.map((blocker) => (
                <li key={blocker}>{blocker}</li>
              ))}
            </ul>
          </>
        ) : (
          <>
            <h3 id="lb-confirm" className="lb-heading">
              <Check size={15} aria-hidden="true" /> This is what I will search for
            </h3>
            <dl className="lb-facts">
              {summary.map((line) => (
                <div key={line.label} className="lb-facts__row">
                  <dt>{line.label}</dt>
                  <dd>{line.value}</dd>
                </div>
              ))}
            </dl>
            <p className="lb-muted">{result.decision.stop_reasoning ? `I don't need to ask anything else. ${result.decision.stop_reasoning}` : "I don't need to ask anything else."}</p>
          </>
        )}
        {searchErrors.length ? (
          <ul className="lb-errors" role="alert">
            {searchErrors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        ) : null}
        <button type="button" className="lb-button lb-button--primary lb-search" onClick={onSearch} disabled={provisional || isSearching}>
          {isSearching ? 'Searching the market…' : 'Search'}
        </button>
      </section>
    </div>
  )
}

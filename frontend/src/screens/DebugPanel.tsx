// Developer-only debugging tool for the Recruiter Intelligence Layer and
// the search pipeline. Never renders outside a dev build (import.meta.env.DEV)
// — this must never appear in production. Every value shown is the real,
// live value currently in play: no mock data, no summarized/rounded
// approximations. This exists so hundreds of real JDs can be sanity-checked
// against what the pipeline is actually doing, end to end.

import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { buildRecruiterIntent } from '../intelligence/recruiterIntent'
import type { SearchBrief } from '../models/searchBrief'
import type { SearchResponse } from '../types'

type DebugPanelProps = {
  jdText: string
  brief: SearchBrief
  searchResponse: SearchResponse | null
}

function DebugSection({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="debug-panel__section">
      <h4>{title}</h4>
      <pre>{JSON.stringify(value, null, 2) ?? 'null'}</pre>
    </div>
  )
}

export function DebugPanel({ jdText, brief, searchResponse }: DebugPanelProps) {
  const [expanded, setExpanded] = useState(false)
  const intent = useMemo(() => buildRecruiterIntent(jdText), [jdText])

  // Belt-and-suspenders: even if this component were somehow imported into
  // a production bundle, it renders nothing outside a dev build.
  if (!import.meta.env.DEV) {
    return null
  }

  const debug = searchResponse?.debug ?? null

  return (
    <div className="debug-panel">
      <button type="button" className="debug-panel__toggle" onClick={() => setExpanded((current) => !current)}>
        {expanded ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
        Recruiter Intelligence
        <span className="debug-panel__badge">dev only</span>
      </button>

      {expanded ? (
        <div className="debug-panel__body">
          <DebugSection title="Recruiter Intent" value={intent} />
          <DebugSection title="Role Classification" value={intent.roleClassification} />
          <DebugSection title="Technology Analysis" value={intent.technologyProfile} />
          <DebugSection title="Primary Technology" value={brief.skills.primaryTechnology} />
          <DebugSection title="Equivalent Titles" value={intent.titleProfile.equivalentTitles} />
          <DebugSection title="Past Titles" value={intent.titleProfile.pastTitles} />
          <DebugSection title="Experience Resolution" value={intent.experienceStrategy} />
          <DebugSection title="Location Resolution" value={intent.locationStrategy} />
          <DebugSection title="Validation Rules Fired" value={intent.ambiguities} />
          <DebugSection title="Clarification Questions" value={intent.clarificationsRequired} />
          <DebugSection title="Final Search Brief" value={brief} />

          {debug ? (
            <>
              <DebugSection title="Generated Provider Query" value={debug.generated_provider_query} />
              <DebugSection title="Final CrustData Payload" value={debug.final_provider_payload} />
              <DebugSection title="Capability Warnings (dropped/unsupported filters)" value={debug.capability_warnings} />
              <DebugSection title="Candidates Returned" value={debug.candidates_returned} />
              <DebugSection title="Execution Time (ms)" value={debug.execution_time_ms} />
              <DebugSection title="Search ID" value={debug.search_id} />
            </>
          ) : (
            <p className="debug-panel__empty">
              Run a search to see the generated provider query, the final CrustData payload, and execution stats.
            </p>
          )}
        </div>
      ) : null}
    </div>
  )
}

// Stage 7 of the Recruiter Reasoning Pipeline: Clarification Generation.
//
// Turns Constraint Validation findings into the small set of questions the
// recruiter actually sees. Two rules govern this:
//   1. Prefer one high-value question over several low-value ones — once a
//      high-severity finding exists, low-severity findings (the kind that
//      are "nice to resolve" but don't materially change the search) are
//      dropped rather than padding out the list.
//   2. Never exceed the UI's structured-review ceiling (5) regardless.
//
// This stage never looks at the raw JD — only at findings already derived
// from Recruiter Intent's section outputs, per the "clarifications come
// from intent, not the JD" rule.

import type { ClarificationQuestion, Severity, ValidationFinding } from './types'

const MAX_QUESTIONS = 5
const SEVERITY_RANK: Record<Severity, number> = { high: 3, medium: 2, low: 1 }

export function generateClarifications(findings: ValidationFinding[]): ClarificationQuestion[] {
  const actionable = findings.filter((finding): finding is ValidationFinding & { question: ClarificationQuestion } => finding.question !== null)

  if (actionable.length === 0) {
    return []
  }

  const highestRank = Math.max(...actionable.map((finding) => SEVERITY_RANK[finding.severity]))
  const kept = actionable
    .filter((finding) => SEVERITY_RANK[finding.severity] >= highestRank - 1)
    .sort((a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity])

  return kept.slice(0, MAX_QUESTIONS).map((finding) => finding.question)
}

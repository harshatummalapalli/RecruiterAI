// Stage 1 of the Recruiter Reasoning Pipeline: Role Classification.
//
// Every JD is classified into a role family before anything else runs, so
// later stages (title reasoning, technology understanding) can reason with
// role-appropriate context instead of treating every JD identically.
//
// This stage does not embed recruiter assumptions itself — it asks
// knowledge/roleFamilies.ts what's known about each role family and scores
// how well the JD matches. Classification is evidence-based: each family
// accumulates points from independent signals (does the title say it
// directly? does the JD body mention it? does the tech stack match? do the
// responsibilities match?) — never a single keyword hit. Adding a new role
// family is a data change in knowledge/roleFamilies.ts; this file never
// needs to change for it.

import { ROLE_FAMILY_KNOWLEDGE } from './knowledge/roleFamilies'
import type { RoleClassification, RoleFamily } from './types'

const TITLE_MATCH_WEIGHT = 3
const BODY_MATCH_WEIGHT = 1
const TECHNOLOGY_MATCH_WEIGHT = 2
const RESPONSIBILITY_MATCH_WEIGHT = 2
const MAX_ATTAINABLE_SCORE = TITLE_MATCH_WEIGHT + TECHNOLOGY_MATCH_WEIGHT + RESPONSIBILITY_MATCH_WEIGHT

export function classifyRole(titleText: string, bodyText: string): RoleClassification {
  const combined = `${titleText}\n${bodyText}`

  let best: { family: RoleFamily; score: number; evidence: string[] } | null = null

  for (const knowledge of ROLE_FAMILY_KNOWLEDGE) {
    const { titlePattern, technologyPattern, responsibilityPattern } = knowledge.detectionSignals
    let score = 0
    const evidence: string[] = []

    if (titlePattern.test(titleText)) {
      score += TITLE_MATCH_WEIGHT
      evidence.push('title names the role directly')
    } else if (titlePattern.test(combined)) {
      score += BODY_MATCH_WEIGHT
      evidence.push('role phrase appears in the JD body')
    }

    if (technologyPattern?.test(combined)) {
      score += TECHNOLOGY_MATCH_WEIGHT
      evidence.push('technology stack matches this role family')
    }

    if (responsibilityPattern?.test(combined)) {
      score += RESPONSIBILITY_MATCH_WEIGHT
      evidence.push('responsibilities match this role family')
    }

    if (score > 0 && (!best || score > best.score)) {
      best = { family: knowledge.id, score, evidence }
    }
  }

  if (!best) {
    return { roleFamily: 'Unclassified', specialization: null, evidence: [], confidence: 0 }
  }

  return {
    roleFamily: best.family,
    specialization: null,
    evidence: best.evidence,
    confidence: Math.min(1, best.score / MAX_ATTAINABLE_SCORE),
  }
}

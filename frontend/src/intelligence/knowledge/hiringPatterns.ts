// Recruiter Knowledge Engine — Hiring Patterns.
//
// Recruiter guidance, not rules. Nothing in this module filters, blocks, or
// validates anything — it's surfaced as advisory text on Recruiter Intent
// (`hiringGuidance`) for a matched role family and/or seniority level, the
// same way an experienced recruiter might mention "these usually come from
// backend" in passing. It never changes what the Search Brief actually
// requires.

import type { RoleFamily } from '../types'

type RoleFamilyGuidance = { roleFamily: RoleFamily; guidance: string }
type SeniorityGuidance = { seniority: string; guidance: string }

const ROLE_FAMILY_GUIDANCE: RoleFamilyGuidance[] = [
  { roleFamily: 'AI Software Engineer', guidance: 'AI Engineers usually require backend experience.' },
  { roleFamily: 'Applied AI Engineer', guidance: 'AI Engineers usually require backend experience.' },
  { roleFamily: 'Platform Engineer', guidance: 'Platform Engineers commonly come from backend or infrastructure.' },
  { roleFamily: 'ML Engineer', guidance: 'ML Engineers often overlap with Data Scientists on modeling background.' },
  { roleFamily: 'DevOps Engineer', guidance: 'DevOps Engineers commonly come from backend or infrastructure.' },
  { roleFamily: 'Engineering Manager', guidance: 'Engineering Managers are usually hired from senior IC ranks within the same domain.' },
]

const SENIORITY_GUIDANCE: SeniorityGuidance[] = [
  { seniority: 'Staff', guidance: 'Staff Engineers are usually architecture-focused.' },
  { seniority: 'Principal', guidance: 'Principal Engineers often overlap with Architects.' },
]

function normalize(value: string): string {
  return value.trim().toLowerCase()
}

/** Advisory guidance for a role family and/or seniority level — informs,
 * never enforces. Returns an empty list rather than guessing when nothing
 * in the knowledge base applies. */
export function guidanceFor(roleFamily: RoleFamily, seniority: string | null): string[] {
  const guidance: string[] = []

  for (const entry of ROLE_FAMILY_GUIDANCE) {
    if (entry.roleFamily === roleFamily) {
      guidance.push(entry.guidance)
    }
  }

  if (seniority) {
    for (const entry of SENIORITY_GUIDANCE) {
      if (normalize(entry.seniority) === normalize(seniority)) {
        guidance.push(entry.guidance)
      }
    }
  }

  return guidance
}

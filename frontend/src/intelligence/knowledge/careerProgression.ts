// Recruiter Knowledge Engine — Career Progression.
//
// The common IC title ladder, kept separate from the management track —
// they're different careers, not two points on the same line. This
// replaces the seniority list that used to live inline inside
// titleIntelligence.ts as an unexplained constant; here it's named,
// documented, and reusable by any reasoning stage that needs it.

export const IC_LADDER = ['Junior', 'Mid-level', 'Senior', 'Lead', 'Staff', 'Principal']

export const MANAGEMENT_LADDER = ['Engineering Manager', 'Senior Engineering Manager', 'Director of Engineering', 'VP of Engineering']

function ladderIndex(ladder: string[], level: string): number {
  return ladder.findIndex((entry) => entry.toLowerCase() === level.trim().toLowerCase())
}

/** One step down the IC ladder from `level`, or null if `level` isn't on it
 * or is already the first rung. */
export function stepDownIcLadder(level: string): string | null {
  const index = ladderIndex(IC_LADDER, level)
  return index > 0 ? IC_LADDER[index - 1] : null
}

/** One step up the IC ladder from `level`, or null if `level` isn't on it
 * or is already the last rung. */
export function stepUpIcLadder(level: string): string | null {
  const index = ladderIndex(IC_LADDER, level)
  return index >= 0 && index < IC_LADDER.length - 1 ? IC_LADDER[index + 1] : null
}

export function isManagementLevel(level: string): boolean {
  return ladderIndex(MANAGEMENT_LADDER, level) >= 0
}

// Release 3 workspace view model. A compression layer over the Release 2 evidence: every fact here is read from
// the ledger the backend already verified. Nothing is scored, ranked or generated. Pure functions, no React.

import type { DiscoveryCandidate, LedgerRow } from './discovery'

export type SectionKey = 'start' | 'worth' | 'thin' | 'unchecked' | 'preparing'

// Fixed rules, disclosed to the recruiter. Not tuned: section sizes are outcomes, not targets.
export const START_HERE_SHARE = 0.6

export const SECTION_ORDER: SectionKey[] = ['start', 'worth', 'thin', 'unchecked', 'preparing']

export const SECTION_COPY: Record<SectionKey, { title: string; basis: string }> = {
  start: { title: 'Start here', basis: 'Most of the core requirements are shown on their profile.' },
  worth: { title: 'Worth a look', basis: 'At least one core requirement is shown on their profile.' },
  thin: {
    title: 'Not much shown yet',
    basis: 'No core requirement beyond total years is shown. This is about the profile, not the person.',
  },
  unchecked: {
    title: 'Not checked against the brief',
    basis: 'The core requirements could not be checked against these profiles, so nothing is claimed either way.',
  },
  preparing: { title: 'Still being prepared', basis: 'Profiles being read. They move into a group once they are ready.' },
}

export type Dot = { label: string; shown: boolean }
export type ProofChip = { label: string; requirement: string; quote: string; source: string | null; described: boolean }
export type WatchChip = { key: 'floor' | 'level' | 'title' | 'other'; label: string }

export type CardFacts = {
  section: SectionKey
  /** One dot per NON-years core requirement in the brief, in the brief's order. The years requirement is never a dot. */
  dots: Dot[]
  /** The single deterministic line under the headline, or null while the profile is still being prepared. */
  why: string | null
  chips: ProofChip[]
  /** Concerns only: facts that argue against fit. Never missing information, never a gap. */
  watch: WatchChip[]
  /** Core requirements with no evidence on the profile ("not proven"), by name. */
  notProven: string[]
  /** The full concern sentences, for the expanded area. */
  concerns: string[]
  shown: number
  coreTotal: number
  described: number
}

const MAX_CHIPS = 3
const MAX_CHIP_CHARS = 44
const TIER_RANK: Record<LedgerRow['tier'], number> = { core: 0, supporting: 1, differentiator: 2 }

function stripLeadingMarks(text: string): string {
  return text.replace(/^[^\p{L}\p{N}]+/u, '').trim()
}

const STOPWORDS = new Set(['a', 'an', 'the', 'and', 'or', 'for', 'of', 'to', 'in', 'on', 'with', 'using', 'by', 'as', 'at', 'from', 'that', 'this', 'is', 'are', 'was', 'be'])

function words(text: string): string[] {
  return text.toLowerCase().match(/[\p{L}\p{N}][\p{L}\p{N}+#./-]*/gu) ?? []
}

function clip(label: string): string {
  if (label.length <= MAX_CHIP_CHARS) return label
  const cut = label.slice(0, MAX_CHIP_CHARS - 1)
  const atWord = cut.slice(0, Math.max(cut.lastIndexOf(' '), 12)).trimEnd()
  // Never end on a dangling connector ("… tools such as…").
  return `${atWord.replace(/(\s+(such as|as|and|or|for|of|to|in|with|the|a|an|on|by|using))+$/i, '')}…`
}

/** The brief's own wording for a requirement, without its lead-in ("Experience with", "3+ years of"). */
function requirementLabel(requirement: string): string {
  const core = requirement
    .replace(/[.\s]+$/, '')
    .replace(/^(\d+\+?\s*years?\s+of\s+)/i, '')
    .replace(/^(proven\s+|strong\s+|hands-on\s+)?(experience|familiarity|proficiency|exposure|expertise|knowledge|background)\s+(with|in|of|using|building|to)\s+/i, '')
  return clip(core.charAt(0).toUpperCase() + core.slice(1))
}

/** A label that is just the opening words of a long quote and says nothing about the requirement ("Write and"). */
function isWeakOpening(label: string, quote: string, requirement: string): boolean {
  const labelWords = words(label)
  if (labelWords.length === 0) return true
  const opensQuote = stripLeadingMarks(quote).toLowerCase().startsWith(label.toLowerCase()) && words(quote).length > labelWords.length
  if (!opensQuote) return false
  const stemOverlap = labelWords.some((word) => word.length >= 3 && !STOPWORDS.has(word) && words(requirement).some((other) => other.startsWith(word) || word.startsWith(other)))
  return STOPWORDS.has(labelWords[0]) || STOPWORDS.has(labelWords[labelWords.length - 1]) || !stemOverlap
}

/**
 * A short label for what the profile shows. The judge's `term` (a phrase verified to sit inside the quote) is used
 * when it reads as a real phrase. If it is missing, garbled or only the opening words of the quote, the brief's own
 * wording for the requirement is used instead. The quote itself is always shown in full under Proof.
 */
export function proofLabel(row: Pick<LedgerRow, 'term' | 'quote' | 'requirement'>): string | null {
  const quote = (row.quote ?? '').replace(/\s+/g, ' ').trim()
  if (!quote) return null
  const term = row.term ? stripLeadingMarks(row.term.replace(/\s+/g, ' ')) : ''
  const usable = term && quote.toLowerCase().includes(term.toLowerCase()) && !isWeakOpening(term, quote, row.requirement)
  const label = usable ? clip(term) : requirementLabel(row.requirement)
  return label || null
}

function coreRows(candidate: DiscoveryCandidate): LedgerRow[] {
  return candidate.ledger.find((group) => group.tier === 'core')?.rows ?? []
}

function proofChips(candidate: DiscoveryCandidate): ProofChip[] {
  const rows: Array<{ row: LedgerRow; order: number }> = []
  let order = 0
  for (const group of candidate.ledger) {
    for (const row of group.rows) {
      rows.push({ row, order: order++ })
    }
  }
  const usable = rows
    .filter(({ row }) => row.verdict === 'met' && !row.derived && row.quote)
    .sort((a, b) => TIER_RANK[a.row.tier] - TIER_RANK[b.row.tier] || Number(b.row.described) - Number(a.row.described) || a.order - b.order)

  const chips: ProofChip[] = []
  const seen = new Set<string>()
  for (const { row } of usable) {
    const label = proofLabel({ term: row.term, quote: row.quote, requirement: row.requirement })
    if (!label || seen.has(label.toLowerCase())) continue
    seen.add(label.toLowerCase())
    chips.push({ label, requirement: row.requirement, quote: (row.quote ?? '').replace(/^[-•\s]+/, ''), source: row.sourceLabel, described: row.described })
    if (chips.length === MAX_CHIPS) break
  }
  return chips
}

function watchChips(candidate: DiscoveryCandidate): WatchChip[] {
  const chips: WatchChip[] = []
  if (candidate.experienceFloor === false) chips.push({ key: 'floor', label: 'Under the years asked' })
  if (candidate.levelFit === 'above') chips.push({ key: 'level', label: 'Level may be above this role' })
  if (candidate.levelFit === 'below') chips.push({ key: 'level', label: 'Level may be below this role' })
  if (candidate.relevanceTier === 'tangential') chips.push({ key: 'title', label: 'Title differs from the role' })
  // A concern the backend raised that none of the above explains still deserves a flag, with its text in the expander.
  if (chips.length === 0 && candidate.potentialConcerns.length > 0) chips.push({ key: 'other', label: 'Concern noted' })
  return chips.slice(0, 2)
}

/**
 * The coverage statement. It counts the core requirements other than total years, and says so: "4 core requirements
 * shown" never reads as "4 of 4" when the years requirement is represented separately.
 */
function whyLine(shown: number, described: number, hasYears: boolean): string {
  if (shown === 0) {
    return hasYears ? 'Nothing beyond total years is shown on the profile.' : 'No core requirement is shown on the profile.'
  }
  const base = `${shown} core ${shown === 1 ? 'requirement' : 'requirements'} shown`
  return described > 0 ? `${base} · ${described} in described work` : base
}

export function sectionOf(candidate: DiscoveryCandidate): SectionKey {
  if (candidate.lifecycleState !== 'review_ready') return 'preparing'
  const core = coreRows(candidate)
  const nonYears = core.filter((row) => !row.derived)
  if (candidate.ledger.length === 0 || nonYears.length === 0) return 'unchecked'
  const shown = nonYears.filter((row) => row.verdict === 'met').length
  if (shown === 0) return 'thin'
  return shown / nonYears.length >= START_HERE_SHARE ? 'start' : 'worth'
}

export function cardFacts(candidate: DiscoveryCandidate): CardFacts {
  const section = sectionOf(candidate)
  const core = coreRows(candidate)
  const nonYears = core.filter((row) => !row.derived)
  const shown = nonYears.filter((row) => row.verdict === 'met').length
  const described = nonYears.filter((row) => row.described).length
  const hasYears = core.some((row) => row.derived)
  const checked = candidate.ledger.length > 0 && nonYears.length > 0

  let why: string | null
  if (section === 'preparing') why = null
  else if (!checked) why = 'Requirements were not checked against this profile'
  else why = whyLine(shown, described, hasYears)

  return {
    section,
    dots: nonYears.map((row) => ({ label: row.requirement, shown: row.verdict === 'met' })),
    why,
    chips: proofChips(candidate),
    watch: section === 'preparing' ? [] : watchChips(candidate),
    notProven: core.filter((row) => row.verdict !== 'met').map((row) => row.requirement.replace(/[.\s]+$/, '')),
    concerns: candidate.potentialConcerns,
    shown,
    coreTotal: nonYears.length,
    described,
  }
}

export type WorkspaceCandidate = { candidate: DiscoveryCandidate; facts: CardFacts }

export function buildWorkspaceCandidates(candidates: DiscoveryCandidate[]): WorkspaceCandidate[] {
  return candidates.map((candidate) => ({ candidate, facts: cardFacts(candidate) }))
}

/** Group once, keeping the order the search returned inside each group. Order inside a group is not a ranking. */
export function groupBySection(items: WorkspaceCandidate[]): Array<{ key: SectionKey; items: WorkspaceCandidate[] }> {
  return SECTION_ORDER.map((key) => ({ key, items: items.filter((item) => item.facts.section === key) })).filter((group) => group.items.length > 0)
}

/**
 * Keep a list order stable while a search is still filling in: candidates keep the place they first arrived in, new
 * ones are appended. The server may re-order its own list when the search finishes; the workspace does not follow.
 */
export function stableOrder(previous: string[], incoming: string[]): string[] {
  const known = new Set(previous)
  const kept = previous.filter((id) => incoming.includes(id))
  return [...kept, ...incoming.filter((id) => !known.has(id))]
}

// ---- Decisions and filter -------------------------------------------------------------------------------------

export type Decision = 'shortlist' | 'maybe' | 'reject'
export type FilterKey = 'all' | 'to_review' | 'shortlist' | 'maybe' | 'reject'

export const FILTERS: Array<{ key: FilterKey; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'to_review', label: 'To review' },
  { key: 'shortlist', label: 'Shortlisted' },
  { key: 'maybe', label: 'Maybe' },
  { key: 'reject', label: 'Rejected' },
]

export function normalizeDecision(value: string | undefined | null): Decision | undefined {
  return value === 'shortlist' || value === 'maybe' || value === 'reject' ? value : undefined
}

export function matchesFilter(filter: FilterKey, decision: Decision | undefined): boolean {
  if (filter === 'all') return true
  if (filter === 'to_review') return decision === undefined
  return decision === filter
}

export function filterCounts(ids: string[], decisions: Record<string, Decision | undefined>): Record<FilterKey, number> {
  const counts: Record<FilterKey, number> = { all: ids.length, to_review: 0, shortlist: 0, maybe: 0, reject: 0 }
  for (const id of ids) {
    const decision = decisions[id]
    if (decision === undefined) counts.to_review += 1
    else counts[decision] += 1
  }
  return counts
}

// ---- Funnel header --------------------------------------------------------------------------------------------

export type FunnelRaw = {
  in_scope?: number | null
  has_location_scope?: boolean
  retrieved?: number | null
  selected?: number | null
  read_in_depth?: number | null
  presented?: number | null
}

export function readFunnel(diagnostics: Record<string, unknown> | undefined): FunnelRaw | null {
  const funnel = diagnostics?.funnel
  return funnel && typeof funnel === 'object' ? (funnel as FunnelRaw) : null
}

function count(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/** "about 724,000": three significant figures at most, so a pool size never reads as a precise match count. */
export function approximateCount(value: number): string {
  if (value < 1000) return String(value)
  const magnitude = 10 ** (Math.floor(Math.log10(value)) - 2)
  return `about ${(Math.round(value / magnitude) * magnitude).toLocaleString('en-US')}`
}

export type FunnelCopy = {
  headline: string
  /** The area's size, only when a location boundary exists, and never called a match count. */
  scope: string | null
  /** Facts about the profiles that were retrieved but not read. */
  notRead: string | null
}

/** Facts from the stored search metadata only. No rationale is given for how the profiles were chosen. */
export function funnelCopy(funnel: FunnelRaw | null, admitted: number): FunnelCopy {
  const selected = count(funnel?.selected) ?? admitted
  const retrieved = count(funnel?.retrieved)
  const read = count(funnel?.read_in_depth)
  const inScope = count(funnel?.in_scope)

  let headline: string
  if (retrieved !== null && retrieved > selected) {
    headline =
      read === null || read === selected
        ? `${selected} profiles were selected from the ${retrieved} retrieved and read in full.`
        : `${selected} profiles were selected from the ${retrieved} retrieved. ${read} were read in full.`
  } else if (read !== null && read < selected) {
    headline = `${selected} profiles were retrieved. ${read} were read in full.`
  } else {
    headline = `${selected} profiles were retrieved and read in full.`
  }

  return {
    headline,
    scope:
      funnel?.has_location_scope && inScope !== null && inScope > 0
        ? `The search area holds ${approximateCount(inScope)} profiles. That is the size of the area, not the number of matches.`
        : null,
    notRead:
      retrieved !== null && retrieved > selected
        ? `The other ${retrieved - selected} retrieved profiles were not read in full, so nothing here says they lack evidence.`
        : null,
  }
}

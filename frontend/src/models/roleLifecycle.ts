// Role lifecycle: the single source of truth for a search's status, and the
// Active ↔ Completed split that keeps Home to live work only. Phase 1 is
// frontend-only — Close/Reopen and the 14-day auto-archive are derived here and
// remembered in localStorage; Phase 2 makes them a real backend status.
import type { SearchListItem } from '../types'

export type RoleStatus = 'draft' | 'searching' | 'paused' | 'complete'

const OVERRIDES_KEY = 'recruiterai:roleOverrides'
const AUTO_ARCHIVE_DAYS = 14
const DAY_MS = 86_400_000

/** A recruiter override of the automatic rule: Close → 'closed', Reopen → 'open'. */
type Override = { state: 'closed' | 'open'; at: string }
export type Overrides = Record<string, Override>

export function readOverrides(): Overrides {
  try {
    const raw = window.localStorage.getItem(OVERRIDES_KEY)
    return raw ? (JSON.parse(raw) as Overrides) : {}
  } catch {
    return {}
  }
}

function writeOverrides(next: Overrides): Overrides {
  try {
    window.localStorage.setItem(OVERRIDES_KEY, JSON.stringify(next))
  } catch {
    // Best-effort only — the split still works for this session from in-memory state.
  }
  return next
}

export function setOverride(current: Overrides, id: string, state: 'closed' | 'open'): Overrides {
  return writeOverrides({ ...current, [id]: { state, at: new Date().toISOString() } })
}

/** The one badge a card shows — role lifecycle only, never the pipeline's "complete". */
export function roleStatus(item: SearchListItem): RoleStatus {
  if (item.kind === 'draft') return 'draft'
  if (item.role_status === 'paused') return 'paused'
  if (item.role_status === 'searching') return 'searching'
  return 'complete' // role_status null = a finished one-shot search, not a live mandate
}

function lastActivity(item: SearchListItem, overrides: Overrides): number {
  const stamps = [item.updated_at, overrides[item.id]?.at]
    .filter(Boolean)
    .map((t) => new Date(t as string).getTime())
    .filter((n) => !Number.isNaN(n))
  return stamps.length ? Math.max(...stamps) : 0
}

/** Completed/archived = off Home. Manual Close wins; else finished one-shots and
 * roles idle ≥ 14 days auto-archive. An explicit Reopen keeps a role Active. */
export function isArchived(item: SearchListItem, overrides: Overrides, now: number = Date.now()): boolean {
  const ov = overrides[item.id]
  if (ov?.state === 'open') return false
  if (ov?.state === 'closed') return true
  if (item.kind === 'draft') return false
  if (roleStatus(item) === 'complete') return true
  const last = lastActivity(item, overrides)
  return last > 0 && now - last >= AUTO_ARCHIVE_DAYS * DAY_MS
}

export function partitionRoles(
  items: SearchListItem[],
  overrides: Overrides,
  now: number = Date.now(),
): { active: SearchListItem[]; completed: SearchListItem[] } {
  const active: SearchListItem[] = []
  const completed: SearchListItem[] = []
  for (const item of items) (isArchived(item, overrides, now) ? completed : active).push(item)
  return { active, completed }
}

/** The rail's quick-return list: the most recently touched Active roles. */
export function recentRoles(
  items: SearchListItem[],
  overrides: Overrides,
  limit = 4,
  now: number = Date.now(),
): SearchListItem[] {
  return partitionRoles(items, overrides, now)
    .active.slice()
    .sort((a, b) => lastActivity(b, overrides) - lastActivity(a, overrides))
    .slice(0, limit)
}

export type ActiveGroup = { key: 'review' | 'searching' | 'paused' | 'draft'; label: string; items: SearchListItem[] }

const GROUP_ORDER: Array<ActiveGroup['key']> = ['review', 'searching', 'paused', 'draft']
const GROUP_LABEL: Record<ActiveGroup['key'], string> = {
  review: 'Needs your review',
  searching: 'Searching',
  paused: 'Paused',
  draft: 'Drafts',
}

/** Active work, grouped by where attention is owed: review first, then live, paused, drafts. */
export function groupActive(items: SearchListItem[]): ActiveGroup[] {
  const buckets: Record<ActiveGroup['key'], SearchListItem[]> = { review: [], searching: [], paused: [], draft: [] }
  for (const item of items) {
    const status = roleStatus(item)
    if (status === 'draft') buckets.draft.push(item)
    else if ((item.to_review_count ?? 0) > 0) buckets.review.push(item)
    else if (status === 'paused') buckets.paused.push(item)
    else buckets.searching.push(item)
  }
  return GROUP_ORDER.filter((key) => buckets[key].length).map((key) => ({ key, label: GROUP_LABEL[key], items: buckets[key] }))
}

const GENERIC_TITLES = new Set(['job description', 'jd', 'untitled', ''])

/** Never let a raw-JD heading or a long sentence stand in as a role name. */
export function displayTitle(title: string): string {
  const trimmed = (title ?? '').trim()
  if (GENERIC_TITLES.has(trimmed.toLowerCase())) return 'Untitled search'
  return trimmed.length > 70 ? `${trimmed.slice(0, 67).trimEnd()}…` : trimmed
}

export function timeAgo(iso: string | null): string {
  if (!iso) return 'recently'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'recently'
  const seconds = Math.max(0, (Date.now() - then) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days === 1) return 'yesterday'
  if (days < 7) return `${days}d ago`
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function draftStage(status: string | null): string {
  if (status === 'ready') return 'Brief ready to confirm'
  if (status === 'needs_clarification') return 'Clarifying the role'
  return 'Finish the brief'
}

/** The one honest activity line under a card — count-derived, never the pipeline flag. */
export function activitySummary(item: SearchListItem): { text: string; emphasis: boolean } {
  const status = roleStatus(item)
  if (status === 'draft') return { text: draftStage(item.status), emphasis: false }
  if ((item.to_review_count ?? 0) > 0) return { text: `${item.to_review_count} to review`, emphasis: true }
  if (item.new_count > 0) return { text: `${item.new_count} new`, emphasis: true }
  if (status === 'paused') return { text: 'Paused', emphasis: false }
  return { text: `Updated ${timeAgo(item.updated_at)}`, emphasis: false }
}

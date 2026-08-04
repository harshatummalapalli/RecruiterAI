import { useEffect, useMemo, useState } from 'react'
import type { Candidate, SearchHistoryEntry, SearchIntent, SearchResponse } from '../types'
import {
  buildAnalytics,
  buildParsedIntentSummary,
  buildSearchSummary,
  createHistoryEntry,
  defaultIntent,
  serializeIntentForSearch,
  exportCandidateResults,
  getCandidateKey,
  getProviderAvailability,
  parseJobDescription,
  runCandidateSearch,
  validateIntent,
  type BusyState,
  type Notice,
  type RecruiterAction,
  type SearchSummary,
} from '../services/recruiterWorkflow'

type CandidateWorkspaceState = {
  shortlist: boolean
  reviewed: boolean
  rejected: boolean
  notes: Array<{ id: string; text: string; createdAt: string; updatedAt?: string; pinned?: boolean }>
  resumes: Array<{ name: string; uploadedAt: string; size?: string; version?: string; status?: string }>
  activity: Array<{ id: string; type: string; label: string; detail: string; timestamp: string }>
  exported: boolean
  status: string
}

const buildActivityEntry = (type: string, label: string, detail: string) => ({
  id: `${type}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
  type,
  label,
  detail,
  timestamp: new Date().toLocaleString(),
})

export function useRecruiterWorkbench() {
  const [jdText, setJdText] = useState('We are hiring a Senior Software Engineer with Python, FastAPI, AWS, and cloud-native experience for a hybrid role in New York.')
  const [intent, setIntent] = useState<SearchIntent>(defaultIntent)
  const [busyState, setBusyState] = useState<BusyState>(null)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null)
  const [selectedCandidateKey, setSelectedCandidateKey] = useState<string | null>(null)
  const [hasParsed, setHasParsed] = useState(false)
  const [lastParsedJd, setLastParsedJd] = useState('')
  const [validationErrors, setValidationErrors] = useState<string[]>([])
  const [providerAvailable, setProviderAvailable] = useState(true)
  const [searchSummary, setSearchSummary] = useState<SearchSummary | null>(null)
  const [analytics, setAnalytics] = useState<ReturnType<typeof buildAnalytics> | null>(null)
  const [demoMode, setDemoMode] = useState(false)
  const [comparisonKeys] = useState<string[]>([])
  const [history, setHistory] = useState<SearchHistoryEntry[]>([])

  const parsedIntentSummary = useMemo(() => buildParsedIntentSummary(intent), [intent])
  const hasPendingParse = hasParsed && jdText.trim() !== lastParsedJd.trim()

  useEffect(() => {
    const checkProviderAvailability = async () => {
      const availability = await getProviderAvailability()
      setProviderAvailable(availability.available)
    }

    void checkProviderAvailability()
  }, [])

  const selectedCandidate = useMemo(() => {
    if (!searchResponse?.candidates.length) {
      return null
    }

    if (!selectedCandidateKey) {
      return searchResponse.candidates[0] ?? null
    }

    return searchResponse.candidates.find((candidate) => getCandidateKey(candidate) === selectedCandidateKey) ?? searchResponse.candidates[0] ?? null
  }, [searchResponse, selectedCandidateKey])

  const comparisonCandidates = useMemo(() => {
    if (!searchResponse?.candidates.length) {
      return []
    }

    const ordered = comparisonKeys
      .map((key) => searchResponse.candidates.find((candidate) => getCandidateKey(candidate) === key))
      .filter((candidate): candidate is Candidate => Boolean(candidate))

    return ordered.slice(0, 3)
  }, [comparisonKeys, searchResponse])

  const selectedCandidateState = useMemo<CandidateWorkspaceState | null>(() => {
    if (!selectedCandidate) {
      return null
    }

    const candidateWithState = selectedCandidate as Candidate & {
      shortlist?: boolean
      reviewed?: boolean
      rejected?: boolean
      notes?: Array<{ id: string; text: string; createdAt: string; updatedAt?: string; pinned?: boolean }>
      resumes?: Array<{ name: string; uploadedAt: string; size?: string; version?: string; status?: string }>
      activity?: Array<{ id: string; type: string; label: string; detail: string; timestamp: string }>
      exported?: boolean
      status?: string | null
    }

    const status = candidateWithState.status ?? (candidateWithState.rejected ? 'Rejected' : candidateWithState.shortlist ? 'Shortlisted' : candidateWithState.reviewed ? 'Reviewed' : candidateWithState.exported ? 'Submitted' : 'New')

    return {
      shortlist: candidateWithState.shortlist ?? false,
      reviewed: candidateWithState.reviewed ?? false,
      rejected: candidateWithState.rejected ?? false,
      notes: candidateWithState.notes ?? [],
      resumes: candidateWithState.resumes ?? [],
      activity: candidateWithState.activity ?? [],
      exported: candidateWithState.exported ?? false,
      status,
    }
  }, [selectedCandidate])

  const updateIntent = (updater: (current: SearchIntent) => SearchIntent) => {
    setIntent((current) => {
      const next = updater(current)
      setValidationErrors(validateIntent(next))
      return next
    })
  }

  const parseIntent = async () => {
    if (!jdText.trim()) {
      setNotice({ type: 'error', message: 'Paste a job description before parsing.' })
      setValidationErrors(['Paste a job description before parsing.'])
      return null
    }

    setBusyState('parsing')
    setNotice(null)

    try {
      const parsed = await parseJobDescription(jdText)
      setIntent(parsed)
      setHasParsed(true)
      setLastParsedJd(jdText)
      setValidationErrors(validateIntent(parsed))
      setNotice({ type: 'success', message: 'Search brief refreshed from the job description.' })
      return parsed
    } catch (error) {
      setNotice({ type: 'error', message: error instanceof Error ? error.message : 'Unable to parse JD' })
      return null
    } finally {
      setBusyState(null)
    }
  }

  const runSearch = async () => {
    const availability = await getProviderAvailability()
    setProviderAvailable(availability.available)
    const nextValidation = validateIntent(intent)
    setValidationErrors(nextValidation)

    if (!jdText.trim()) {
      setNotice({ type: 'error', message: 'Paste a job description before searching.' })
      return
    }

    if (nextValidation.length) {
      setNotice({ type: 'error', message: 'Complete the required sections before searching.' })
      return
    }

    setBusyState('searching')
    setNotice(null)
    setSearchResponse(null)
    setSelectedCandidateKey(null)

    try {
      const parsedIntent = (!hasParsed || jdText.trim() !== lastParsedJd.trim())
        ? await parseIntent()
        : intent

      const startedAt = Date.now()
      const payload = await runCandidateSearch(jdText, parsedIntent ?? intent)
      const duration = `${((Date.now() - startedAt) / 1000).toFixed(1)}s`
      setSearchResponse(payload)
      setSelectedCandidateKey(payload.candidates[0] ? getCandidateKey(payload.candidates[0]) : null)
      const nextSummary = buildSearchSummary(payload)
      nextSummary.searchDuration = duration
      setSearchSummary(nextSummary)
      setAnalytics(buildAnalytics(payload))
      setDemoMode(Boolean(payload.demo || !availability.available))
      setHistory((current) => [createHistoryEntry(jdText, parsedIntent ? serializeIntentForSearch(parsedIntent) : serializeIntentForSearch(intent), payload.candidate_count ?? payload.candidates.length, duration, parsedIntent ?? intent), ...current].slice(0, 8))
      setNotice({
        type: 'success',
        message: nextSummary.demo
          ? 'No sourcing providers are configured. Showing representative candidates.'
          : `Found ${payload.candidate_count ?? 0} candidates.`,
      })
    } catch (error) {
      setNotice({ type: 'error', message: error instanceof Error ? error.message : 'Unable to run search' })
    } finally {
      setBusyState(null)
    }
  }

  const exportResults = async () => {
    const nextValidation = validateIntent(intent)
    setValidationErrors(nextValidation)

    if (!jdText.trim()) {
      setNotice({ type: 'error', message: 'Paste a job description before exporting.' })
      return
    }

    if (nextValidation.length) {
      setNotice({ type: 'error', message: 'Complete the required sections before exporting.' })
      return
    }

    setBusyState('exporting')
    setNotice(null)

    try {
      const parsedIntent = (!hasParsed || jdText.trim() !== lastParsedJd.trim())
        ? await parseIntent()
        : intent

      await exportCandidateResults(jdText, parsedIntent ?? intent)
      setNotice({ type: 'success', message: 'Export started successfully.' })
    } catch (error) {
      setNotice({ type: 'error', message: error instanceof Error ? error.message : 'Unable to export results' })
    } finally {
      setBusyState(null)
    }
  }

  const applyCandidateAction = (candidate: Candidate, action: RecruiterAction, payload?: string) => {
    const key = getCandidateKey(candidate)
    setSearchResponse((current) => {
      if (!current) {
        return current
      }

      return {
        ...current,
        candidates: current.candidates.map((item) => {
          if (getCandidateKey(item) !== key) {
            return item
          }

          const nextCandidate = item as Candidate & {
            shortlist?: boolean
            reviewed?: boolean
            rejected?: boolean
            notes?: Array<{ id: string; text: string; createdAt: string; updatedAt?: string; pinned?: boolean }>
            resumes?: Array<{ name: string; uploadedAt: string; size?: string; version?: string; status?: string }>
            activity?: Array<{ id: string; type: string; label: string; detail: string; timestamp: string }>
            exported?: boolean
            status?: string | null
          }

          const nextNotes = action === 'note' && payload?.trim()
            ? [...(nextCandidate.notes ?? []), { id: `note-${Date.now()}`, text: payload.trim(), createdAt: new Date().toLocaleString() }]
            : (nextCandidate.notes ?? [])

          const activity = [...(nextCandidate.activity ?? [])]
          if (action === 'review') {
            activity.push(buildActivityEntry('review', 'Reviewed', 'Recruiter reviewed the candidate profile and notes.'))
          }
          if (action === 'shortlist') {
            activity.push(buildActivityEntry('shortlist', 'Shortlisted', 'Recruiter marked the candidate for follow-up.'))
          }
          if (action === 'submit') {
            activity.push(buildActivityEntry('submit', 'Submitted', 'Recruiter moved the candidate into the submission pipeline.'))
          }
          if (action === 'interview') {
            activity.push(buildActivityEntry('interview', 'Interviewing', 'Recruiter advanced the candidate to interview stage.'))
          }
          if (action === 'offer') {
            activity.push(buildActivityEntry('offer', 'Offer', 'Recruiter recorded an offer decision.'))
          }
          if (action === 'reject') {
            activity.push(buildActivityEntry('reject', 'Rejected', 'Recruiter moved the candidate out of the active slate.'))
          }
          if (action === 'export') {
            activity.push(buildActivityEntry('export', 'Exported', 'Candidate export prepared from the local workspace.'))
          }

          const nextStatus = action === 'review' ? 'Reviewed' : action === 'shortlist' ? 'Shortlisted' : action === 'submit' ? 'Submitted' : action === 'interview' ? 'Interviewing' : action === 'offer' ? 'Offer' : action === 'reject' ? 'Rejected' : nextCandidate.status ?? 'New'

          return {
            ...item,
            shortlist: action === 'shortlist' ? true : nextCandidate.shortlist ?? false,
            reviewed: action === 'review' ? true : nextCandidate.reviewed ?? false,
            rejected: action === 'reject' ? true : nextCandidate.rejected ?? false,
            notes: nextNotes,
            resumes: nextCandidate.resumes ?? [],
            activity,
            exported: action === 'export' ? true : nextCandidate.exported ?? false,
            status: nextStatus,
          }
        }),
      }
    })
  }

  const addResume = (candidate: Candidate, name: string) => {
    const key = getCandidateKey(candidate)
    setSearchResponse((current) => {
      if (!current) {
        return current
      }

      return {
        ...current,
        candidates: current.candidates.map((item) => {
          if (getCandidateKey(item) !== key) {
            return item
          }

          const nextCandidate = item as Candidate & {
            resumes?: Array<{ name: string; uploadedAt: string; size?: string; version?: string; status?: string }>
            activity?: Array<{ id: string; type: string; label: string; detail: string; timestamp: string }>
          }
          const resumes = [...(nextCandidate.resumes ?? []), { name, uploadedAt: new Date().toLocaleString(), size: '0 KB', version: 'v1', status: 'Uploaded' }]
          const activity = [...(nextCandidate.activity ?? []), buildActivityEntry('resume', 'Resume uploaded', 'Recruiter attached a resume in the candidate workspace.')]
          return {
            ...item,
            resumes,
            activity,
            resume_status: 'Uploaded',
          }
        }),
      }
    })
  }

  const addNote = (candidate: Candidate, text: string) => {
    if (!text.trim()) {
      return
    }

    const key = getCandidateKey(candidate)
    setSearchResponse((current) => {
      if (!current) {
        return current
      }

      return {
        ...current,
        candidates: current.candidates.map((item) => {
          if (getCandidateKey(item) !== key) {
            return item
          }

          const nextCandidate = item as Candidate & {
            notes?: Array<{ id: string; text: string; createdAt: string; updatedAt?: string; pinned?: boolean }>
            activity?: Array<{ id: string; type: string; label: string; detail: string; timestamp: string }>
          }
          return {
            ...item,
            notes: [...(nextCandidate.notes ?? []), { id: `note-${Date.now()}`, text: text.trim(), createdAt: new Date().toLocaleString(), pinned: false }],
            activity: [...(nextCandidate.activity ?? []), buildActivityEntry('note', 'Note added', 'Recruiter captured an internal note for this candidate.')],
          }
        }),
      }
    })
  }

  const editNote = (candidate: Candidate, noteId: string, text: string, pinned?: boolean) => {
    if (!text.trim()) {
      return
    }

    const key = getCandidateKey(candidate)
    setSearchResponse((current) => {
      if (!current) {
        return current
      }

      return {
        ...current,
        candidates: current.candidates.map((item) => {
          if (getCandidateKey(item) !== key) {
            return item
          }

          const nextCandidate = item as Candidate & { notes?: Array<{ id: string; text: string; createdAt: string; updatedAt?: string; pinned?: boolean }> }
          return {
            ...item,
            notes: (nextCandidate.notes ?? []).map((note) => (note.id === noteId ? { ...note, text: text.trim(), updatedAt: new Date().toLocaleString(), pinned: pinned ?? note.pinned } : note)),
          }
        }),
      }
    })
  }

  const deleteNote = (candidate: Candidate, noteId: string) => {
    const key = getCandidateKey(candidate)
    setSearchResponse((current) => {
      if (!current) {
        return current
      }

      return {
        ...current,
        candidates: current.candidates.map((item) => {
          if (getCandidateKey(item) !== key) {
            return item
          }

          const nextCandidate = item as Candidate & { notes?: Array<{ id: string; text: string; createdAt: string; updatedAt?: string; pinned?: boolean }> }
          return {
            ...item,
            notes: (nextCandidate.notes ?? []).filter((note) => note.id !== noteId),
          }
        }),
      }
    })
  }

  const togglePin = (candidate: Candidate, noteId: string) => {
    const key = getCandidateKey(candidate)
    setSearchResponse((current) => {
      if (!current) {
        return current
      }

      return {
        ...current,
        candidates: current.candidates.map((item) => {
          if (getCandidateKey(item) !== key) {
            return item
          }

          const nextCandidate = item as Candidate & { notes?: Array<{ id: string; text: string; createdAt: string; updatedAt?: string; pinned?: boolean }> }
          return {
            ...item,
            notes: (nextCandidate.notes ?? []).map((note) => note.id === noteId ? { ...note, pinned: !note.pinned } : note),
          }
        }),
      }
    })
  }

  const viewCandidate = (candidate: Candidate) => {
    const key = getCandidateKey(candidate)
    setSelectedCandidateKey(key)
    setSearchResponse((current) => {
      if (!current) {
        return current
      }

      return {
        ...current,
        candidates: current.candidates.map((item) => {
          if (getCandidateKey(item) !== key) {
            return item
          }

          const nextCandidate = item as Candidate & { activity?: Array<{ id: string; type: string; label: string; detail: string; timestamp: string }> }
          return {
            ...item,
            activity: [...(nextCandidate.activity ?? []), buildActivityEntry('view', 'Candidate viewed', 'Recruiter opened the profile workspace.')],
          }
        }),
      }
    })
  }

  const reopenHistoryEntry = (entry: SearchHistoryEntry) => {
    setJdText(entry.jd)
    setIntent(entry.intent)
    setNotice({ type: 'success', message: `Reopened a previous search with ${entry.candidateCount} candidates.` })
  }

  return {
    jdText,
    setJdText,
    intent,
    updateIntent,
    busyState,
    notice,
    searchResponse,
    selectedCandidate,
    setSelectedCandidateKey,
    hasPendingParse,
    validationErrors,
    parsedIntentSummary,
    providerAvailable,
    searchSummary,
    analytics,
    selectedCandidateState,
    comparisonCandidates,
    history,
    demoMode,
    applyCandidateAction,
    addResume,
    addNote,
    editNote,
    deleteNote,
    togglePin,
    viewCandidate,
    reopenHistoryEntry,
    parseIntent,
    runSearch,
    exportResults,
  }
}

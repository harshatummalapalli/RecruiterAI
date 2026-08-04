import { useEffect, useMemo, useState } from 'react'
import type { Candidate, SearchIntent, SearchResponse } from '../types'
import {
  buildParsedIntentSummary,
  buildSearchSummary,
  defaultIntent,
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
  rejected: boolean
  notes: Array<{ id: string; text: string; createdAt: string }>
  resumes: Array<{ name: string; uploadedAt: string }>
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
  const [demoMode, setDemoMode] = useState(false)

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

  const selectedCandidateState = useMemo<CandidateWorkspaceState | null>(() => {
    if (!selectedCandidate) {
      return null
    }

    const candidateWithState = selectedCandidate as Candidate & {
      shortlist?: boolean
      rejected?: boolean
      notes?: Array<{ id: string; text: string; createdAt: string }>
      resumes?: Array<{ name: string; uploadedAt: string }>
      activity?: Array<{ id: string; type: string; label: string; detail: string; timestamp: string }>
      exported?: boolean
    }

    const status = candidateWithState.rejected ? 'Rejected' : candidateWithState.shortlist ? 'Shortlisted' : candidateWithState.exported ? 'Exported' : 'New'

    return {
      shortlist: candidateWithState.shortlist ?? false,
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

      const payload = await runCandidateSearch(jdText, parsedIntent ?? intent)
      setSearchResponse(payload)
      setSelectedCandidateKey(payload.candidates[0] ? getCandidateKey(payload.candidates[0]) : null)
      const nextSummary = buildSearchSummary(payload)
      setSearchSummary(nextSummary)
      setDemoMode(Boolean(payload.demo || !availability.available))
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
            rejected?: boolean
            notes?: Array<{ id: string; text: string; createdAt: string }>
            resumes?: Array<{ name: string; uploadedAt: string }>
            activity?: Array<{ id: string; type: string; label: string; detail: string; timestamp: string }>
            exported?: boolean
          }

          const nextNotes = action === 'note' && payload?.trim()
            ? [...(nextCandidate.notes ?? []), { id: `note-${Date.now()}`, text: payload.trim(), createdAt: new Date().toLocaleString() }]
            : (nextCandidate.notes ?? [])

          const activity = [...(nextCandidate.activity ?? [])]
          if (action === 'shortlist') {
            activity.push(buildActivityEntry('shortlist', 'Shortlisted', 'Recruiter marked the candidate for follow-up.'))
          }
          if (action === 'reject') {
            activity.push(buildActivityEntry('reject', 'Rejected', 'Recruiter moved the candidate out of the active slate.'))
          }
          if (action === 'export') {
            activity.push(buildActivityEntry('export', 'Exported', 'Candidate export prepared from the local workspace.'))
          }

          return {
            ...item,
            shortlist: action === 'shortlist' ? true : nextCandidate.shortlist ?? false,
            rejected: action === 'reject' ? true : nextCandidate.rejected ?? false,
            notes: nextNotes,
            resumes: nextCandidate.resumes ?? [],
            activity,
            exported: action === 'export' ? true : nextCandidate.exported ?? false,
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
            resumes?: Array<{ name: string; uploadedAt: string }>
            activity?: Array<{ id: string; type: string; label: string; detail: string; timestamp: string }>
          }
          const resumes = [...(nextCandidate.resumes ?? []), { name, uploadedAt: new Date().toLocaleString() }]
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
            notes?: Array<{ id: string; text: string; createdAt: string }>
            activity?: Array<{ id: string; type: string; label: string; detail: string; timestamp: string }>
          }
          return {
            ...item,
            notes: [...(nextCandidate.notes ?? []), { id: `note-${Date.now()}`, text: text.trim(), createdAt: new Date().toLocaleString() }],
            activity: [...(nextCandidate.activity ?? []), buildActivityEntry('note', 'Note added', 'Recruiter captured an internal note for this candidate.')],
          }
        }),
      }
    })
  }

  const editNote = (candidate: Candidate, noteId: string, text: string) => {
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

          const nextCandidate = item as Candidate & { notes?: Array<{ id: string; text: string; createdAt: string }> }
          return {
            ...item,
            notes: (nextCandidate.notes ?? []).map((note) => (note.id === noteId ? { ...note, text: text.trim() } : note)),
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

          const nextCandidate = item as Candidate & { notes?: Array<{ id: string; text: string; createdAt: string }> }
          return {
            ...item,
            notes: (nextCandidate.notes ?? []).filter((note) => note.id !== noteId),
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
    selectedCandidateState,
    demoMode,
    applyCandidateAction,
    addResume,
    addNote,
    editNote,
    deleteNote,
    viewCandidate,
    parseIntent,
    runSearch,
    exportResults,
  }
}

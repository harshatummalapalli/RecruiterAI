import { useMemo, useState } from 'react'
import type { SearchIntent, SearchResponse } from '../types'
import { buildParsedIntentSummary, defaultIntent, exportCandidateResults, getCandidateKey, parseJobDescription, runCandidateSearch, validateIntent, type BusyState, type Notice } from '../services/recruiterWorkflow'

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

  const parsedIntentSummary = useMemo(() => buildParsedIntentSummary(intent), [intent])
  const hasPendingParse = hasParsed && jdText.trim() !== lastParsedJd.trim()

  const selectedCandidate = useMemo(() => {
    if (!searchResponse?.candidates.length) {
      return null
    }

    if (!selectedCandidateKey) {
      return searchResponse.candidates[0] ?? null
    }

    return searchResponse.candidates.find((candidate) => getCandidateKey(candidate) === selectedCandidateKey) ?? searchResponse.candidates[0] ?? null
  }, [searchResponse, selectedCandidateKey])

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
      setNotice({ type: 'success', message: `Found ${payload.candidate_count ?? 0} candidates.` })
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
    parseIntent,
    runSearch,
    exportResults,
  }
}

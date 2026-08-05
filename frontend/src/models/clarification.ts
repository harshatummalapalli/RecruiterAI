// Decides whether the AI has enough confidence to generate the Search Brief
// directly, or whether it needs to ask the recruiter a small number of
// structured clarifying questions first. This is not a chatbot — it's a
// one-shot structured review: at most 5 questions, each answered with a
// single tap (radio/chip), never free text.

import { detectAllCountryHints, detectAllExperienceRanges, detectPrimaryTechCandidates, extractLocally } from '../screens/localJdExtraction'

export type ClarificationOption = { value: string; label: string }
export type ClarificationQuestion = {
  id: 'primaryTechnology' | 'locationCountry' | 'experienceRange' | 'workMode' | 'seniority'
  question: string
  options: ClarificationOption[]
}

const GENERIC_TITLES = new Set(['ai engineer', 'software engineer', 'engineer', 'developer', 'full stack engineer'])

const SENIORITY_OPTIONS = ['Junior', 'Mid-level', 'Senior', 'Staff', 'Principal']

const MAX_QUESTIONS = 5

export function buildClarificationQuestions(jdText: string): ClarificationQuestion[] {
  const text = jdText.trim()
  if (!text) {
    return []
  }

  const extraction = extractLocally(text)
  const questions: ClarificationQuestion[] = []

  // 1. Multiple backend languages / major technologies detected.
  const primaryTechCandidates = detectPrimaryTechCandidates(text)
  if (primaryTechCandidates.length > 1) {
    questions.push({
      id: 'primaryTechnology',
      question: 'Multiple major technologies were detected — how should we treat them?',
      options: [
        ...primaryTechCandidates.map((candidate) => ({ value: candidate, label: `${candidate} is the primary technology` })),
        { value: '__multiple__', label: 'This is a polyglot role — treat them all as required' },
      ],
    })
  }

  // 2. Ambiguous location — mentions span more than one country. Combines
  // countries implied by recognized "City, ST" entries with any other
  // country explicitly named in the text (e.g. a US city plus "...UK").
  const distinctCountries = Array.from(
    new Set([...extraction.locations.map((entry) => entry.country).filter(Boolean), ...detectAllCountryHints(text)]),
  )
  if (distinctCountries.length > 1) {
    questions.push({
      id: 'locationCountry',
      question: 'We found locations in multiple countries — how should we search?',
      options: [
        ...distinctCountries.map((country) => ({ value: country, label: `Just ${country}` })),
        { value: '__all__', label: 'All of these locations' },
      ],
    })
  }

  // 3. Conflicting experience requirements.
  const experienceRanges = detectAllExperienceRanges(text)
  if (experienceRanges.length > 1) {
    questions.push({
      id: 'experienceRange',
      question: 'This JD mentions more than one experience requirement — which is correct?',
      options: experienceRanges.map((range) => ({
        value: `${range.minimumYears ?? ''}-${range.maximumYears ?? ''}`,
        label: range.maximumYears ? `${range.minimumYears}–${range.maximumYears} years` : `${range.minimumYears}+ years`,
      })),
    })
  }

  // 4. Unclear work mode — both remote and onsite mentioned without an explicit "hybrid".
  if (extraction.workModes.includes('remote') && extraction.workModes.includes('onsite') && !extraction.workModes.includes('hybrid')) {
    questions.push({
      id: 'workMode',
      question: 'This JD mentions both remote and onsite work — which applies?',
      options: [
        { value: 'remote', label: 'Remote' },
        { value: 'hybrid', label: 'Hybrid' },
        { value: 'onsite', label: 'Onsite' },
      ],
    })
  }

  // 5. Generic title with no seniority signal anywhere in the JD.
  if (extraction.roleTitle && GENERIC_TITLES.has(extraction.roleTitle.trim().toLowerCase()) && !extraction.seniority) {
    questions.push({
      id: 'seniority',
      question: `"${extraction.roleTitle}" is a fairly broad title — what level are you hiring for?`,
      options: SENIORITY_OPTIONS.map((level) => ({ value: level, label: level })),
    })
  }

  return questions.slice(0, MAX_QUESTIONS)
}

// Stage 2 of the Recruiter Reasoning Pipeline: Technology Understanding.
//
// Combines primary-language detection, the multi-language reasoning
// judgment call, and AI-concept detection into one profile. This stage owns
// deciding what's "primary" vs "supporting" — later stages and the Search
// Brief builder just consume the result.

import { detectPrimaryTechCandidates } from '../screens/localJdExtraction'
import { classifyLanguageSignal } from './languageReasoning'
import { detectAiConcepts } from './technologyGraph'
import { technologyFamiliesReferencedBy } from './knowledge/technologyFamilies'
import type { TechnologyProfile } from './types'

export function analyzeTechnology(text: string, requiredSkills: string[], preferredSkills: string[]): TechnologyProfile {
  const candidates = detectPrimaryTechCandidates(text)
  const aiConcepts = detectAiConcepts(text)
  const allSkills = Array.from(new Set([...requiredSkills, ...preferredSkills, ...candidates]))
  const supportingTechnologies = allSkills.filter((skill) => !candidates.includes(skill))
  // Recruiter knowledge: which technology families (Cloud, Databases, AI,
  // ...) does this JD actually touch — asked, not hardcoded per-technology.
  const technologyFamilies = technologyFamiliesReferencedBy(allSkills)

  if (candidates.length < 2) {
    return {
      primaryTechnologies: candidates,
      supportingTechnologies,
      technologyFamilies,
      aiConcepts,
      languageSignal: null,
      languageDominant: null,
      confidence: candidates.length === 1 ? 0.9 : 0.5,
    }
  }

  const classification = classifyLanguageSignal(text, candidates)

  return {
    primaryTechnologies: candidates,
    supportingTechnologies,
    technologyFamilies,
    aiConcepts,
    languageSignal: classification.signal,
    languageDominant: classification.dominant,
    confidence: classification.signal === 'ambiguous' ? 0.4 : 0.85,
  }
}

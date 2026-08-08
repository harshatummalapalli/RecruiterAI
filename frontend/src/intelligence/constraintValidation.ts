// Stage 6 of the Recruiter Reasoning Pipeline: Constraint Validation.
//
// Runs every reusable recruiter rule from ruleEngine.ts against the
// section outputs already produced by the earlier stages, and collects
// whatever structured findings come back. This stage does not decide what
// the recruiter sees — it only decides what's *true*. Clarification
// Generation (stage 7) turns findings into a prioritized, capped set of
// questions.

import {
  detectExperienceConflict,
  detectLocationConflict,
  detectMissingSeniority,
  detectOverConstrainedSkills,
  detectTitleExperienceMismatch,
  detectUnresolvedPrimaryTechnology,
  detectWorkModeConflict,
} from './ruleEngine'
import type { ExperienceProfile, LocationProfile, TechnologyProfile, TitleProfile, ValidationFinding } from './types'

export type ConstraintValidationInput = {
  requiredSkillCount: number
  title: TitleProfile
  technology: TechnologyProfile
  experience: ExperienceProfile
  location: LocationProfile
}

export function validateConstraints(input: ConstraintValidationInput): ValidationFinding[] {
  const findings = [
    detectUnresolvedPrimaryTechnology(input.technology.primaryTechnologies, input.technology.languageSignal),
    detectLocationConflict(input.location.ambiguousCountries),
    detectExperienceConflict(input.experience.conflicting, input.experience.minimumYears, input.experience.maximumYears),
    detectWorkModeConflict(input.location.workModes),
    detectMissingSeniority(input.title.primaryTitle || null, input.title.seniority),
    detectOverConstrainedSkills(input.requiredSkillCount),
    detectTitleExperienceMismatch(input.title.primaryTitle || null, input.experience.minimumYears),
  ]

  return findings.filter((finding): finding is ValidationFinding => finding !== null)
}

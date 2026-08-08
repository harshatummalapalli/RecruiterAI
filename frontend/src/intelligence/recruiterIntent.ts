// The Recruiter Reasoning Pipeline — the entry point of the Recruiter
// Intelligence Layer.
//
//   JD / Recruiter Input
//         ↓
//   Role Classification → Technology Understanding → Title Reasoning →
//   Experience Reasoning → Location Reasoning → Constraint Validation →
//   Clarification Generation
//         ↓
//   Recruiter Intent
//
// Each stage has one responsibility and lives in its own file. This module
// only sequences them and assembles their outputs into the canonical
// RecruiterIntent — it contains no reasoning of its own. See
// docs/ARCHITECTURE.md for the full data flow and the rationale behind
// each stage.

import { extractLocally } from '../screens/localJdExtraction'
import { classifyRole } from './roleClassifier'
import { analyzeTechnology } from './technologyAnalysis'
import { reasonAboutTitle } from './titleReasoning'
import { reasonAboutExperience } from './experienceReasoning'
import { reasonAboutLocation } from './locationReasoning'
import { validateConstraints } from './constraintValidation'
import { generateClarifications } from './clarificationEngine'
import { guidanceFor } from './knowledge/hiringPatterns'
import type { ConfidenceSection, EmploymentType, RecruiterIntent, Severity } from './types'

const CONSTRAINT_PENALTY: Record<Severity, number> = { high: 0.3, medium: 0.15, low: 0.05 }

function createEmptyRecruiterIntent(): RecruiterIntent {
  return {
    hiringObjective: '',
    roleFamily: 'Unclassified',
    roleSpecialization: null,
    seniority: null,
    hiringConstraints: [],
    primaryTechnologies: [],
    supportingTechnologies: [],
    domainExpertise: [],
    industryContext: [],
    companyPreferences: { include: [], exclude: [] },
    candidateBackgroundPreferences: [],
    locationStrategy: { geography: 'global', country: null, locations: [], workModes: [], ambiguousCountries: [], confidence: 0 },
    experienceStrategy: { minimumYears: null, maximumYears: null, conflicting: false, confidence: 0 },
    employmentModel: [],
    exclusions: { titles: [], companies: [], skills: [] },
    ambiguities: [],
    clarificationsRequired: [],
    hiringGuidance: [],
    confidenceBySection: { role: 0, technology: 0, title: 0, experience: 0, location: 0, constraints: 1 },
    roleClassification: { roleFamily: 'Unclassified', specialization: null, evidence: [], confidence: 0 },
    technologyProfile: {
      primaryTechnologies: [],
      supportingTechnologies: [],
      technologyFamilies: [],
      aiConcepts: { llm: false, generativeAi: false, rag: false, agentic: false, mcp: false, promptEngineering: false, fineTuning: false },
      languageSignal: null,
      languageDominant: null,
      confidence: 0,
    },
    titleProfile: { primaryTitle: '', equivalentTitles: [], pastTitles: [], excludedTitles: [], seniority: null, confidence: 0 },
    requiredSkills: [],
    preferredSkills: [],
  }
}

export function buildRecruiterIntent(jdText: string): RecruiterIntent {
  const text = jdText.trim()
  if (!text) {
    return createEmptyRecruiterIntent()
  }

  const extraction = extractLocally(text)

  const roleClassification = classifyRole(extraction.roleTitle ?? '', text)
  const technologyProfile = analyzeTechnology(text, extraction.requiredSkills, extraction.preferredSkills)
  const titleProfile = reasonAboutTitle(extraction.roleTitle, extraction.seniority)
  const experienceProfile = reasonAboutExperience(text)
  const locationProfile = reasonAboutLocation(text)

  const findings = validateConstraints({
    requiredSkillCount: extraction.requiredSkills.length,
    title: titleProfile,
    technology: technologyProfile,
    experience: experienceProfile,
    location: locationProfile,
  })

  const clarificationsRequired = generateClarifications(findings)
  const constraintConfidence = Math.max(0, 1 - findings.reduce((sum, finding) => sum + CONSTRAINT_PENALTY[finding.severity], 0))

  const hiringConstraints: string[] = []
  if (extraction.employmentTypes.length) {
    hiringConstraints.push(`Employment: ${extraction.employmentTypes.join(', ')}`)
  }
  if (locationProfile.workModes.length) {
    hiringConstraints.push(`Work mode: ${locationProfile.workModes.join(', ')}`)
  }
  for (const finding of findings) {
    if (finding.id === 'overConstrainedSkills') {
      hiringConstraints.push(finding.summary)
    }
  }

  const roleLabel = roleClassification.roleFamily !== 'Unclassified' ? roleClassification.roleFamily : titleProfile.primaryTitle || 'engineer'
  const hiringObjective = `Hire a${titleProfile.seniority ? ` ${titleProfile.seniority}` : ''} ${roleLabel}`.replace(/\s+/g, ' ').trim()

  const confidenceBySection: Record<ConfidenceSection, number> = {
    role: roleClassification.confidence,
    technology: technologyProfile.confidence,
    title: titleProfile.confidence,
    experience: experienceProfile.confidence,
    location: locationProfile.confidence,
    constraints: constraintConfidence,
  }

  return {
    hiringObjective,
    roleFamily: roleClassification.roleFamily,
    roleSpecialization: roleClassification.specialization,
    seniority: titleProfile.seniority,
    hiringConstraints,
    primaryTechnologies: technologyProfile.primaryTechnologies,
    supportingTechnologies: technologyProfile.supportingTechnologies,
    // Reserved for future evidence-based detection — populated conservatively
    // (only from explicit JD evidence) elsewhere in the pipeline; currently
    // no local heuristic detects domain/industry, so these stay empty rather
    // than guess.
    domainExpertise: [],
    industryContext: [],
    // No local heuristic detects company preferences either — those are
    // currently only ever recruiter-entered or AI-parsed (stage 2 of the
    // Search Brief builder), never fabricated here.
    companyPreferences: { include: [], exclude: [] },
    candidateBackgroundPreferences: technologyProfile.supportingTechnologies,
    locationStrategy: locationProfile,
    experienceStrategy: experienceProfile,
    employmentModel: extraction.employmentTypes as EmploymentType[],
    exclusions: { titles: titleProfile.excludedTitles, companies: [], skills: [] },
    ambiguities: findings.map((finding) => finding.summary),
    clarificationsRequired,
    hiringGuidance: guidanceFor(roleClassification.roleFamily, titleProfile.seniority),
    confidenceBySection,
    roleClassification,
    technologyProfile,
    titleProfile,
    requiredSkills: extraction.requiredSkills,
    preferredSkills: extraction.preferredSkills,
  }
}

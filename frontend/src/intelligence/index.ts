// The Recruiter Intelligence Layer.
//
// Every JD, recruiter instruction, and search refinement flows through the
// Recruiter Reasoning Pipeline (recruiterIntent.ts) before a Search Brief is
// generated or updated — it is the product's decision engine, not a parser.
// It is intentionally isolated from every UI component: nothing in
// `frontend/src/screens/` imports from here directly. Instead,
// `models/searchBrief.ts` and `models/clarification.ts` consume it and
// expose the same single, structured SearchBrief the UI already binds to —
// so a future provider or a smarter reasoning module can plug in here
// without any screen ever changing.
//
// See docs/ARCHITECTURE.md for the full pipeline and data flow.

export * from './types'
export * from './technologyGraph'
export * from './languageReasoning'
export * from './titleIntelligence'
export * from './ruleEngine'
export * from './roleClassifier'
export * from './technologyAnalysis'
export * from './titleReasoning'
export * from './experienceReasoning'
export * from './locationReasoning'
export * from './constraintValidation'
export * from './clarificationEngine'
export * from './recruiterIntent'
export * from './knowledge'

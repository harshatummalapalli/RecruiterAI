// Recruiter Knowledge Engine.
//
// Structured recruiter knowledge, consumed by the Recruiter Intent Engine's
// reasoning stages (../roleClassifier.ts, ../titleIntelligence.ts,
// ../technologyAnalysis.ts, ../recruiterIntent.ts). Knowledge informs;
// reasoning decides. Nothing in this directory makes a decision about a
// specific JD — it only describes what's generally true about role
// families, technology families, career progression, title equivalence,
// and hiring patterns, so reasoning can ask a question instead of embedding
// an assumption.
//
// Adding a new role family, technology family, or hiring pattern is a data
// change here — it should never require touching a reasoning stage.

export * from './roleFamilies'
export * from './technologyFamilies'
export * from './careerProgression'
export * from './semanticTitles'
export * from './hiringPatterns'

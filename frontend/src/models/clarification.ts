// Decides whether the Recruiter Intelligence Layer has enough confidence to
// generate the Search Brief directly, or whether it needs to ask the
// recruiter a small number of structured clarifying questions first.
//
// This is a thin wrapper, not where the reasoning lives: clarifications are
// generated from Recruiter Intent (see intelligence/recruiterIntent.ts and
// intelligence/clarificationEngine.ts), never by re-reading the raw JD
// directly — this file exists only to keep the screen-facing import path
// (`../models/clarification`) stable. This is not a chatbot — it's a
// one-shot structured review: each question is answered with a single tap
// (radio/chip), never free text, and the Clarification Generation stage
// prefers one high-value question over several low-value ones.

import { buildRecruiterIntent } from '../intelligence/recruiterIntent'
import type { ClarificationQuestion, ClarificationOption } from '../intelligence/types'

export type { ClarificationQuestion, ClarificationOption }

export function buildClarificationQuestions(jdText: string): ClarificationQuestion[] {
  return buildRecruiterIntent(jdText).clarificationsRequired
}

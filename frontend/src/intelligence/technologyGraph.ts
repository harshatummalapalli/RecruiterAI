// Part of the Recruiter Intelligence Layer.
//
// Technologies are related, not interchangeable. LLM / Generative AI / RAG /
// Agents / MCP / Prompt Engineering / Fine-Tuning are frequently mentioned in
// the same paragraph of a JD, but they are distinct capabilities — a role
// that wants RAG experience is not automatically asking for fine-tuning
// experience. Each concept is detected independently; none are merged into a
// single "AI experience" bucket.

export type AiConceptFlags = {
  llm: boolean
  generativeAi: boolean
  rag: boolean
  agentic: boolean
  mcp: boolean
  promptEngineering: boolean
  fineTuning: boolean
}

const AI_CONCEPT_PATTERNS: Record<keyof AiConceptFlags, RegExp> = {
  llm: /\bLLMs?\b|large language models?/i,
  generativeAi: /\bgenerative ai\b|\bgen[\s-]?ai\b/i,
  rag: /\bRAG\b|retrieval[\s-]augmented generation/i,
  agentic: /\bagentic\b|\bAI agents?\b|\bmulti-agent\b/i,
  mcp: /\bMCP\b|model context protocol/i,
  promptEngineering: /\bprompt engineering\b/i,
  fineTuning: /\bfine[\s-]?tun(?:e|ed|ing)\b/i,
}

/** Every distinct AI concept explicitly named in the text. No inference, no
 * synonym collapsing — each flag is only true when its own evidence exists. */
export function detectAiConcepts(text: string): AiConceptFlags {
  const flags = {} as AiConceptFlags
  for (const key of Object.keys(AI_CONCEPT_PATTERNS) as Array<keyof AiConceptFlags>) {
    flags[key] = AI_CONCEPT_PATTERNS[key].test(text)
  }
  return flags
}

export function createEmptyAiConceptFlags(): AiConceptFlags {
  return {
    llm: false,
    generativeAi: false,
    rag: false,
    agentic: false,
    mcp: false,
    promptEngineering: false,
    fineTuning: false,
  }
}

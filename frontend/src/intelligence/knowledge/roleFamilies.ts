// Recruiter Knowledge Engine — Role Families.
//
// Structured knowledge about each role family: what it does, what
// technology families it typically draws from, how careers move in and out
// of it, and which other families it's closely related to. This is data,
// not logic — `roleClassifier.ts` (reasoning) asks this module "what does
// recruiter knowledge say about this role family?" instead of embedding
// "if title contains AI..." branches itself.
//
// `detectionSignals` is the one part of each record that exists to let
// reasoning find a match at all — it's still data (a pattern to look for),
// not a hardcoded branch. Everything else here is pure recruiter knowledge:
// responsibilities, technology families, career transitions, related roles.

import type { RoleFamily } from '../types'

export type RoleFamilyKnowledge = {
  id: RoleFamily
  label: string
  detectionSignals: {
    titlePattern: RegExp
    technologyPattern?: RegExp
    responsibilityPattern?: RegExp
  }
  commonResponsibilities: string[]
  /** References technologyFamilies.ts ids — see that module. */
  commonTechnologyFamilies: string[]
  /** Typical titles/directions a career in this family moves through —
   * guidance, not a strict ladder (see careerProgression.ts for the ladder). */
  commonCareerTransitions: string[]
  relatedRoleFamilies: RoleFamily[]
}

export const ROLE_FAMILY_KNOWLEDGE: RoleFamilyKnowledge[] = [
  {
    id: 'Backend Engineer',
    label: 'Backend Engineering',
    detectionSignals: {
      titlePattern: /\bback-?end engineer\b/i,
      technologyPattern: /\bapi\b|microservices|\bdatabase\b|server-side/i,
    },
    commonResponsibilities: ['API design', 'service architecture', 'database design', 'system reliability'],
    commonTechnologyFamilies: ['programming-languages', 'databases', 'cloud', 'containers', 'messaging'],
    commonCareerTransitions: ['Senior Backend Engineer', 'Staff Engineer', 'Platform Engineer', 'Engineering Manager'],
    relatedRoleFamilies: ['Full Stack Engineer', 'Platform Engineer', 'Data Engineer'],
  },
  {
    id: 'Frontend Engineer',
    label: 'Frontend Engineering',
    detectionSignals: {
      titlePattern: /\bfront-?end engineer\b/i,
      technologyPattern: /\breact\b|\bangular\b|\bvue\b|\bcss\b|accessibility/i,
    },
    commonResponsibilities: ['UI implementation', 'client-side performance', 'accessibility', 'design-system work'],
    commonTechnologyFamilies: ['frameworks', 'programming-languages'],
    commonCareerTransitions: ['Senior Frontend Engineer', 'Staff Engineer', 'Full Stack Engineer'],
    relatedRoleFamilies: ['Full Stack Engineer', 'Mobile Engineer'],
  },
  {
    id: 'Full Stack Engineer',
    label: 'Full Stack Engineering',
    detectionSignals: {
      titlePattern: /\bfull-?stack engineer\b/i,
      technologyPattern: /\breact\b|\bnode(?:\.js)?\b|end[- ]to[- ]end feature/i,
    },
    commonResponsibilities: ['end-to-end feature delivery', 'API design', 'UI implementation'],
    commonTechnologyFamilies: ['programming-languages', 'frameworks', 'databases', 'cloud'],
    commonCareerTransitions: ['Senior Full Stack Engineer', 'Backend Engineer', 'Frontend Engineer', 'Staff Engineer'],
    relatedRoleFamilies: ['Backend Engineer', 'Frontend Engineer'],
  },
  {
    id: 'AI Software Engineer',
    label: 'AI Engineering',
    detectionSignals: {
      titlePattern: /\bai (software )?engineer\b/i,
      technologyPattern: /\bLLMs?\b|large language models?|generative ai|\bRAG\b|agentic|prompt engineering/i,
    },
    commonResponsibilities: ['LLM application development', 'retrieval pipelines', 'production AI integration'],
    commonTechnologyFamilies: ['ai', 'vector-databases', 'programming-languages', 'cloud'],
    commonCareerTransitions: ['Senior AI Engineer', 'Applied AI Engineer', 'ML Engineer', 'Staff Engineer'],
    relatedRoleFamilies: ['Applied AI Engineer', 'ML Engineer', 'Backend Engineer'],
  },
  {
    id: 'Applied AI Engineer',
    label: 'Applied AI Engineering',
    detectionSignals: {
      titlePattern: /\bapplied ai engineer\b/i,
      technologyPattern: /\bLLMs?\b|\bRAG\b|fine[-\s]?tun|production ai/i,
    },
    commonResponsibilities: ['applying foundation models to product problems', 'evaluation pipelines', 'fine-tuning'],
    commonTechnologyFamilies: ['ai', 'vector-databases', 'programming-languages'],
    commonCareerTransitions: ['AI Software Engineer', 'ML Engineer', 'Staff Engineer'],
    relatedRoleFamilies: ['AI Software Engineer', 'ML Engineer'],
  },
  {
    id: 'ML Engineer',
    label: 'ML Engineering',
    detectionSignals: {
      titlePattern: /\b(ml|machine learning) engineer\b/i,
      technologyPattern: /\bpytorch\b|\btensorflow\b|\bmlops\b|model training|feature engineering/i,
    },
    commonResponsibilities: ['model training', 'MLOps', 'feature pipelines', 'model serving'],
    commonTechnologyFamilies: ['ai', 'databases', 'cloud', 'infrastructure'],
    commonCareerTransitions: ['Senior ML Engineer', 'Applied AI Engineer', 'Data Scientist', 'Staff Engineer'],
    relatedRoleFamilies: ['Applied AI Engineer', 'AI Software Engineer', 'Data Scientist', 'Data Engineer'],
  },
  {
    id: 'Data Engineer',
    label: 'Data Engineering',
    detectionSignals: {
      titlePattern: /\bdata engineer\b/i,
      technologyPattern: /\betl\b|\bairflow\b|\bspark\b|data pipeline|data warehouse/i,
    },
    commonResponsibilities: ['data pipeline design', 'data warehousing', 'data quality'],
    commonTechnologyFamilies: ['databases', 'messaging', 'cloud', 'infrastructure'],
    commonCareerTransitions: ['Senior Data Engineer', 'Data Scientist', 'ML Engineer', 'Staff Engineer'],
    relatedRoleFamilies: ['Data Scientist', 'ML Engineer', 'Platform Engineer'],
  },
  {
    id: 'Data Scientist',
    label: 'Data Science',
    detectionSignals: {
      titlePattern: /\bdata scientist\b/i,
      technologyPattern: /\bstatistics\b|\bpandas\b|\bjupyter\b|experimentation|\ba\/b testing\b/i,
    },
    commonResponsibilities: ['statistical modeling', 'experimentation', 'analysis and reporting'],
    commonTechnologyFamilies: ['databases', 'ai'],
    commonCareerTransitions: ['Senior Data Scientist', 'ML Engineer', 'Staff Data Scientist'],
    relatedRoleFamilies: ['ML Engineer', 'Data Engineer'],
  },
  {
    id: 'DevOps Engineer',
    label: 'DevOps',
    detectionSignals: {
      titlePattern: /\bdevops engineer\b/i,
      technologyPattern: /\bci\/cd\b|\bterraform\b|\bansible\b|infrastructure as code/i,
    },
    commonResponsibilities: ['CI/CD pipelines', 'infrastructure automation', 'release engineering'],
    commonTechnologyFamilies: ['infrastructure', 'cloud', 'containers', 'observability'],
    commonCareerTransitions: ['Senior DevOps Engineer', 'Platform Engineer', 'Staff Engineer'],
    relatedRoleFamilies: ['Platform Engineer', 'Security Engineer'],
  },
  {
    id: 'Platform Engineer',
    label: 'Platform Engineering',
    detectionSignals: {
      titlePattern: /\bplatform engineer\b/i,
      technologyPattern: /\binternal tooling\b|developer experience|\bkubernetes\b|golden path/i,
    },
    commonResponsibilities: ['internal developer platforms', 'developer experience', 'infrastructure reliability'],
    commonTechnologyFamilies: ['infrastructure', 'cloud', 'containers', 'observability'],
    commonCareerTransitions: ['Senior Platform Engineer', 'Staff Engineer', 'Principal Engineer'],
    relatedRoleFamilies: ['DevOps Engineer', 'Backend Engineer', 'Security Engineer'],
  },
  {
    id: 'Security Engineer',
    label: 'Security Engineering',
    detectionSignals: {
      titlePattern: /\bsecurity engineer\b/i,
      technologyPattern: /penetration testing|vulnerabilit(?:y|ies)|\bsoc\s*2\b|threat model/i,
    },
    commonResponsibilities: ['threat modeling', 'vulnerability management', 'security tooling'],
    commonTechnologyFamilies: ['infrastructure', 'cloud', 'observability'],
    commonCareerTransitions: ['Senior Security Engineer', 'Staff Security Engineer', 'Security Architect'],
    relatedRoleFamilies: ['Platform Engineer', 'DevOps Engineer'],
  },
  {
    id: 'QA Engineer',
    label: 'QA',
    detectionSignals: {
      titlePattern: /\b(qa|quality assurance|sdet) engineer\b/i,
      technologyPattern: /test automation|\bselenium\b|\bcypress\b|test coverage/i,
    },
    commonResponsibilities: ['test automation', 'quality processes', 'release validation'],
    commonTechnologyFamilies: ['programming-languages', 'infrastructure'],
    commonCareerTransitions: ['Senior QA Engineer', 'SDET', 'QA Lead'],
    relatedRoleFamilies: ['Backend Engineer', 'DevOps Engineer'],
  },
  {
    id: 'Mobile Engineer',
    label: 'Mobile Engineering',
    detectionSignals: {
      titlePattern: /\bmobile engineer\b/i,
      technologyPattern: /\bios\b|\bandroid\b|\bswift\b|\bkotlin\b|react native/i,
    },
    commonResponsibilities: ['native app development', 'app performance', 'release management'],
    commonTechnologyFamilies: ['programming-languages', 'frameworks'],
    commonCareerTransitions: ['Senior Mobile Engineer', 'Staff Engineer', 'Mobile Lead'],
    relatedRoleFamilies: ['Frontend Engineer', 'Full Stack Engineer'],
  },
  {
    id: 'Engineering Manager',
    label: 'Management',
    detectionSignals: {
      titlePattern: /\b(engineering manager|em\b|manager,?\s*engineering)\b/i,
      responsibilityPattern: /\b(manage a team|direct reports|people management|1:1s|grow(?:ing)? engineers)\b/i,
    },
    commonResponsibilities: ['people management', 'team roadmap ownership', 'hiring and growth', 'cross-team coordination'],
    commonTechnologyFamilies: [],
    commonCareerTransitions: ['Senior Engineering Manager', 'Director of Engineering', 'VP of Engineering'],
    relatedRoleFamilies: ['Backend Engineer', 'Platform Engineer'],
  },
]

export function findRoleFamilyKnowledge(id: RoleFamily): RoleFamilyKnowledge | null {
  return ROLE_FAMILY_KNOWLEDGE.find((entry) => entry.id === id) ?? null
}

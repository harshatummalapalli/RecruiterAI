// Recruiter Knowledge Engine — Technology Families.
//
// Each family exposes relationships only — a flat set of related-but-distinct
// technologies. No ranking, no "primary" member: order here carries no
// meaning. This is what lets reasoning ask "what family does this
// technology belong to, and what else is in it?" instead of hardcoding
// technology-specific logic.

export type TechnologyFamily = {
  id: string
  label: string
  members: string[]
}

export const TECHNOLOGY_FAMILIES: TechnologyFamily[] = [
  {
    id: 'programming-languages',
    label: 'Programming Languages',
    members: ['Python', 'Java', 'Go', 'C#', 'Rust', 'Ruby', 'PHP', 'JavaScript', 'TypeScript', 'Swift', 'Kotlin'],
  },
  {
    id: 'dotnet',
    label: '.NET Ecosystem',
    members: ['C#', '.NET', '.NET Core', 'ASP.NET', 'ASP.NET Core', 'Entity Framework'],
  },
  {
    id: 'frameworks',
    label: 'Frameworks',
    members: ['React', 'Angular', 'Vue', 'Django', 'Flask', 'FastAPI', 'Spring', 'Node.js', 'Next.js'],
  },
  {
    id: 'cloud',
    label: 'Cloud',
    members: ['AWS', 'GCP', 'Azure'],
  },
  {
    id: 'containers',
    label: 'Containers',
    members: ['Docker', 'Kubernetes'],
  },
  {
    id: 'ai',
    label: 'AI',
    members: ['LLM', 'Generative AI', 'RAG', 'AI Agents', 'Prompt Engineering', 'Fine Tuning', 'MCP'],
  },
  {
    id: 'vector-databases',
    label: 'Vector Databases',
    members: ['Pinecone', 'Weaviate', 'Milvus', 'Chroma', 'pgvector'],
  },
  {
    id: 'databases',
    label: 'Databases',
    members: ['SQL', 'PostgreSQL', 'MySQL', 'MongoDB', 'Redis'],
  },
  {
    id: 'messaging',
    label: 'Messaging',
    members: ['Kafka', 'RabbitMQ', 'SQS', 'Pub/Sub'],
  },
  {
    id: 'observability',
    label: 'Observability',
    members: ['Prometheus', 'Grafana', 'Datadog', 'OpenTelemetry'],
  },
  {
    id: 'infrastructure',
    label: 'Infrastructure',
    members: ['Terraform', 'Ansible', 'CI/CD'],
  },
]

function normalize(value: string): string {
  return value.trim().toLowerCase()
}

export function findTechnologyFamily(skill: string): TechnologyFamily | null {
  const target = normalize(skill)
  return TECHNOLOGY_FAMILIES.find((family) => family.members.some((member) => normalize(member) === target)) ?? null
}

/** The other members of the same family — a technology's siblings, never
 * itself, never ranked. */
export function relatedTechnologies(skill: string): string[] {
  const family = findTechnologyFamily(skill)
  if (!family) {
    return []
  }
  const target = normalize(skill)
  return family.members.filter((member) => normalize(member) !== target)
}

/** Every distinct family referenced by a set of skills — used to attach
 * "what kinds of technology does this JD touch" to Recruiter Intent without
 * hardcoding a per-technology check in the reasoning stage. */
export function technologyFamiliesReferencedBy(skills: string[]): string[] {
  const familyIds = new Set<string>()
  for (const skill of skills) {
    const family = findTechnologyFamily(skill)
    if (family) {
      familyIds.add(family.id)
    }
  }
  return Array.from(familyIds)
}

"""Golden role: AI Solutions Architect (the live-experiment role).

This fixture encodes the exact failures the 2026-10-29 end-to-end run exposed,
so the clean architecture must get them right before anything ships:
  - all three cities survive (legacy collapsed to Hyderabad only);
  - a 15+ role is scoped at least staff/lead-level (legacy said "senior" and
    the gate then excluded genuine seniors);
  - the role-defining AI capability is enforced;
  - hybrid work-mode is disclosed as an un-filterable limitation, not dropped.
"""

from recruiter.evals.golden import GoldenRole

ROLE = GoldenRole(
    name="ai_solutions_architect",
    notes=(
        "AI Solutions Architect\n"
        "We are looking for an AI Solutions Architect with solid 15+ years of "
        "experience. The tech stack is Java and/or Python, but the candidate "
        "should have built and deployed AI solutions/products into Production. "
        "Should have a good amount of AI experience, especially with RAG, "
        "Langchain and related technologies. Experience with Cloud - Azure, AWS "
        "or GCP is required, however Azure would be preferred. This is a Hybrid "
        "role, and the candidate can be located anywhere in Hyderabad, "
        "Bengaluru OR Pune."
    ),
    boundary={
        "hiring_company": "",
        "country": "India",
        "work_mode": "hybrid",
        "cities": ["Hyderabad", "Bengaluru", "Pune"],
    },
    expect={
        "cities": ["Hyderabad", "Bengaluru", "Pune"],
        "min_seniority": "staff/lead",   # 15+ years must not read as plain "senior"
        "capability": "AI",
        "work_mode_disclosed": True,
        "has_core": True,
    },
)

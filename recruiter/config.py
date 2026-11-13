"""Central model configuration — the one place to pick models/providers.

Chosen from the offline matrix + Judge A/B (2026): off the retiring gpt-4 line,
onto Claude. Reader is high-ish volume and cheap on Haiku; the capability
proposer is rare+cached and the Judge is quality-critical, so both use Sonnet.
Model names route by provider automatically (see recruiter/llm/core.py), so
switching provider later is a one-line change here.
"""

READER_MODEL = "claude-haiku-5-5"       # intake Task A/B understanding
CAPABILITY_MODEL = "claude-sonnet-5-5"   # role-defining capability (rare, cached)
JUDGE_MODEL = "claude-sonnet-5-5"        # requirement verification (quality-critical)
SCREEN_MODEL = "claude-haiku-5-5"        # Tier-1 admission gate (high-volume, coarse, cheap)
CAREER_MODEL = "claude-sonnet-5-5"       # Tier-2 holistic career-fit read (quality-critical ranking driver)
OUTREACH_MODEL = "claude-sonnet-5-5"     # first-touch outreach drafting (tone-critical, recruiter edits before send)

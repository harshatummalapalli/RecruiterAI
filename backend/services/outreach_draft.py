"""First-touch outreach drafting (Phase 1, step 3).

Drafts a short LinkedIn connection note / InMail / email, grounded ONLY in the
evidence RecruiterAI already computed for this candidate and the role being
hired for. The model is told to use nothing but the facts it is handed, so a
draft can never invent a shared employer, a school, or a skill the candidate
doesn't have. The output is always a DRAFT the recruiter reviews and edits —
nothing is ever sent from here (see OutreachService for the send path).

A deterministic `fallback_draft` keeps the composer usable if the model call
fails, so a recruiter is never blocked from reaching out.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from recruiter.config import OUTREACH_MODEL
from recruiter.llm.core import complete_json

logger = logging.getLogger(__name__)

# Keep in sync with OutreachService.LINKEDIN_NOTE_CAP — the connection-note limit.
LINKEDIN_NOTE_CAP = 200


def _first_name(name: Optional[str]) -> str:
    return (name or "").strip().split(" ")[0] if (name or "").strip() else "there"


def _signals(evidence: Optional[Dict[str, Any]]) -> List[str]:
    """Up to four short, literal evidence quotes for this candidate — the real
    sentences MatchExplainer already verified, never a guess."""
    out: List[str] = []
    alignment = (evidence or {}).get("role_alignment") or {}
    for signal in (alignment.get("matched_signals") or []):
        text = (signal.get("evidence_text") or signal.get("signal_text") or "").strip()
        if text and text not in out:
            out.append(text)
        if len(out) >= 4:
            break
    return out


def _context(candidate: Dict[str, Any], evidence: Optional[Dict[str, Any]], role: Optional[Dict[str, Any]], recruiter_name: Optional[str]) -> Dict[str, Any]:
    evidence = evidence or {}
    role = role or {}
    return {
        "candidate_name": candidate.get("name") or "",
        "candidate_first_name": _first_name(candidate.get("name")),
        "current_title": candidate.get("title") or evidence.get("current_title") or "",
        "current_company": candidate.get("company") or evidence.get("current_company") or "",
        "evidence": _signals(evidence),
        "role_title": role.get("posted_title") or role.get("primary_title") or (role.get("role") or {}).get("primaryTitle") or "",
        "hiring_company": role.get("hiring_company") or role.get("company") or "",
        "recruiter_name": (recruiter_name or "").strip(),
    }


_CHANNEL_BRIEF = {
    "connect": (
        f"Write a LinkedIn connection-request note. HARD LIMIT {LINKEDIN_NOTE_CAP} characters "
        "including spaces — count them. One or two sentences. No subject. Warm, specific, not salesy; "
        "do not pitch the role in detail, just open a genuine conversation."
    ),
    "inmail": (
        "Write a LinkedIn InMail. 3–5 short sentences. A one-line subject that is specific, not clickbait. "
        "Lead with why THIS person, name the role plainly, end with a low-pressure ask to chat."
    ),
    "message": (
        "Write a short LinkedIn message to an existing connection. 2–4 sentences, friendly and direct. "
        "A subject is optional (may be empty)."
    ),
    "email": (
        "Write a recruiting email. A specific, plain subject line. 3–5 short sentences in the body: why this "
        "person, the role named plainly, a low-pressure ask. Sign off with the recruiter's name if given."
    ),
}


def _mode(channel: str, inmail: bool) -> str:
    if channel == "email":
        return "email"
    if channel == "linkedin" and inmail:
        return "inmail"
    if channel == "linkedin":
        return "connect"
    return "message"


def _system(mode: str) -> str:
    return (
        "You are a senior technical recruiter writing a first-touch outreach message. "
        "You are given, as JSON, only verified facts about ONE candidate and the role being hired for. "
        "Use ONLY those facts. Never invent a shared employer, school, mutual connection, skill, or achievement "
        "that is not in the input. If the evidence list is empty, write a warm, honest note based only on their "
        "current title/company and the role — do not fabricate specifics. Address them by first name. "
        "Be concrete and human; avoid clichés ('I came across your profile', 'rockstar', 'ninja') and flattery. "
        f"{_CHANNEL_BRIEF[mode]} "
        'Reply with ONLY a JSON object: {"subject": string, "body": string}. '
        "Use an empty string for subject when no subject applies."
    )


def draft_outreach(
    channel: str,
    *,
    candidate: Dict[str, Any],
    evidence: Optional[Dict[str, Any]],
    role: Optional[Dict[str, Any]],
    recruiter_name: Optional[str] = None,
    inmail: bool = False,
    model: str = OUTREACH_MODEL,
    client: Any = None,
) -> Dict[str, Any]:
    """Return {channel, subject, body, inmail, char_limit}. Raises on model/parse
    failure — the caller falls back to `fallback_draft`."""
    channel = (channel or "").strip().lower()
    mode = _mode(channel, inmail)
    ctx = _context(candidate, evidence, role, recruiter_name)
    data = complete_json(_system(mode), json.dumps(ctx), model, max_tokens=600, client=client)
    subject = str(data.get("subject") or "").strip()
    body = str(data.get("body") or "").strip()
    if not body:
        raise ValueError("Empty draft body from model.")
    if mode == "connect":
        subject = ""
        body = body[:LINKEDIN_NOTE_CAP]
    return {
        "channel": channel,
        "subject": subject,
        "body": body,
        "inmail": bool(inmail),
        "char_limit": LINKEDIN_NOTE_CAP if mode == "connect" else None,
    }


def fallback_draft(
    channel: str,
    *,
    candidate: Dict[str, Any],
    role: Optional[Dict[str, Any]] = None,
    recruiter_name: Optional[str] = None,
    inmail: bool = False,
) -> Dict[str, Any]:
    """A plain, factual draft when the model is unavailable — never blocks the
    recruiter from reaching out. Uses only name/title/role; invents nothing."""
    channel = (channel or "").strip().lower()
    mode = _mode(channel, inmail)
    ctx = _context(candidate, {}, role, recruiter_name)
    first = ctx["candidate_first_name"]
    role_title = ctx["role_title"] or "a role"
    company = ctx["hiring_company"]
    role_phrase = f"{role_title} role" + (f" at {company}" if company else "")
    sign = f"\n\n— {ctx['recruiter_name']}" if ctx["recruiter_name"] else ""

    if mode == "connect":
        body = (f"Hi {first} — I'm hiring for a {role_phrase} and your background stood out. "
                "Would love to connect.")[:LINKEDIN_NOTE_CAP]
        return {"channel": channel, "subject": "", "body": body, "inmail": bool(inmail), "char_limit": LINKEDIN_NOTE_CAP}

    cur = f" Your work as {ctx['current_title']}" + (f" at {ctx['current_company']}" if ctx["current_company"] else "") if ctx["current_title"] else ""
    body = (f"Hi {first},\n\nI'm hiring for a {role_phrase} and thought of you.{cur} looks like a strong fit. "
            f"Would you be open to a quick chat?{sign}")
    subject = "" if mode == "message" else (f"{role_title} opportunity" if role_title != "a role" else "A role you might like")
    return {"channel": channel, "subject": subject, "body": body, "inmail": bool(inmail), "char_limit": None}

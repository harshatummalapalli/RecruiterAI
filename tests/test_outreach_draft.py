"""Outreach drafting — grounded, length-capped, with a deterministic fallback.

Uses the same injected-client seam as the rest of the engine (complete_json's
`client=` path), so no network/model call happens in tests."""

import json

from backend.services.outreach_draft import LINKEDIN_NOTE_CAP, draft_outreach, fallback_draft

CANDIDATE = {"name": "Jane Doe", "title": "Staff Engineer", "company": "Acme"}
EVIDENCE = {"role_alignment": {"matched_signals": [
    {"evidence_text": "Led the migration of Acme's billing platform to event-driven services."},
    {"signal_text": "Kafka"},
]}}
ROLE = {"posted_title": "Principal Backend Engineer", "hiring_company": "Northwind"}


class FakeResp:
    def __init__(self, text):
        self.output_text = text


class FakeClient:
    """OpenAI-shaped double matching complete_json's injected-client path."""
    def __init__(self, payload):
        self._payload = payload
        self.last_input = None

    class _Responses:
        def __init__(self, outer):
            self._outer = outer

        def create(self, *, model, input, text):
            self._outer.last_input = input
            return FakeResp(json.dumps(self._outer._payload))

    @property
    def responses(self):
        return FakeClient._Responses(self)


def test_connect_note_has_no_subject_and_respects_cap():
    client = FakeClient({"subject": "ignored", "body": "y" * 400})
    draft = draft_outreach("linkedin", candidate=CANDIDATE, evidence=EVIDENCE, role=ROLE, recruiter_name="Alice", inmail=False, client=client)
    assert draft["subject"] == ""
    assert len(draft["body"]) == LINKEDIN_NOTE_CAP
    assert draft["char_limit"] == LINKEDIN_NOTE_CAP


def test_email_draft_keeps_subject_and_body():
    client = FakeClient({"subject": "A principal role at Northwind", "body": "Hi Jane,\n\nWould you chat?"})
    draft = draft_outreach("email", candidate=CANDIDATE, evidence=EVIDENCE, role=ROLE, recruiter_name="Alice", client=client)
    assert draft["subject"] == "A principal role at Northwind"
    assert draft["body"].startswith("Hi Jane")
    assert draft["char_limit"] is None


def test_draft_is_grounded_in_the_evidence_we_pass():
    client = FakeClient({"subject": "", "body": "ok"})
    draft_outreach("linkedin", candidate=CANDIDATE, evidence=EVIDENCE, role=ROLE, inmail=True, client=client)
    # The model is handed the real evidence quote + the role — nothing else to invent from.
    sent = json.loads(client.last_input[1]["content"])
    assert "Led the migration of Acme's billing platform" in sent["evidence"][0]
    assert sent["role_title"] == "Principal Backend Engineer"
    assert sent["candidate_first_name"] == "Jane"


def test_reply_mode_drafts_a_response_to_their_message():
    client = FakeClient({"subject": "", "body": "Great to hear from you, Jane — are you free Thursday?"})
    draft = draft_outreach("linkedin", candidate=CANDIDATE, evidence=EVIDENCE, role=ROLE, reply_to="Sounds interesting, tell me more.", client=client)
    assert draft["body"].startswith("Great to hear")
    sent = json.loads(client.last_input[1]["content"])
    assert sent["their_reply"] == "Sounds interesting, tell me more."   # the model is given what they said


def test_fallback_connect_is_capped_and_specific():
    draft = fallback_draft("linkedin", candidate=CANDIDATE, role=ROLE, recruiter_name="Alice", inmail=False)
    assert len(draft["body"]) <= LINKEDIN_NOTE_CAP
    assert "Jane" in draft["body"]


def test_fallback_email_has_subject_and_signoff():
    draft = fallback_draft("email", candidate=CANDIDATE, role=ROLE, recruiter_name="Alice R")
    assert draft["subject"]
    assert "Alice R" in draft["body"]

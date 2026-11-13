# Unipile Outreach — Phase 1 Scope & Isolation Model

**Status:** SPEC — ready to build. Live-validated against Unipile's API (connection request, message, email-send all fired successfully on 2026-11-12).
**Goal:** turn RecruiterAI from *find candidates* into *find → reach out → track replies*, with each recruiter acting through **their own** connected LinkedIn / email (and WhatsApp later) and **never** touching anyone else's.

---

## 0. What Phase 1 delivers
1. A recruiter connects **their** LinkedIn and email once (hosted auth).
2. From a shortlisted candidate: **connect request + note**, **message**, **email** — message/note AI-drafted from the evidence we already compute.
3. A **reply inbox**: inbound replies / email events flip a candidate `Not contacted → Invited/Emailed → Replied`.
4. Per-recruiter isolation enforced end to end (the rest of this doc).

WhatsApp is **not** in Phase 1 but the model below already accommodates it as "just another provider row" — no rework.

---

## 1. The isolation model — the spine (read this first)

### 1.1 The one rule
**A recruiter can only ever act through accounts they themselves connected, and inbound events only ever touch their own data.** The acting `account_id` is **never supplied by the client** — it is resolved server-side from the authenticated `owner_email` (the exact identity that fixed our cross-tenant leak — see [[owner-scoping-tenant-isolation]]). Outreach isolation is the *same contract* as our existing per-user scoping, extended to connected accounts.

### 1.2 Storage — one binding table, owner-keyed
New store `connected_accounts` (same sticky-owner pattern as the intake/search stores):

| field | notes |
|---|---|
| `owner_email` | the recruiter — our tenant key, from the session |
| `provider` | `linkedin` \| `google` \| `outlook` \| `whatsapp` (later) |
| `account_id` | Unipile `acc_xxx` |
| `status` | `running` \| `disconnected` \| `errored` … (kept fresh from `account.status.*` webhooks) |
| `connected_at` | |

Unique on (`owner_email`, `provider`). Single resolver used by **every** outreach call:
```
account_for(owner_email, provider) -> account_id | None   # ALWAYS filtered by owner_email
```

### 1.3 Connect flow (hosted auth) — binds the account to the right recruiter
Credentials never touch our servers; the hosted page handles them. **No vendor is
ever exposed:** the page is served on our **white-label host**
`connect.dayzero.partners` via the auth-link `domain` param (set
`UNIPILE_HOSTED_AUTH_DOMAIN`). PREREQUISITE (one-time, owner): verify that subdomain
with Unipile (DNS + their dashboard); until then the link falls back to the vendor
host. (A fully in-modal "native auth" path exists — `/v2/auth/intent` — but was
declined to keep us out of the LinkedIn credential path.) Connecting Gmail/Outlook
still uses the recruiter's own provider OAuth (Google/Microsoft), which is expected.

1. Recruiter (session `owner_email = R`) clicks **Connect LinkedIn**.
2. Backend mints a **single-use, opaque connect token** `t`, stores `t → R` (short TTL, e.g. 15 min), and calls `POST /v2/auth/link`:
   - `providers: ["LINKEDIN"]` (or `GOOGLE` / `OUTLOOK` / `WHATSAPP`)
   - `redirect_uri: https://hire.dayzero.partners/connect/callback`
   - **`state: t`** — our opaque token (never the raw email; leaks nothing if seen)
   - `expires_on`: now + 15 min
3. Recruiter authenticates on Unipile's hosted page.
4. On success Unipile BOTH: redirects to our callback with `account_id`, `provider`, `state=t`; **and** fires the `account.add` webhook carrying `account_id`, `provider`, `state=t`.
5. Backend binds from the **webhook** (server-to-server, unspoofable by a browser): look up `t → R` (must be valid, unused, unexpired) → write `{owner_email: R, provider, account_id}` → consume `t`. The browser redirect is UX only. An unknown/expired `t` is rejected.

`state` is simultaneously the **anti-CSRF nonce** and the **recruiter binding key**. This is the whole isolation hinge.

### 1.4 Every outbound call is owner-resolved
Endpoints like `POST /outreach/{candidate_id}/connect|message|email` take **no `account_id` from the client**. Handler:
```
owner = session.owner_email
acc   = account_for(owner, 'linkedin')     # or email provider
if not acc: return "Connect your LinkedIn first."
unipile.relation_request(acc, target_user_id, note)   # acts as THIS recruiter only
```
A malicious client cannot pass someone else's `account_id` — it is never read from input.

### 1.5 Inbound (webhooks) routed by account → owner
One endpoint `/webhooks/unipile` (registered once via `POST /v2/webhooks/endpoints/`). Every event carries `account_id`; we map `account_id → owner_email` via `connected_accounts` and apply the event **only** to that owner's candidates/outreach. An event whose `account_id` isn't in our store is **dropped**. A reply to recruiter A's LinkedIn can only ever update A's candidates.
- **Verify webhook authenticity** (Unipile's webhook secret/signature) so a forged POST to `/webhooks/unipile` can't inject events.

### 1.6 Threat table
| Attempt | Why it fails |
|---|---|
| Recruiter B acts as A's LinkedIn | `account_id` resolved from B's `owner_email` only; never from input |
| Forged / replayed connect callback | `state` token must map to a real pending recruiter and is consumed once |
| Webhook for an account we don't own | dropped (not in `connected_accounts`) |
| Forged webhook POST | rejected by signature/secret check |
| Shared machine / stale session | governed by our existing session `owner_email` scoping |

### 1.7 Defense-in-depth (optional, recommended as we add seats)
Phase 1 uses **one server-side app Account API Key** (in `/etc/recruiterai.env`) and isolates in our DB (§1.2–1.5). To add a hard second layer, create a Unipile **Scope per recruiter** and assign their accounts to it (`POST /v2/scopes/`, `account_scope_id` on the account). Then even a server-side bug using the wrong `account_id` is rejected by Unipile. Not required for correctness in Phase 1; worth it beyond a handful of seats. (The scoped key we used for MCP testing is **test-only** and not the production key.)

### 1.8 WhatsApp later — no rework
Same flow: a `whatsapp` row in `connected_accounts`, connected via the same hosted-auth call (WhatsApp uses QR on Unipile's page). Messaging/isolation identical. The only new work later is the WhatsApp message action + its inbound event type.

---

## 2. Components to build
1. **`backend/providers/unipile.py`** — thin client (shape of `harvest.py`), server-side key from env. Methods, all taking `account_id`: `list_accounts`, `get_profile`, `search_people`, `relation_request`, `start_chat`, `send_message`, `list_chats`, `send_email`, `create_auth_link`, `create_webhook`.
2. **`connected_accounts` store** + `account_for(owner, provider)` resolver (§1.2).
3. **Connect flow** — `POST /connect/link` (mint `t`, call auth-link, return hosted URL) + `GET /connect/callback` (UX) + the `account.add` webhook binding (§1.3).
4. **Outreach actions** — `POST /outreach/{candidate}/{connect|message|email}`, owner-resolved (§1.4); candidate gains an **outreach state** (`not_contacted → invited|emailed → replied`). Message/note **AI-drafted** from the candidate's computed evidence.
5. **Webhook endpoint** `/webhooks/unipile` — verify signature, route by `account_id → owner`, update outreach state + account status (§1.5).

---

## 3. Verified endpoints (fired live 2026-11-12)
| Action | Endpoint | Proven |
|---|---|---|
| List accounts | `GET /v2/accounts/` | ✅ |
| Hosted auth link | `POST /v2/auth/link` (`state` = recruiter binding) | schema ✓ |
| Resolve/enrich a person | `GET /v2/{account_id}/users/{identifier}` | ✅ (incl. `can_send_inmail`) |
| People search | `POST /v2/{account_id}/linkedin/search/people` | ✅ |
| Connection request + note | `POST /v2/{account_id}/users/me/relation-requests` `{user_id, message}` | ✅ sent + accepted |
| First message (+ InMail flag) | `POST /v2/{account_id}/chats/send` `{text, users_ids, specifics.linkedin.classic.inmail}` | schema ✓ |
| Reply in thread | `POST /v2/{account_id}/chats/{chat_id}/messages/send` | schema ✓ |
| Send email (+ tracking) | `POST /v2/{account_id}/emails/send` `{to[], subject, html, tracking_options}` | ✅ sent + replied |
| Webhook register | `POST /v2/webhooks/endpoints/` | schema ✓ |

Base URL `https://api.unipile.com`; auth header `X-API-KEY`.

---

## 4. Guardrails (baked in from day one)
- **Account safety is a product constraint, not a setting.** Per-recruiter daily caps (≈20–25 connection requests/day; throttled messages), warm-up on a newly connected account, never bulk-blast. (Unipile adds its own rate-limiting/caching; we add ours on top.)
- **Connection-note cap** ≈200 chars — enforce + truncate (we hit this live).
- **Seat reality:** the test LinkedIn seat **can't InMail**; Gmail send works. Phase 1 outreach = *connect+note* and *email*. InMail becomes available if a recruiter connects a Premium/Sales Nav seat (we already read `can_send_inmail` per profile to decide).
- **PII:** messages/replies become data we store — treat like the candidate PII we already guard (gitignored output, owner-scoped).

---

## 5. Secrets / config
- `UNIPILE_API_KEY` (server-side app Account key) + `UNIPILE_BASE_URL` (default `https://api.unipile.com`) + `UNIPILE_WEBHOOK_SECRET` + `UNIPILE_HOSTED_AUTH_DOMAIN` (white-label connect host) — all in `/etc/recruiterai.env` only, never the repo. The MCP test key stays out of production.
- **Deploy note:** the new `/integrations/*` routes must be added to the nginx proxy regex on the server (see [[production-deployment]] — new backend routes otherwise fall through to the SPA).

---

## 6. Build order (within Phase 1)
1. `unipile.py` client + `connected_accounts` store + resolver (foundation; unit-testable with a fake client).
2. Connect flow (auth-link + callback + `account.add` binding) — the isolation core.
3. Outreach actions on the candidate (connect / message / email) + outreach state.
4. Webhook endpoint (replies / status) → reply inbox.

Each step ships on its own and is validated live against the Unipile MCP as we go.

---

## 7. Open decisions
- **Where recruiters connect:** Settings (standalone) vs inline on first "Reach out". Lean **Settings**, with an inline nudge from the candidate action.
- **Defense-in-depth now or later:** per-recruiter Unipile Scopes (§1.7) — recommend **later**, once past a few seats.
- **Draft tone:** fully AI-drafted vs template-with-AI-fill for the first message/note (default: AI-drafted from evidence, recruiter edits before send).

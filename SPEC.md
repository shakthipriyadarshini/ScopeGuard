ScopeGuard: SPEC.md

> Paste this file at the start of every Claude session, together with your folder tree.
> Update the Status section at the bottom after each working step.

## 1. What this is
ScopeGuard is an AI-powered agreement and payment layer for freelancers, built solo for the
PayPal AI Hackathon (Devpost). It turns a project description into a structured agreement,
gets the client's approval through an invite link, detects when a new client request falls
outside the approved scope, and collects milestone and change-request payments through
PayPal. PayPal checkout is central to the product, and AI is the differentiator.

Not an escrow service. Not legal advice. AI output is always a draft that a human confirms.

## 2. Stack
- Backend: Python Flask, SQLAlchemy, SQLite, Pydantic
- Frontend: Jinja templates, Tailwind via CDN, vanilla JS (no React)
- AI: Gemini API (google-genai SDK), model name in env var `GEMINI_MODEL` [FILL: model name]
- Payments: PayPal Orders v2 REST API (sandbox, USD) + PayPal JS SDK button
- All free tiers only. No paid services.

## 3. Hard rules (never break)
1. Money is stored as **integer cents**. Send amounts to PayPal as strings like `"60.00"`.
2. The payment amount is **always read from the database**, never from the request.
3. Secrets come only from environment variables (`.env`, git-ignored). Never hardcode or log them.
4. AI never decides prices, approves anything, or rejects client requests. Humans decide.
5. User text and AI text are treated as data. Jinja autoescape stays on; no `|safe`.
6. Every route checks ownership (freelancer) or the invite token (client).
7. Do only the step requested. No extra features, frameworks or auth systems.
8. Keep code simple and readable so I can explain every line.

## 4. Folder structure [FILL: update if yours differs]
```
scopeguard/
  backend/
    app/
      __init__.py          # app factory
      models.py
      routes/ auth.py projects.py client.py changes.py payments.py
      services/  paypal_service.py
      
      templates/ base.html login.html project.html projects.html
                 review.html client.html changes.html
      static/
    config.py
    run.py
    seed.py
    requirements.txt
  .env.example
  .gitignore
  LICENSE  (MIT)
  README.md
  SPEC.md
```

## 5. Data model
| Table | Fields |
|---|---|
| User | id, name, email, password_hash (freelancer only) |
| Project | id, title, client_name, description, status (DRAFT/ACTIVE), invite_token, freelancer_id |
| Agreement | id, project_id, version, scope_json, budget_cents, status (DRAFT/PENDING_CLIENT/ACTIVE/SUPERSEDED), content_hash, approved_at |
| Milestone | id, project_id, title, amount_cents, status (PENDING/PAID), agreement_version, kind (ORIGINAL/CHANGE), change_request_id nullable |
| ChangeRequest | id, project_id, request_text, ai_analysis_json, extra_cost_cents, extra_days, status (PENDING_CLIENT/APPROVED/REJECTED), created_at |
| Payment | id, milestone_id, paypal_order_id, capture_id, amount_cents, currency, status (CREATED/CAPTURED/FAILED), request_id, created_at |

- `invite_token` = `secrets.token_urlsafe(24)`, created when the project is published.
- `content_hash` = sha256 of canonical scope_json + budget_cents.
- Agreements are versioned, never overwritten. Only one version is ACTIVE; older ones become SUPERSEDED.

## 6. Main flow (this is also the demo video)
1. Freelancer enters a project description. Gemini returns a structured draft.
2. Freelancer reviews and edits it, enters or confirms the budget, and publishes it.
   Agreement v1 becomes PENDING_CLIENT and an invite link is created.
3. Client opens `/c/<token>`, reviews, and approves. Agreement v1 becomes ACTIVE and
   milestones are created from the percentages. The last milestone gets the rounding remainder.
4. Client pays the advance through PayPal sandbox.
5. Freelancer pastes a new client request into the scope check. Gemini classifies each
   requested item as included / not included / needs clarification, with reasons.
6. Freelancer creates a change request with an extra price and days. Client approves it.
   This creates Agreement v(n+1) as ACTIVE (previous becomes SUPERSEDED, deliverables appended,
   budget increased) and adds a CHANGE milestone for the extra amount. Client pays it through
   PayPal. If the client rejects it, nothing changes.
7. Dashboard shows the financial overview.

Demo numbers: $200 total, advance $60 (30%), change request $30.

## 7. Routes
| Method | Path | Who | Purpose |
|---|---|---|---|
| GET/POST | /login | freelancer | session login |
| GET | /dashboard | freelancer | projects and financial overview |
| GET/POST | /projects/new | freelancer | description in, AI draft out |
| GET/POST | /projects/<id>/review | freelancer | edit and publish agreement |
| GET | /projects/<id> | freelancer | project, milestones, change requests |
| POST | /projects/<id>/scope-check | freelancer | analyze a pasted client request |
| POST | /projects/<id>/changes | freelancer | create a change request |
| GET | /c/<token> | client | agreement, milestones, change requests |
| POST | /c/<token>/approve | client | approve the agreement |
| POST | /c/<token>/changes/<id>/approve | client | approve a change request |
| POST | /c/<token>/changes/<id>/reject | client | reject a change request |
| POST | /api/payments/create-order | client (token) | create a PayPal order |
| POST | /api/payments/capture-order | client (token) | capture and verify |
| GET | /api/payments/status/<milestone_id> | either | payment status |

## 8. AI workflows

### 8.1 Agreement generation
- Input: free-text project description. Output validated by Pydantic `AgreementDraft`:
  `project_title`, `deliverables` (1-15), `exclusions`, `budget_usd` (None if not stated),
  `timeline_days` (None if not stated), `milestones` [{name, percentage}] summing to exactly 100.
- Structured JSON output from Gemini. Retry once on validation failure, then show a friendly error.
- Never invent a budget. The freelancer must enter or confirm it.
- The description is wrapped in delimiters and treated as data. Instructions inside it are ignored.

### 8.2 Scope check
- Input: the current ACTIVE agreement (deliverables, exclusions, timeline) and the pasted client request.
- Output validated by Pydantic `ScopeAssessment`:
  - `overall`: within_scope / potential_scope_change / needs_clarification
  - `items`: list of {requested_item, classification (included / not_included / needs_clarification),
    matching_deliverable (nullable), reason}
  - `recommendation`: short text. If any item is not_included, suggest creating a change request.
- It is explainable: always show the original requirement, the new request, and the reason.
- Show qualitative reasons only. No fake confidence percentages.
- It is advisory. The freelancer makes the final decision.
- Minor tweaks inside an agreed deliverable (for example a colour change) should be classified
  as included or needs_clarification, not as a new deliverable.

## 9. PayPal integration
- Backend uses `requests` (no PayPal SDK). Cache the access token until it expires.
- `create-order`: load the milestone from the DB, reject if PAID or not owned by the token's
  project, or if its agreement is not ACTIVE. Create the order with `intent=CAPTURE`, the amount
  from the DB, `custom_id` = milestone id, and a `PayPal-Request-Id` header. Store a Payment (CREATED).
- `capture-order`: find the Payment by order id (reject unknown ones). If already CAPTURED, return
  success (idempotent). Otherwise capture, verify status COMPLETED and that amount and currency equal
  the DB milestone, then in one transaction mark the Payment CAPTURED (with capture_id) and the
  milestone PAID. On verification failure, mark FAILED.
- The browser never sees the PayPal secret. Only the client id is passed to the page.
- Test with the sandbox **personal (buyer)** account, not the business account.
- Optional, only if time permits: webhook `PAYMENT.CAPTURE.COMPLETED` with signature verification.

## 10. Dashboard financial overview
Original budget (v1), approved extras (sum of approved change requests), revised project value
(current ACTIVE agreement budget), payments captured, remaining balance. All computed from the DB.

## 11. Environment variables (`.env.example`)
```
PAYPAL_CLIENT_ID=
PAYPAL_CLIENT_SECRET=
PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com
GEMINI_API_KEY=
GEMINI_MODEL=
SECRET_KEY=
DATABASE_URL=sqlite:///scopeguard.db
```

## 12. Out of scope (do not build)
React, JWT, client accounts, webhooks (until everything else works), email notifications,
PDF export, activity log, escrow, PayPal Agent Toolkit, AI price or timeline estimates.

## 13. Hackathon deliverables
Public GitHub repo with a visible MIT license, README (setup, env vars, test accounts,
architecture), working demo (hosted or runnable locally), public YouTube video under 3 minutes
showing the full flow with no copyrighted music, and a Devpost text description.
Deadline: Nov 12, 2026, 12:00 PM Pacific (Nov 13, 1:30 AM IST). Aim to submit on Nov 12 evening IST.

## 14. Status (update after each step)
- [* ] Day 0: repo, license, PayPal sandbox accounts, Gemini key, smoke tests
- [* ] Day 1: foundation, login, milestones, PayPal create and capture working
- [ ] Day 2: Gemini agreement, review and publish, client portal, approval, client pays
- [ ] Day 3: scope check, change request, v2 agreement, change payment, dashboard
- [ ] Day 4: polish, hardening, README, demo video, Devpost draft
- [ ] Nov 12: buffer, final fixes, submit
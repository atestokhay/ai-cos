# AI-COS V1 — API Specification

> **Scope limit:** This document defines the API's responsibilities, some interactions and its security requirements. It does not define a complete REST endpoint inventory, HTTP methods and paths, or JSON request and response schemas. Defined contract requirements are therefore kept separate from endpoints that still need design. Undefined routes are not presented as a final API.

## 1. API responsibilities

API (`apps/api`) responsibilities:
- Authentication.
- Receiving founder commands.
- Querying structured records.
- Live updates.
- Approval endpoints.
- The single point of communication between the PWA and the backend.

The API:
- Makes no business policy decisions.
- Makes no model calls.
- Does not run tools directly.
- Holds no Gateway credentials.
- Gives no secrets or provider tokens to the browser.

Model and tool operations run through the Gateway and Tool Registry.

## 2. Authentication and sessions

Requirements:
- Sign-in with WebAuthn passkeys.
- Fresh user verification before approval, budget edits and passkey changes.
- At least two registered passkeys (a phone plus a second device or security key).
- The founder must store offline recovery codes.
- If all passkeys are lost, a documented break-glass recovery through the core server console is required.
- Short sessions.
- Secure cookies.
- CSRF protection.
- Strict Content Security Policy.
- A rate limit on every endpoint.
- No secrets or tokens in browser storage.
- A passkey's private key never leaves the device; the server stores the public key.

### API authentication behavior
- Unauthenticated requests to protected endpoints are rejected.
- Authorization checks happen server-side.
- Access control applies even when a Workspace or project ID comes from the client.
- For approval, the passkey assertion must be bound to the payload hash and request ID.

> Exact authentication routes and WebAuthn challenge and response JSON schemas are not defined yet: **DESIGN REQUIRED**.

## 3. API resource contracts

### 3.1 Command submission
The Command interface is defined as typed submission, not as a free-form chat thread.

Command types to support:
- New project specification.
- Existing project amendment.
- Clarification answer.
- One-off question to the Orchestrator.
- Structured control command: pause, resume, cancel, priority.

Rules:
- A new specification stores the original text verbatim.
- Draft autosave is supported.
- Markdown import and file attachments are required.
- The SpecVersion number and hash are shown after submission.
- An amendment creates a new SpecVersion and a change request.
- The answer to a question is presented as a Report record.
- Status queries are answered from records, without a model call where possible.
- Control commands are structured actions, not left to natural-language interpretation.

### 3.2 Project and Workspace queries
Data the PWA's project screen must show:
- Lifecycle stage and next gate.
- Specification versions and differences.
- Requirement ledger, quote anchors and assumption flags.
- Plan, task graph and department distribution.
- Evidence: test, build, review, artifacts.
- Cost: breakdown by task, department and tier.
- Timeline: events and decisions.
- Releases.

Workspace rules:
- The user can select an active Workspace.
- A project explicitly named in a message takes precedence over the active Workspace.
- For an ambiguous target, the Orchestrator requests clarification.
- Every API operation performs a Workspace authorization check.

### 3.3 Approval operations
Approval detail view:
- Code-generated action summary.
- Target.
- Reversibility.
- Cost.
- Payload binding.
- Evidence links.
- Agent explanation (labeled unverified).
- Expiry.

Operations:
- Reject.
- Approve with a passkey.
- Clarification or change request, where needed.

Rules:
- Approval is bound to the canonical payload hash.
- The passkey challenge is derived from the request ID and payload hash.
- Approval must be single-use and expiring.
- A changed payload invalidates the approval.
- Expired or revoked approvals are rejected.
- There is no L3 batch approval.
- Approvals are not queued offline.

### 3.4 Task and run queries
On the task detail screen:
- TaskAssignment.
- Reports.
- Review records.
- Evidence.
- Run history and cost.
- Redacted step trace.

Founder actions:
- Cancel.
- Retry.
- Add a note (as a record).

Task state is not changed by a model response coming through the API; the runtime state machine manages it.

### 3.5 Department and Agent status
Company screen requirements:
- Department cards and goals.
- Agent list, version and status.
- Department scorecards.
- Open proposals.
- Agent and department pause action.
- Agent definitions shown read-only.

### 3.6 Budget and usage
To display:
- Budget meter: run, task, project, department, day, month.
- Token usage by tier.
- Cache hit ratio.
- Month-end projection (labeled as an estimate).
- Manually entered fixed costs.
- Provider balance (not assumed to be readable through an API; checked by the founder).

Changing a budget cap needs a passkey step-up, and L4 governance policy changes belong to the founder. The authority shown in the UI and API must match the gateway policy.

### 3.7 Reports and audit
Reports:
- Completion reports.
- Weekly digest.
- Cost report.
- Security report.

Activity and audit:
- Searchable events.
- Verdicts.
- Approvals.
- Audit-chain integrity status.
- The audit view is read-only.

### 3.8 Settings
- Devices and passkeys.
- Sessions.
- Notification categories and quiet hours.
- Autonomy lease check-in.
- Add or revoke a passkey.

## 4. Live updates and notifications

Defined behavior:
- Server-Sent Events (SSE) keep an open screen up to date.
- SSE fallback: slow refresh.
- Web Push: approvals, blocked escalations, budget thresholds, health alerts, completions.
- Other notifications go into a daily digest.
- Notification categories and quiet hours.
- The PWA shell is readable offline.
- No action runs while offline; approvals are not queued offline.

> SSE event names, payload schemas, retry and resume cursor and Push payload formats are not defined yet: **DESIGN REQUIRED**.

## 5. Error and security behavior

Defined behavior:
- Unauthenticated requests are rejected.
- Authorization is applied server-side.
- Every endpoint has a rate limit.
- CSRF protection.
- Strict CSP.
- Secure cookies and short sessions.
- No tokens or secrets in browser storage.
- Workspace access is verified on every request.
- An operation with a mismatched approval payload hash is rejected.
- Expired or revoked approvals are rejected.
- Governance policy applies default deny.
- An unknown tool or argument pattern is rejected as L4.
- A tool call does not run without a gateway verdict.
- Timeouts and idempotency apply to tool and model calls.
- API and worker do not directly hold provider, GitHub or runner secrets.

### Error response standard
A common error JSON format, HTTP status mapping and error code catalog are not defined yet.

The following must be decided during API design:
- Authentication failure response.
- Authorization or Workspace mismatch response.
- Validation failure response.
- Approval expired, revoked or hash mismatch response.
- Budget exhausted response.
- Emergency stop active response.
- Rate limit response.
- Provider or runner unavailable response.
- Conflict or idempotency response.
- Internal error correlation ID format.

HTTP status codes for these cases are deliberately not given here; they are not defined yet.

## 6. Endpoint inventory — design required

The rows below show functional API areas. Exact HTTP methods and paths are **not defined yet**.

| Area | Function | Status |
|---|---|---|
| Authentication / Passkeys | Sign-in, register, revoke, session | Function defined; route and schema to be designed |
| Command submission | Specification, amendment, question, control command | Function defined; route and schema to be designed |
| Projects | Project overview, spec, requirements, plan, evidence, cost, timeline, releases | Data and views defined; route and schema to be designed |
| Workspace selection | Active Workspace selection and context resolution | Function defined; route and schema to be designed |
| Clarifications | Clarification list, answer, defer | Function defined; route and schema to be designed |
| Tasks | Task list and detail, cancel, retry, note | Function defined; route and schema to be designed |
| Approvals | Inbox, detail, approve, reject | Function defined; payload-bound passkey approval required |
| Departments | Department status, goals, pause | UI requirement defined; route and schema to be designed |
| Agents | Agent list, version and status, pause | UI requirement defined; route and schema to be designed |
| Budget / Usage | Scope meters, token and cost reports, cap management | Function defined; route and schema to be designed |
| Reports | Completion, weekly, cost, security reports | Function defined; route and schema to be designed |
| Activity / Audit | Events, verdicts, approvals, chain integrity | Function defined; route and schema to be designed |
| Notifications | Push subscription, categories, quiet hours | Function defined; route and schema to be designed |
| Live updates | SSE stream | Technology defined; event contract to be designed |
| Emergency stop | Stop, status and resume flow | UI and safety behavior defined; route and schema to be designed |

## 7. Request and response schemas — contracts not yet defined

The following JSON schemas and exact field sets are not defined yet:
- Command submission request and response.
- Project and Workspace response.
- Clarification answer.
- TaskAssignment.
- Full JSON schemas for Report, Blocked, ReviewRequest, ReviewResult, Escalation and Proposal payloads.
- Approval request, approval assertion and rejection.
- Budget edit.
- Agent and Department status.
- SSE event envelope.
- Push notification payload.
- Error response.

These must be designed as versioned typed schemas under `core/contracts`. Only conceptual typed record names are defined at this point; missing fields must not be filled in by guessing.

## 8. Idempotency and operation safety

- Jobs and tool calls carry an idempotency key.
- External adapters such as Git push, deploy and messaging record the intent before the operation and the result after it.
- Before a retry, the previous intent and result are checked.
- Approval is single-use and bound to the payload hash.
- The idempotency requirement and key scope for API mutation endpoints must be designed separately.
- A production deploy request must exactly match the approved commit, version and target.

## 9. API acceptance criteria

- [ ] Protected endpoints cannot be reached without a passkey-based session.
- [ ] Operations requiring fresh user verification ask for step-up verification.
- [ ] Every endpoint is rate-limited.
- [ ] CSRF protection and CSP are in place.
- [ ] No secrets or tokens are kept in the browser.
- [ ] Workspace and project authorization is verified server-side.
- [ ] Command submission produces a typed record.
- [ ] A specification is stored with its original text and hash.
- [ ] Approval is bound to the payload hash and is single-use.
- [ ] Approval does not work offline.
- [ ] SSE and push connections are authorized.
- [ ] The API does not make model or tool calls directly.
- [ ] The API carries no worker or gateway secrets.
- [ ] Task state is updated only by the runtime.
- [ ] The error schema, status mapping and endpoint contracts are defined in `core/contracts` before implementation.

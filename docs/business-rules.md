# AI-COS V1 — Business Rules

> This document defines the target business rules of AI-COS V1, including behavior that is not implemented yet.

## 1. Founder and system authority

- The founder has final authority over strategy, product design, spending, publishing and policy.
- The Orchestrator is the founder's execution and coordination layer; it is not a co-designer of the product.
- The Orchestrator cannot change the founder's specification or approve its own work.
- Governance is under the founder's control; the Orchestrator and Managers cannot change governance policy.
- Agents may make suggestions; an unaccepted suggestion cannot become work or a product requirement.

## 2. Specification and requirement rules

1. The original specification submitted by the founder is stored verbatim and versioned.
2. An existing SpecVersion cannot be changed; a change creates a new version.
3. Each Requirement carries a quote or anchor from the founder's text.
4. A Requirement without a source quote is marked `assumption` and cannot become an acceptance criterion without founder approval.
5. Ambiguity, contradiction, missing information or an infeasible requirement is not filled in by guessing; it is put to the founder as a Clarification.
6. The founder's answer is recorded as a new SpecVersion or amendment.
7. Agent improvement suggestions are recorded as Proposals and do not enter scope until the founder accepts them.
8. The release report links each Requirement to a Task, Test and Evidence, and explicitly lists unmet requirements.

## 3. Command and Workspace resolution

- The founder uses a single Orchestrator interface.
- If an active Workspace is selected, it is the default task context.
- If the founder's message explicitly names another project, that project takes precedence over the active Workspace.
- If the project is ambiguous, the Orchestrator asks for clarification before changing files or starting tasks.
- Every Task, Job, Artifact and project-scoped record must carry the correct Project/Workspace identity.
- A Workspace ID alone does not grant access; every operation also passes an authorization check.
- A Workspace's secrets, repository, database, memory or deployment information cannot move to another Workspace.
- Each project uses its own Workspace, repository, database project, environment and deployment configuration.

## 4. Hierarchy and task assignment

### 4.1 Assignment authority
| Sender | Receiver | Allowed |
|---|---|---|
| Founder | Orchestrator | Specification or command |
| Orchestrator | Department Manager | Yes, with TaskAssignment |
| Manager | Its own specialists | Yes, with TaskAssignment |
| Manager | Another department | Not directly; Escalation or ReviewRequest to the Orchestrator |
| Specialist | Any agent | No; Report, Blocked or Proposal to its own Manager |
| Workflow Engine | Another department's gate in an approved plan | Yes, within a pre-planned and logged gate |

### 4.2 Orchestrator
- Receives the request, resolves the Workspace and analyzes the specification and requirements.
- Directs any Clarification to the founder.
- Prepares the brief, task graph, department participation and plan.
- Requests estimates and plans from Managers.
- Assigns the approved plan to Managers.
- Tracks dependencies, blockers and cross-department coordination.
- Produces the completion report from records and evidence.
- Does not directly micromanage specialist tasks.
- Cannot invent requirements, change the specification or approve its own work.

### 4.3 Manager
- Breaks the project goal into subtasks for its own department.
- Assigns tasks, dependencies and deadlines to its own specialists.
- Assigns only within the approved plan's scope and budget envelope.
- Reviews outputs on the basis of evidence.
- Requests at most two revision rounds, then escalates.
- Marks blocked tasks and raises them to the Orchestrator.
- Can narrow the task types of its own specialist definitions or disable an agent.
- Cannot assign tasks to another department's staff.
- Cannot expand tool allowlists, permissions, budgets or another department's scope.
- Cannot grant its own acceptance.

### 4.4 Specialist
- Works only within its assigned Task and tool allowlist.
- Cannot assign tasks to another specialist.
- Cannot escalate its own privileges.
- Passes output to its own Manager as a structured Report, Blocked or Proposal.
- A model's or agent's claim of success is not task completion on its own.

## 5. Department responsibilities

### Engineering
- Technical design, implementation, testing, build and release candidates.
- Produces pull requests, test and build evidence, and release notes.
- Cannot change requirements.
- Cannot deploy to production without founder approval.

### Cybersecurity
- Security checks of the company's own code, dependencies, secret exposure, infrastructure and accounts.
- Produces secure development checklists, review results, vulnerability reports and hardening proposals.
- Tests only assets on the authorized-assets list.
- Security audit or penetration testing services for outside parties are out of V1 scope.

### Creative & Design
- A detailed responsibility matrix for this department is not defined yet; separate playbooks and acceptance criteria must be defined when UI/UX, brand and visual production tasks are designed.
- No definitive tool list or automatic publishing authority is assumed for this department.

### Business
- Budgeting, product economics, pricing research, cost estimation and reporting.
- Presents spending increases or subscription needs as a Proposal or Approval Request.
- Cannot spend money, change budgets or edit CostLedger records.

### Marketing
- Positioning, store and landing copy, launch plans and analytics summaries.
- Can prepare content and campaign drafts.
- Cannot publish content or send messages externally outside approved automation scope.

### R&D
- Part of the long-term organization; it does not have to be fully active in the first operational release.
- Produces feasibility memos, technology comparisons and prototypes.
- Cannot adopt a technology into a product on its own.

## 6. Task lifecycle and working rules

### 6.1 Task state
- `proposed` → `ready` → `running` → `in_review` → `accepted`
- Side states: `blocked`, `revision`, `failed`, `cancelled`
- `revision` returns to `ready`, for at most two rounds.
- Only the runtime changes task state; a model response does not.
- `accepted` requires evidence and review.

### 6.2 Run state
- `queued` → `leased` → `running`
- Terminal states: `succeeded`, `failed`, `timed_out`, `cancelled`, `lost`

### 6.3 Worker and retry
- A worker takes jobs from the PostgreSQL queue with a lease.
- Claiming uses a row lock and `SKIP LOCKED`.
- A heartbeat renews the lease.
- Retries happen only for reasons such as a transient provider or server error, or a lost worker.
- At most 3 attempts, with exponential backoff and jitter.
- Policy denials and validation failures are not retried.
- Every job and tool call carries an idempotency key.
- An adapter with external effects checks its intent and result record before a retry.
- The execution model is at-least-once; exactly-once is not guaranteed.
- The cancel flag is checked at every step and heartbeat.
- After an expired lease, the run continues if the last committed step is trustworthy; otherwise it restarts from the beginning.
- When the attempt limit is reached, the job becomes dead and an escalation goes to the Manager.

### 6.4 Agent communication
- Agents do not chat freely with each other; they exchange typed records and artifacts.
- Text from another agent or an external source is presented as quoted, labeled, untrusted data.
- Agents report only along their own reporting lines.
- Model output does not become a record until it passes schema validation.

## 7. Project lifecycle

1. Project registration: the founder's command is the authority to open a record.
2. Specification preservation: the original text is stored as an immutable SpecVersion.
3. Requirement analysis: each requirement is extracted with a quote anchor; assumptions are marked separately.
4. Clarification: the plan waits until blocking questions are answered.
5. Brief: goal, in and out of scope, platform, constraints and requirement-based acceptance criteria.
6. Department selection: the required departments are identified.
7. Plan and task graph: tasks, dependencies, budget envelope, model and infrastructure estimates and risks are prepared.
8. Founder plan approval: brief, plan and spending cap are approved in a single L3 decision.
9. Assignment: each task is linked to at least one Requirement.
10. Implementation: branch, patch, PR and artifact production in a sandbox.
11. Progress: dependencies and blockers are tracked.
12. Independent review: the reviewer cannot be the author; the same or a higher tier is required.
13. Evidence collection: CI, build and test results come from real system records, not agent summaries.
14. Release plan: release notes, a deployment plan and a rollback plan are mandatory.
15. External or irreversible action: requires founder approval.
16. Completion report: artifacts, evidence, traceability matrix, unresolved issues and a cost/cap report.

## 8. Completion criteria

A workflow can reach completion only when:
- Every approved Requirement is linked to at least one Task and Evidence, or is explicitly listed as unmet.
- CI passes on the exact merge commit.
- The authoring agent did not control the CI run.
- An independent ReviewResult exists for every L2 change.
- No Critical or High security finding is open, or the founder has accepted it in writing.
- Artifacts are stored with a hash.
- Cost is within the cap, or the overrun has been separately approved.
- A rollback plan exists for the release.

## 9. Governance and permission rules

### 9.1 Governance principles
- Governance is independent of agents and the Orchestrator.
- Code makes the decisions; a model is not the final policy authority.
- Default deny applies.
- An unknown tool or argument pattern counts as L4.
- Effective tool list: tools requested by the definition ∩ tools granted by policy.
- An assignment cannot grant more authority than the assigner holds.
- Policy is kept in Git; changes need founder review and merge.
- The audit log is append-only and hash-chained.

### 9.2 L0–L4
| Level | Meaning | Examples |
|---|---|---|
| L0 | Read-only / sandbox-local | Reading an authorized repository, sandbox test and build |
| L1 | Reversible internal | Feature branch, commit, PR, internal record or Proposal |
| L2 | Internal change requiring independent review | Default branch merge, agent definition or lesson promotion, staging deploy |
| L3 | Founder approval | Production deploy, publish, external communication, spend, credential or access change, production infrastructure change, important data deletion |
| L4 | Forbidden for agents | Changing governance, policy, budget or audit; reading raw secrets; controlling personal accounts; changing emergency stop; approving one's own work; testing outside the authorized list |

### 9.3 Approval
- An ApprovalRequest contains a canonical payload and payload hash.
- The risk summary is generated by code from the structured payload.
- Approval is verified with a passkey.
- The challenge is bound to the request ID and payload hash.
- Approval must be single-use and expiring.
- A changed payload needs a new approval.
- Expired or revoked approvals are rejected.
- Silence is not approval.
- There is no batch approval for L3 operations.
- The number of pre-approved automations in V1 is zero.

### 9.4 Emergency stop and safety
- Emergency Stop is present on every PWA screen.
- It works with a one-step confirmation sheet; stopping needs no passkey step-up.
- A global stop halts new leases, cancels current leases, terminates sandboxes and pauses schedules.
- Levels: agent quarantine, department pause and company-wide stop.
- Out-of-band steps are documented: model provider API key revocation, halting prepaid top-ups and a server console stop.
- Policy changes are made only by the founder, through Git, and the permission test suite runs.
- Agents can suggest policy changes only as Proposals.

## 10. Cost and spending rules

- Six budget scopes: run, task, project, department, day, month.
- The worst-case cost is reserved before every model call.
- Budget caps belong to the founder; agents have read-only access.
- 50%: an event is recorded.
- 80%: the relevant Manager is woken and the founder alerted.
- 100%: new model calls stop for that scope.
- The provider's prepaid balance is also a hard limit.
- Paid services, hosting, domains, model APIs, subscriptions, auto-renewal and usage-based charges need founder approval in advance.
- The Business Manager only analyzes and proposes; it does not purchase or pay.
- V1 has no tool that spends money; the founder makes payments directly.
- Before starting any paid plan, AI-COS shows the cost, rationale, alternatives and renewal terms and asks for approval.

## 11. GitHub, staging, production and delivery

- GitHub is the center of source code and version history; it is not hosting on its own.
- Code is tested first, reviewed through a branch and PR, and CI evidence is collected.
- Staging deploy is L2; production deploy requires L3 founder approval.
- Production approval is bound to the exact commit, version and target.
- The release workflow cannot deploy any commit other than the approved one.
- Signing material and store credentials are kept in GitHub Actions environment-scoped secrets, not in the sandbox.
- In V1, agents do not manage personal store accounts; store submission is a founder action.
- Each product is hosted on its own hosting account; hosting product sites on the AI-COS server is not planned.
- Deployment can be automated: approved code is pushed to GitHub and a CI or hosting pipeline publishes the site.
- Buying paid hosting or a plan requires a separate L3 spending approval.

## 12. Marketing and Creative publishing rules

- Marketing can prepare content, campaign and launch drafts.
- Creative & Design produces the design and asset workflow.
- External communication and public content require L3 founder approval unless an approved automation exists.
- The identities and accounts of different brands and products are kept separate.
- Third-party media and GitHub tools are reviewed for license, dependencies, security, maintenance and resource use.
- V1 has no image, audio or 3D generation tool; assets are provided or licensed by the founder. Placeholder builds are clearly marked.

## 13. Memory rules

- Retrieve, do not inject: a run receives only a relevant, bounded context pack.
- A memory record carries its source, timestamp, scope and review status.
- Agent working notes are `unreviewed` and untrusted.
- Only approved entries enter retrieval for other agents.
- A lesson can enter promotion only if it cites AI-COS's own evidence records.
- Information from external sources is recorded with a URL and retrieval date, and stays unverified until confirmed.
- A conflicting record requires the new entry to set its supersedes field.
- There is no automatic promotion.

## 14. Measurement and agent performance

- Measurement dimensions:
  - Rate of tasks completed with evidence.
  - First-pass acceptance and rework.
  - Assignment-to-accepted cycle time.
  - Cost per accepted task, including failed attempts.
  - Run failure, timeout and retry reliability.
  - Definition review when the same failure class recurs three or more times.
  - Golden-task score.
- Agents are compared only within the same task type.
- With data from fewer than 10 tasks, the score shows "insufficient data".
- No single overall score is produced.
- Correction order: note → warning → revised-instructions proposal → scope narrowing → deactivate.
- Permissions cannot be changed through performance management; the governance change process is required.

## 15. Active departments and Workspace selection

- Active departments: Engineering, Cybersecurity, Creative & Design, Business, Marketing.
- R&D is deferred to a later stage.
- Workspace resolution covers selecting the active project from the phone control panel and explicitly naming a project in a message.
- AI-COS cannot start paid hosting or subscriptions on its own; approval is mandatory.

# AI-COS V1 — Data Model

> **Important:** This model is conceptual; it is not a final PostgreSQL migration or table schema. Field names, types and constraints must be finalized during schema design.

## 1. Modeling rules

- PostgreSQL is the system of record.
- Every project-related record must carry a `project_id`.
- Typed payloads must pass schema validation when written.
- Free text exists only in defined fields.
- Secrets are not stored in the database.
- Passkey public keys and secret fingerprints used for redaction are the exceptions.
- Append-only records are never updated; a correction is made with a new record.
- There is a single-owner, single-company model; V1 has no tenant field.
- Relationships and cardinalities are conceptual; do not assume types or fields that are not stated.

## 2. Organization entities

### Department
| Field | Description |
|---|---|
| name | Department name |
| measurable goals | Measurable department goals |
| manager | Department manager |

Relationship: a Department contains multiple Agents.

### Agent
| Field | Description |
|---|---|
| stable identity | Durable agent identity |
| role | Agent role |
| department | Department it belongs to |
| manager | Manager it reports to |

### AgentVersion
| Field | Description |
|---|---|
| instructions | Agent instructions |
| playbook references | Playbook references |
| requested tools | Requested tool list |
| tier | Model capability tier |
| status | `draft`, `active`, `retired` |
| golden-task result | The version's golden task result |

Relationship: each Agent can have multiple versions. A Job is pinned to the AgentVersion at assignment time. An agent definition's behavior is separate from its authority; actual authority comes from Governance policy.

## 3. Project and specification entities

### Project
| Field | Description |
|---|---|
| name | Project name |
| business_line | Configurable product line classification; values are not hardcoded |
| status | Project status |
| spending cap | Project spending limit |
| owner | Project owner |

Relationship: a Project has SpecVersion, Task and Release records.

### SpecVersion
| Field | Description |
|---|---|
| exact text | Original text submitted by the founder |
| hash | Content hash |
| number | Version number |
| parent version | Previous version |
| author | Author of the text |

Rules:
- Belongs to a Project.
- Immutable and insert-only.
- An existing version is never changed; a change creates a new version.

### Clarification
| Field | Description |
|---|---|
| question | Clarification question |
| blocking flag | Whether it stops planning |
| answer | The founder's answer |
| resulting SpecVersion | New specification version created by the answer |

Relationship: belongs to a Project.

### Requirement
| Field | Description |
|---|---|
| quote anchor | Location of the source text within the SpecVersion |
| text | Extracted requirement |
| kind | `quoted` or `assumption` |
| status | Requirement status |

Relationship: belongs to a SpecVersion and links to Task records.
Rule: a requirement without a source quote is marked as an assumption and cannot become an acceptance criterion without founder approval.

### Plan
| Field | Description |
|---|---|
| brief | Structured project brief |
| task graph version | Task graph version |
| budget envelope | Plan budget limit |
| estimates | Cost and effort estimates |
| approval reference | Founder approval reference |

Relationship: belongs to a Project. Plan and brief approval is an L3 gate.

### Task
| Field | Description |
|---|---|
| owner | Responsible agent or manager |
| department | Relevant department |
| state | State managed by the runtime |
| acceptance criteria | Acceptance criteria |
| deadline | Deadline |
| budget envelope | Task budget |
| parent | Parent task |

Relationships:
- Links to Requirement records.
- Carries dependency relationships.
- Has Job, Record and Evidence records.
- Subtasks are represented through the parent relationship.
- Every Task must link to at least one Requirement; the runtime rejects an assignment without a requirement link.

### Release
| Field | Description |
|---|---|
| version | Release version |
| commit | Git commit reference |
| target | Release target |
| artifacts | Release artifacts |
| approval reference | Release approval |

Relationship: belongs to a Project. Created after approval.

## 4. Runtime and task evidence entities

### Job
| Field | Description |
|---|---|
| task | Linked Task |
| type | Job type |
| state | Job state |
| lease and expiry | Worker lease information |
| attempt count | Number of attempts |
| idempotency key | Key preventing repeated effects |
| run-after time | Earliest time it can run |
| off-peak preference | Off-peak preference |
| pinned agent version | AgentVersion at assignment time |

Relationship: a Task can have one or more Jobs; a Job produces one or more Runs.

### Run
| Field | Description |
|---|---|
| worker | Executing worker |
| state | Run state |
| start and end | Start and end times |
| steps used | Number of steps used |
| tokens | Token usage |
| cost | Cost |

Relationship: belongs to a Job; has Step records.

### Step
| Field | Description |
|---|---|
| sequence | Order within the Run |
| kind | Model call or tool call |
| request hash | Request hash |
| redacted result reference | Reference to the redacted result |
| usage | Usage information |

Relationship: belongs to a Run. Append-only.

### Record
Defined typed record kinds:
- `TaskAssignment`
- `Report`
- `Blocked`
- `ReviewRequest`
- `ReviewResult`
- `Escalation`
- `Proposal`

Fields:
- kind
- validated typed payload
- sender
- receiver
- status

Relationship: concerns a Task and is written by a Run. The payload is validated against the relevant record schema.

### Evidence
| Field | Description |
|---|---|
| kind | test, build, CI run, diff, review or artifact |
| source | Source of the evidence |
| exit code | Process exit code |
| reference | Evidence reference |
| hash | Content hash |

Relationship: belongs to a Task. Immutable. Written by the evidence collector, with its source recorded.

### Artifact
Fields:
- object-storage key
- hash
- size
- kind

Relationship: belongs to a Task or Release.

### Event
Fields:
- type
- subject
- payload
- handled flag (outbox)

Rule: written in the same transaction as the state change.

### Schedule
Fields:
- trigger
- target definition
- enabled flag
- approval reference

Relationship: wakes Jobs. Creating one requires L3 approval.

## 5. Governance and cost entities

### Verdict
Fields:
- action hash
- tool
- redacted arguments
- permission level
- decision
- reason
- policy version

Relationship: belongs to a Step. Written only by the Gateway.

### Approval
Fields:
- payload hash
- risk summary
- status
- expiry
- consumed time
- passkey assertion reference

Relationship: linked to a Verdict. Single-use. Written only by the Gateway.

### PolicyVersion
Fields:
- Git commit
- activation time

Verdict records reference the relevant policy version.

### Budget
Fields:
- scope: `run`, `task`, `project`, `department`, `day`, `month`
- cap
- set by

Caps are set by the founder; agents have read-only access. Written and changed only by the Gateway.

### CostLedger
Fields:
- run and step
- provider
- model
- cache-hit tokens
- cache-miss tokens
- output tokens
- price table version
- peak flag
- cost

Rules:
- Append-only.
- Includes every charge and failed attempt.
- Written only by the Gateway.

### AuditLog
Fields:
- event
- actor
- subject
- previous row hash

Rules:
- Append-only.
- Uses a hash chain.
- The chain is verified daily.
- The chain head is exported to object storage with each backup.

### EmergencyState
Fields:
- level
- scope
- who
- reason
- cleared by

Read by Gateway admission checks.

### AuthorizedAsset
Fields:
- asset identifier
- owner
- allowed test types

Limits security testing scope. Requires founder approval.

## 6. Identity and access entities

A single-founder, single-owner model is defined:
- Founder
- Passkey
- Session
- PushSubscription

Defined information:
- A single owner.
- Credential IDs and public keys.
- Device labels.
- Revocation information.
- Push subscription.

A passkey's private key never leaves the device; the server stores only the public key.

## 7. Memory and evaluation entities

### MemoryEntry
Fields:
- kind
- scope: company, department or project
- content
- source
- status
- reviewer
- timestamps

Relationships:
- Can be scoped to a Project or Department.
- Promotion depends on the level.
- Source, author, created, last verified, review status, reviewer, recheck date, supersedes and data class are also part of the memory entry's structure.

States:
- `draft`
- `proposed`
- `approved`
- `rejected`
- `superseded`
- `expired`
- `unreviewed` (working notes)

Memory types:
- Company policies
- Department knowledge
- Project specifications
- Task history
- Agent working context
- Approved long-term lessons

### GoldenTask and EvalRun
- GoldenTask: task definition and expected checks.
- EvalRun: evaluation result per agent version.
- The Evaluation Engine runs measurements when agent definitions change.

## 8. State machines

### Task state
States managed by the runtime:
- Main flow: `proposed` → `ready` → `running` → `in_review` → `accepted`
- Side exits: `blocked`, `revision`, `failed`, `cancelled`
- `revision` returns to the `ready` flow, for at most two rounds.
- `accepted` is granted only with evidence and review; an agent's own claim of success is not enough.

### Run state
- `queued`
- `leased`
- `running`
- Terminal: `succeeded`, `failed`, `timed_out`, `cancelled`, `lost`

### AgentVersion status
- `draft`
- `active`
- `retired`

### MemoryEntry status
- `draft`
- `proposed`
- `approved`
- `rejected`
- `superseded`
- `expired`
- `unreviewed`

## 9. Relationship summary

```text
Department 1 --- N Agent
Agent 1 --- N AgentVersion

Project 1 --- N SpecVersion
Project 1 --- N Task
Project 1 --- N Release
Project 1 --- N Clarification
Project 1 --- N Plan

SpecVersion 1 --- N Requirement
Requirement N --- N Task (traceability)
Task 1 --- N Job
Job 1 --- N Run
Run 1 --- N Step
Task 1 --- N Record
Task 1 --- N Evidence
Task 1 --- N Artifact
Release 1 --- N Artifact

Step 1 --- N Verdict (relationship detail to be confirmed in the schema)
Verdict 1 --- N Approval (Approval is linked to a Verdict; cardinality is not final)
Run/Step --- CostLedger
Event --- AuditLog
```

> The cardinalities in this diagram are conceptual and must be confirmed during schema design. In particular, the exact Verdict–Approval and Step–Verdict cardinalities are not decided yet.

## 10. Open schema decisions

- SQL table names and naming conventions.
- Primary key types such as UUID, ULID or serial.
- Exact SQL type, nullability and default of every field.
- Foreign key on-delete behavior.
- Indexes and unique constraints.
- Whether a task's requirement link is single or multiple.
- Verdict–Approval cardinality.
- Artifact storage metadata schema.
- Detailed Session and push subscription fields.
- Whether Workspace is modeled as a separate entity or table, and its relationship to the Project entity and project scope.
- Department seed records for the active departments, including Creative & Design.

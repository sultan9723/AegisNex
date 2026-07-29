# CommandMesh Execution Instructions

Status: active build plan  
Product focus: runtime control layer for AI agent actions

## Brutal Product Direction

Do not build CommandMesh as a broad "AI governance platform" yet. That category is too wide, crowded, and easy to make shallow.

Build the narrow wedge first:

> CommandMesh is the runtime control layer that prevents AI agents from taking risky actions without policy checks, approval, and audit evidence.

The first excellent workflow must be:

1. An agent requests an action.
2. CommandMesh identifies the agent, tenant, target, and action type.
3. Policy returns allow, deny, or approval required.
4. Approval-required actions pause.
5. A human approves or rejects.
6. Every decision is written to a tamper-evident audit trail.
7. The buyer can export evidence.

If a new feature does not make that workflow stronger, defer it.

## What Not To Build Yet

- Do not expand generic dashboards.
- Do not build deep semantic cache yet.
- Do not add more model providers until the action-control workflow is strong.
- Do not build a custom ML risk classifier yet.
- Do not make a marketing site before the demo is sharp.
- Do not claim enterprise compliance until audit integrity and exports are real.

## Sprint Sequence From Here

### Sprint 2A: Tamper-Evident Action Audit

Goal: make every governance action independently verifiable.

Build:

- Hash-chain every `agent_actions` row.
- Store `previous_hash` and `entry_hash`.
- Add verification that detects modified, missing, or reordered records.
- Add CSV export for action evidence.
- Add tests for valid chain, tamper detection, and export shape.

Acceptance:

- `record_action()` always writes hashes.
- Old rows are backfillable.
- `/api/governance/audit/verify` reports integrity status.
- `/api/governance/audit/export.csv` downloads evidence.

### Sprint 2B: Production Approval Workflow

Goal: make the approval flow buyer-demo credible.

Build:

- Approval detail page or drawer.
- Approve/reject with reason.
- Link approval records to agent action IDs.
- Show action context, policy reason, requester, target, and timestamps.
- Record approval response into governance audit evidence.

Acceptance:

- Approval-required action can be reviewed from UI.
- Rejection/approval reason is stored.
- Action history shows approval outcome.

### Sprint 3: Tool Action Gateway

Goal: govern the risky part of agents: tool execution.

Build:

- `POST /api/governance/actions/evaluate-and-record`.
- Normalize tool action requests.
- Apply policy before execution.
- Return allow/deny/pending approval response.
- Provide a small SDK/helper that agent code can call before tools execute.

Acceptance:

- A demo support/refund or deploy action is blocked or approval-gated.
- The audit trail links request, policy, approval, and outcome.

### Sprint 4: Evidence Packet

Goal: make compliance evidence exportable.

Build:

- Export agent registry, policies, actions, approvals, and audit verification result.
- Start with CSV/JSON zip.
- Add PDF later only if the CSV/JSON evidence is useful.

Acceptance:

- One click produces an evidence packet for a date range.
- The packet can answer who, what, when, why, policy, verdict, approval, and integrity status.

## Demo To Optimize For

Use this demo until it is excellent:

> A customer support agent attempts a large refund. CommandMesh identifies the agent, checks policy, pauses the action for approval, logs the decision, records the approval result, and exports audit evidence.

This is the story. Build toward it.


# CommandMesh: AegisNex Governance and Cost Control Plane for AI Agents

Prepared for: Sultan, Founder and CTO  
Status: Internal engineering strategy and build roadmap  
Planning baseline: June 2026

## Executive Summary

CommandMesh is the AegisNex governance and cost-control module for AI agents. It sits between agent runtimes and the models, tools, and systems those agents act on. Its job is to intercept agent actions before execution, evaluate policy, route model calls to the cheapest capable model, escalate risky actions to humans, and preserve a complete audit trail.

The one-sentence pitch:

> CommandMesh is the policy and cost layer enterprises put in front of AI agents so those agents can act autonomously without acting recklessly or expensively.

The current AegisNex codebase already contains important foundations: FastAPI APIs, authentication, API keys, audit logging, approval queue primitives, risk and policy gates, multi-tenant organization/team/project models, multi-provider LLM support, a governance dashboard, and `src/ai_governance.py` for agent registry, policies, action audit, and anomaly tracking.

The CommandMesh-specific gap is that these pieces are not yet a complete cost-control plane. Governance records are now tenant-scoped, the governance dashboard supports the operator workflow, non-streaming OpenAI-compatible chat completion calls can flow through a policy-gated proxy, and deterministic model-tier routing now records estimated cost metadata. Semantic caching is absent, streaming proxy support is not implemented, benchmark reporting is not yet built, and audit records are not yet tamper-evident.

This roadmap treats governance as the foundation and cost routing as the wedge. Phase 0 makes the existing governance core credible. Phase 1 proves a measurable cost-reduction claim. Later phases turn the audit trail and deployment posture into enterprise readiness.

## Current State vs Target State

### Current State

AegisNex already provides:

- FastAPI backend with JWT, API key auth, RBAC, rate limiting, and audit logging.
- Multi-tenant primitives through organizations, teams, projects, and tenant users.
- AI intelligence loop with planning, tool routing, execution, risk assessment, policy checking, approvals, verification, and learning.
- `AppPolicyEngine` and intelligence policy/risk engines for autonomous action classification.
- Platform approval queue for human review workflows.
- `src/ai_governance.py` for AI agent registry, action audit, policy evaluation, and anomaly detection.
- `/api/governance/*` routes and a Next.js `/governance` dashboard.
- Multi-provider LLM support for OpenAI, Anthropic, Ollama, Azure OpenAI, and Gemini.

Current limitations:

- CommandMesh policy decisions are not yet the single mandatory gate for all agent/model/tool actions.
- The system exposes a non-streaming OpenAI-compatible chat completions proxy, but not streaming or Anthropic-compatible proxy ingress.
- The complexity classifier and model-tier routing are implemented for proxy calls, but semantic caching and a durable cost ledger are not yet implemented.
- Audit logs are useful but not append-only/tamper-evident through hash chaining.
- The governance UI supports the core create/update/approve/resolve operator loop, but still needs richer cost and audit evidence views.

### Target State

CommandMesh should become the AegisNex module that provides:

- Agent-aware ingress for model calls and tool actions.
- Tenant-scoped policy evaluation before execution.
- Human-in-the-loop escalation for high-risk actions.
- Model routing based on task complexity, policy, cost, and fallback availability.
- Cost observability by tenant, team, agent, provider, model, route decision, and task type.
- Immutable, exportable audit evidence for compliance reviews.
- A self-hostable deployment path that regulated buyers can evaluate without sending agent traffic to a third-party cloud.

## Architecture

### Ingress

CommandMesh should expose a gateway layer that can receive:

- Agent tool/action requests.
- OpenAI-compatible chat completion requests.
- Later, Anthropic-compatible message requests.

V1 should prioritize OpenAI-compatible proxy behavior because it creates the lowest-friction adoption path: customers should be able to point an existing SDK `base_url` at AegisNex with minimal code changes.

Inline question for Sultan: should V1 support OpenAI only first, or OpenAI plus Anthropic from day one?

### Policy Layer

Policy enforcement should stay declarative. A compliance or security buyer must be able to read the policy and understand why an action was allowed, blocked, or escalated.

V1 policy scope:

- Agent identity.
- Tenant or organization.
- Environment.
- Action type.
- Target resource.
- Risk level.
- Model/provider request class.
- Approval requirement.

Inline question for Sultan: should CommandMesh standardize on `org_id`, `tenant_id`, or both with one treated as an alias?

### Routing Layer

The routing engine should start rule-based, not ML-based.

V1 routing inputs:

- Prompt length.
- Presence of tool calls.
- Action type.
- Risk classification.
- Explicit model requested by the caller.
- Policy constraints.
- Provider availability.

V1 routing outputs:

- Selected provider.
- Selected model.
- Routing reason.
- Estimated input/output cost.
- Fallback chain.

Inline question for Sultan: which default models should define cheap, medium, and frontier routing tiers for demos?

### HITL Layer

High-risk actions should pause and create approval requests instead of executing blindly.

The existing AegisNex approval queue should be reused rather than creating a second queue. CommandMesh-specific approval records should carry enough context to answer:

- Which agent requested the action?
- What tenant/project did it belong to?
- What policy matched?
- What action would execute if approved?
- What model/tool context led to the request?

### Audit Layer

Audit is a core product asset, not just logging.

Every CommandMesh decision should produce an audit event with:

- Tenant or organization identifier.
- Agent identifier.
- User/API key identity where available.
- Request ID / correlation ID.
- Model requested and model selected.
- Policy verdict.
- Routing decision.
- Approval decision if applicable.
- Cost estimate.
- Inputs/outputs metadata, with configurable redaction.
- Previous hash and entry hash once hash chaining is introduced.

## Iteration Roadmap

### Iteration 0: Documentation Alignment

Goal: create a truthful engineering roadmap before adding more features.

Deliverables:

- This document in `docs/COMMANDMESH_ROADMAP.md`.
- Clear distinction between shipped AegisNex foundations and CommandMesh roadmap work.
- Inline product questions for decisions that need founder input.

Acceptance criteria:

- The document can guide implementation without implying cost routing is already shipped.
- Current-state claims match the repo.
- The roadmap starts with governance hardening before advanced routing.

### Iteration 1: Governance Core Hardening

Status: complete. Tenant-scoped governance storage, route scoping, approval queue creation for pending governance decisions, focused governance tests, route-level tenant tests, and legacy SQLite unique-constraint migration are implemented.

Goal: make the existing governance module enterprise-credible.

Implementation work:

- Add tenant scoping to AI governance records for agents, policies, actions, and anomalies. Done.
- Resolve tenant context from authenticated users/API keys where possible. Done with `org:{id}` for tenant memberships and `default` fallback.
- Enforce tenant filtering on all `/api/governance/*` list/get/update/delete routes. Done.
- Add governance tests for registry, policy evaluation, action audit, anomaly detection, and route authorization. Done.
- Connect high-risk governance decisions to the existing approval queue instead of leaving approval as a display-only verdict. Done for `pending_approval` evaluation and action recording paths.

Acceptance criteria:

- A user in tenant A cannot read or mutate tenant B governance records.
- Unknown or inactive agents are denied by policy.
- High-risk actions produce pending approval records.
- Governance smoke tests and API tests run in CI.

Inline question for Sultan: should the first tenant demo use one default organization or multiple named demo organizations?

### Iteration 2: Demo Policy Library and Operator Workflow

Status: complete. The demo policy library, expanded demo agents, deterministic action seed data, pending-approval examples, policy precedence fix, governance seed tests, and operator controls in the governance page are implemented.

Goal: make CommandMesh demo-ready for a technical buyer.

Implementation work:

- Add 15 to 20 realistic policy examples covering refunds, code deploys, data deletion, external API calls, production writes, finance actions, customer communication, and compliance-only read access. Done.
- Add seed data that demonstrates allowed, denied, pending approval, and anomalous actions. Done.
- Expand the governance dashboard so operators can create policies, edit policies, approve/reject queued actions, and resolve anomalies. Done.
- Add empty/error/loading states that make demo failures understandable.

Acceptance criteria:

- A demo user can show allow/block/escalate behavior without curl.
- The dashboard makes policy verdicts and reasons visible.
- Seeded demo data is deterministic and safe.

Inline question for Sultan: should demo policies be framed around SaaS operations, fintech/finance risk, customer support, or developer tools first?

### Iteration 3: OpenAI-Compatible Proxy Foundation

Status: complete for non-streaming chat completions. Added OpenAI-compatible `/v1/chat/completions` and `/api/v1/chat/completions` routes, OpenAI-style bearer API-key support, governance policy gating before provider calls, structured policy errors for denied and approval-required requests, approval queue creation, action/audit recording, and focused proxy contract tests.

Goal: enable drop-in model-call governance.

Implementation work:

- Add OpenAI-compatible routes for chat completions. Done for non-streaming requests.
- Normalize each request into CommandMesh metadata: tenant, agent, action type, target resource, requested model, and provider. Done.
- Evaluate policy before forwarding the request. Done.
- Forward allowed requests to configured providers. Done through the existing provider factory.
- Log allow/block/approval-required decisions to CommandMesh action/audit records. Done.
- Return compatible error responses for blocked or approval-required calls. Done.

Acceptance criteria:

- A standard OpenAI SDK can send a chat completion request through CommandMesh.
- Blocked requests return structured errors.
- Allowed requests are audited with model, tenant, agent, policy, and latency metadata.
- Provider credentials are read from existing settings/secrets mechanisms, not hard-coded.

Inline question for Sultan: should approval-required model calls return an error immediately, or return a pending approval object that the client can poll?

### Iteration 4: Cost Routing MVP

Status: partially complete. Implemented deterministic complexity classification, configurable cheap/medium/frontier model tiers, default cheap-tier downgrade for simple requests, caller model-lock override via metadata, selected/requested cost estimates, routing metadata in proxy responses and governance action records, and `/api/governance/costs/summary` for tenant-scoped cost aggregation. Benchmark harness, durable ledger schema, and dashboard panels remain.

Goal: make cost savings measurable.

Implementation work:

- Implement a deterministic rule-based complexity classifier. Done.
- Add model tier configuration for cheap, medium, and frontier models. Done via `AEGIS_COMMANDMESH_MODEL_TIERS` with safe defaults.
- Route simple requests to cheaper models unless policy or caller constraints override. Done with `metadata.model_locked` / `metadata.routing_disabled`.
- Record estimated input, output, and total cost for each routed request. Done in proxy response metadata and governance action output.
- Add a route decision and cost summary API. Done via `/api/governance/costs/summary`.
- Add a benchmark harness comparing direct-to-model cost versus routed cost on a fixed workload. Not yet done.
- Add a cost dashboard section showing spend by tenant, agent, model, provider, and route decision. Not yet done.

Acceptance criteria:

- The same prompt produces reproducible routing decisions.
- Simple requests are routed to the cheap tier by default, while locked calls keep the requested model.
- Cost estimates are stored in action output and queryable through the cost summary API.
- The benchmark reports cost delta, latency delta, and fallback count. Not yet done.

Inline question for Sultan: should the first public benchmark use synthetic workloads, recorded local AegisNex workloads, or a curated demo-agent workload?

### Iteration 5: Audit and Compliance Readiness

Goal: make audit evidence usable in a buyer conversation.

Implementation work:

- Add tamper-evident hash chaining for CommandMesh audit events.
- Add policy versioning and change history.
- Add CSV export for audit events and policy decisions.
- Add PDF export only after CSV is accepted as useful.
- Add a short control-mapping document for SOC 2 and ISO 42001-style evidence requests.

Acceptance criteria:

- Audit export can answer who, what, when, why, model, policy, verdict, approval, and cost.
- Hash-chain validation detects modified or missing audit records.
- Policy changes are attributable to a user/API key and timestamp.

### Iteration 6: Enterprise Readiness

Goal: remove predictable security-review blockers.

Implementation work:

- Document Docker Compose self-host deployment for CommandMesh mode.
- Add OIDC SSO if not already available for the target deployment path.
- Validate encrypted secret storage for provider keys.
- Add rate limits for proxy endpoints.
- Add retention controls for audit records and cached model responses.
- Add a minimal production checklist for regulated buyers.

Acceptance criteria:

- A buyer can deploy locally with Docker Compose.
- Provider keys are never shown in plaintext through APIs or UI.
- Proxy endpoints are rate limited by tenant/API key.
- Deployment docs include security and retention defaults.

## Engineering Backlog

### Data Model

- Add tenant context to CommandMesh governance records.
- Add request/correlation IDs to action and audit records.
- Add model routing metadata to action audit records.
- Add cost estimate fields or a dedicated model usage ledger.
- Add audit hash fields once hash chaining begins.

### Backend APIs

- Harden `/api/governance/*` for tenant isolation.
- Add policy CRUD tests and route tests.
- Add OpenAI-compatible proxy routes.
- Add route decision and cost summary APIs.
- Add audit export APIs.

### Frontend

- Upgrade `/governance` from read-only dashboard to operator console.
- Add approval review actions.
- Add policy editor with YAML/JSON preview.
- Add cost dashboard panels after routing ledger exists.
- Add audit export controls.

### Testing

- Unit-test governance manager behavior against fresh SQLite databases.
- API-test tenant isolation and RBAC.
- Contract-test OpenAI-compatible proxy responses.
- Fixture-test deterministic routing decisions.
- Integrity-test audit hash chain validation.
- Regression-test that destructive actions still pass through risk/policy/HITL gates.

## Product Questions for Sultan

- Should the external product name remain AegisNex with CommandMesh as a module, or eventually become a separate CommandMesh SKU?
- Should tenant identity in code use `org_id`, `tenant_id`, or both?
- Which demo buyer should shape policy examples first: AI-native SaaS, fintech, customer support, or DevOps/platform engineering?
- Which provider should be the first proxy target: OpenAI only, or OpenAI plus Anthropic?
- Which model tiers should be the default for demo routing?
- Should approval-required proxy calls return a pending object, a structured error, or a blocking wait with timeout?
- Should benchmark claims stay internal until measured on a design partner workload?
- Should the first deployment target be self-hosted Docker Compose or a public free-tier demo?

## Risks and Constraints

- Cost reduction is not yet measured. Treat any 20 to 40 percent savings claim as a target until the benchmark harness proves it.
- AegisNex has multiple policy systems today. CommandMesh must avoid creating a third disconnected policy path.
- Tenant isolation must happen before public demos that show multi-customer data.
- Proxy compatibility can expand quickly in scope. V1 should keep provider behavior narrow and testable.
- Semantic caching can create data-leak risk if tenant boundaries and redaction are not correct.
- Audit immutability is hard to retrofit, so the hash-chain design should be introduced before serious customer traffic.

## Near-Term Execution Order

1. Finish this roadmap document.
2. Add tenant scoping and tests to the governance module.
3. Add realistic demo policies and seed data.
4. Upgrade the governance dashboard into an operator console.
5. Add OpenAI-compatible proxy ingress.
6. Add routing and cost ledger.
7. Add benchmark harness and publish only measured results.

The main discipline is sequencing. Do not build advanced routing before the governance core can prove tenant isolation, policy enforcement, HITL escalation, and auditability.

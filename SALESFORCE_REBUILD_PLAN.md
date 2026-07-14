# Rebuilding Salesforce from Scratch: A Plan

If we were to re-make Salesforce today — a modern CRM platform with the benefit of
25 years of hindsight — this is how we'd do it. The goal is not to clone Salesforce
feature-for-feature, but to rebuild what made it dominant (the metadata-driven
platform, the ecosystem, the "no software" promise) without the accumulated debt
(Apex, Visualforce, governor-limit folklore, three overlapping UI frameworks, and
per-seat pricing that fights against automation).

---

## 1. Vision and Strategy

**One-liner:** A metadata-driven business application platform whose first and best
application is a CRM — AI-native, developer-friendly, and priced for a world where
agents do most of the clicking.

**Core bets:**

1. **Platform first, CRM second.** Salesforce won because the CRM was just the
   flagship app on a general-purpose platform (custom objects, workflows, AppExchange).
   We build the platform primitives first and implement Sales/Service as apps *on*
   the platform, eating our own dog food from day one.
2. **AI-native, not AI-bolted-on.** Every record, workflow, and API is designed to be
   operated by both humans and LLM agents. The "user" abstraction covers both, with
   the same permission model.
3. **Open core data layer.** Customer data lives in open formats (Postgres +
   Iceberg for analytics) with first-class export. Lock-in comes from the ecosystem
   and quality, not data hostage-taking.
4. **Consumption + seat hybrid pricing.** Per-seat for humans, metered for agents and
   automation — so customers aren't punished for automating.

**What we deliberately do NOT rebuild:** Marketing Cloud, Tableau, Slack, MuleSoft-style
acquisitions. Those were bolted on; we integrate with best-of-breed instead and keep
the surface area small.

---

## 2. Product Scope

### Phase 1 product (the wedge): Sales Cloud equivalent
- Leads, Contacts, Accounts, Opportunities, Activities, Pipelines
- Email/calendar sync (Google, Microsoft)
- Reports and dashboards
- Mobile app (read + quick actions, offline-tolerant)

### Phase 2: Service
- Cases, omnichannel routing, knowledge base, SLAs/entitlements
- AI deflection (answer from knowledge base before creating a case)

### Phase 3: Platform opened to the world
- Custom apps, marketplace (the AppExchange equivalent), ISV program

Everything in Phases 1–2 must be buildable with the public platform APIs. If our own
CRM team needs a private hook, that's a platform bug.

---

## 3. Architecture

### 3.1 The metadata engine (the heart of the system)

This is the single most important component — Salesforce's real moat. Everything is
metadata interpreted at runtime:

- **Objects & fields**: customers define entities without migrations. Implemented as
  a typed metadata catalog over Postgres — *not* the giant generic
  `value0..value500` flex-column table Salesforce used. Modern Postgres gives us
  JSONB + partial indexes + logical partitioning per tenant; we generate real
  columns for hot fields and JSONB for long-tail custom fields, with an online
  "promotion" path from JSONB to column.
- **Permissions**: object-, field-, and row-level security evaluated in one place
  (a policy engine, e.g. Cedar/OPA-style), enforced at the data API layer so no app
  code can bypass it.
- **Automation**: a single workflow engine (event → condition → actions, plus
  long-running orchestrations on a durable-execution runtime like Temporal). One
  engine — not the Workflow Rules / Process Builder / Flow archaeology dig.
- **UI**: layouts, list views, and record pages are metadata rendered by a standard
  component runtime (React + a published web-component contract for custom
  components). One UI framework, ever.

### 3.2 Tenancy

- **Cell-based architecture**: tenants are grouped into cells (~hundreds of tenants
  per cell), each cell a fully independent stack (DB, compute, queue). Blast radius
  of any failure is one cell. Big enterprise tenants can get dedicated cells.
- Schema-per-tenant inside a cell's Postgres cluster; automated tenant migration
  between cells for rebalancing.
- Regions/data residency from day one (EU, US at launch).

### 3.3 APIs

- **One canonical data API**: a typed CRUD+query API (GraphQL-flavored over the
  metadata catalog) with cursor pagination, batch operations, and optimistic
  concurrency. REST façade generated from it.
- **Events out**: every mutation emits a CDC event to a per-tenant stream customers
  can subscribe to (webhooks + Kafka-compatible consumer API).
- **Bulk in/out**: first-class async bulk API backed by object storage; nightly
  Iceberg snapshots of tenant data for their own warehouse.
- **MCP server built in**: the platform ships an MCP interface so any agent can
  operate a tenant with the tenant's permission model applied.

### 3.4 Customization & code

Where Salesforce invented Apex, we use **sandboxed TypeScript/WASM**:

- Customer logic runs as V8 isolates/WASM with CPU/memory/time budgets — real
  resource metering instead of magic-number governor limits, and budgets are
  purchasable rather than hard walls.
- Standard toolchain: npm-adjacent packaging, local dev server that emulates the
  platform, tests run in CI like any modern codebase.
- Versioned metadata: every org's full configuration is exportable as a git-friendly
  text format; environments (dev → staging → prod) are branches with diff/merge
  tooling. This kills the change-set misery.

### 3.5 AI layer

- **Agent runtime on the platform**: agents are principals with permission sets,
  audit logs, and spend budgets. They act through the same data API as humans.
- **Grounded assistance everywhere**: record summarization, email drafting, forecast
  explanations — always with citations to the underlying records.
- **Semantic layer**: the metadata catalog doubles as the semantic model for
  natural-language querying ("show me deals slipping this quarter") and for
  reporting, so NL query and dashboards share one definition of truth.

### 3.6 Search, reporting, files

- Search: per-cell OpenSearch/Vespa cluster indexing off the CDC stream, permission
  trimming at query time.
- Reporting: operational reports run on Postgres read replicas; heavy analytics on
  the Iceberg snapshots via DuckDB/Trino. No separate "Analytics Cloud" product.
- Files: object storage with per-tenant encryption keys; virus scanning; versioning.

---

## 4. Engineering Plan and Phasing

### Phase 0 — Foundations (months 0–6)
- Metadata catalog + typed data API + permission engine (the trio must land together)
- Cell infrastructure: one cell, IaC-provisioned, with tenant lifecycle (create,
  suspend, export, delete)
- AuthN/Z: OIDC/SAML SSO, SCIM provisioning, API keys, audit log
- CDC pipeline and event delivery
- Exit criteria: a to-do app and a bug tracker built purely on the public platform
  API by an internal team that has no backdoor access.

### Phase 1 — CRM alpha (months 6–14)
- Standard objects (Lead/Contact/Account/Opportunity/Activity) as *metadata
  packages*, not hardcoded tables
- Record UI runtime, list views, kanban pipeline, global search
- Email/calendar sync, dedupe, import wizard + bulk API
- Workflow engine v1 (triggers, scheduled jobs, approvals)
- Reports v1, mobile app (React Native)
- 10 design partners live; migrate one real org off a competitor as the acid test.

### Phase 2 — CRM GA + AI (months 14–22)
- Forecasting, territories, products/price books/quotes (CPQ-lite)
- Agent runtime GA: SDR-assist, pipeline-hygiene, and case-deflection agents
- Sandboxed code (TS/WASM) GA with local dev tooling
- Environments + metadata-as-code GA
- SOC 2 Type II, ISO 27001, HIPAA-ready cells; 99.95% SLA
- Service Cloud beta (cases, routing, knowledge)

### Phase 3 — Platform & ecosystem (months 22–36)
- Marketplace with revenue share (take 15%, undercutting the incumbent's 25–30%)
- ISV packaging: apps install as versioned metadata + sandboxed code bundles
- Migration tooling: automated Salesforce importer (objects, data, files, users,
  reports; flag Apex/Flows for manual rework with an AI-assisted converter)
- Second and third regions; dedicated-cell tier

### Team shape (first two years)
- ~8 eng on metadata/data platform, ~6 on infra/cells/SRE, ~10 on CRM apps,
  ~5 on AI/agents, ~4 on UI runtime + design system, ~3 security/compliance,
  plus product/design/GTM. Roughly 45–60 people before Phase 3. Total spend to GA
  in the $25–40M range — this is a venture-scale bet, not a side project.

---

## 5. Go-to-Market

1. **Wedge**: mid-market teams (50–500 employees) outgrowing HubSpot/Pipedrive but
   dreading Salesforce implementation costs. Self-serve onboarding in under an hour.
2. **Pricing**: transparent — e.g. $40–70/human-seat/mo plus metered agent/automation
   usage with included allowances. No "call us" wall until true enterprise features
   (dedicated cells, custom compliance).
3. **Migration as a product**: the Salesforce importer is a flagship feature, not a
   services engagement. Publish honest compatibility matrices.
4. **Ecosystem flywheel**: generous free dev orgs, revenue share that favors ISVs,
   certification program. The platform only compounds if others build on it.
5. **Land with AI ROI**: lead the sales conversation with agent outcomes (response
   time, pipeline hygiene, deflection rate), not feature checklists.

---

## 6. Biggest Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Metadata engine becomes a research project | Time-box Phase 0; ship the ugly-but-working version; the exit criterion (apps built only on public APIs) keeps it honest |
| "Cheaper Salesforce" positioning race to the bottom | Differentiate on AI-native operations and dev experience, not price alone |
| Enterprise trust gap (uptime, compliance) | Cell architecture + published status/postmortems from day one; compliance certs before enterprise push |
| Migration is always harder than promised | Invest in the importer early; be honest about Apex/Flow non-portability; AI-assisted conversion as accelerant not magic |
| Incumbent bundles and discounts to block us | Win where bundling hurts them: speed of implementation, admin cost, agent pricing |
| Scope creep toward rebuilding all of Salesforce's clouds | The "do NOT rebuild" list is a standing decision; integrate instead |

---

## 7. What Success Looks Like

- **Year 1**: 10 design partners running real pipelines; platform exit criteria met.
- **Year 2**: GA, 300+ paying orgs, one lighthouse migration from Salesforce,
  NRR > 110%.
- **Year 3**: marketplace live with 50+ apps, majority of new workflow executions
  initiated by agents rather than humans — proof the AI-native bet landed.

The one-sentence strategy: rebuild Salesforce's true asset — the metadata platform —
on modern foundations, make it the best place for AI agents to do business work, and
let the CRM be the proof.

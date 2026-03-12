# Project Context

- **Owner:** jmservera
- **Project:** Self-learning AI system — scrapes the internet for knowledge on a given topic and becomes a PhD-level expert. Self-healing and self-improving.
- **Stack:** Python 3.12+, FastAPI, Azure AI Foundry, Azure Container Apps, Cosmos DB, Service Bus, AI Search
- **Created:** 2026-03-12

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

### 2026-03-12: Team formation
- Team assembled: Morpheus (Lead), Trinity (Data), Oracle (AI/ML), Tank (Backend), Niobe (Tester)
- Core mission: build a self-improving AI that scrapes the internet and synthesizes PhD-level expertise
- Key subsystems: web scraping → knowledge extraction → knowledge graph → self-evaluation → improvement loop

### 2026-03-12: System architecture designed and scaffolded
- **Architecture doc:** `docs/architecture.md` — 11 sections covering all components, Azure services, data model, deployment
- **8 services:** Scraper, Extractor, Knowledge, Reasoner, Evaluator, Orchestrator, Healer, API Gateway
- **Key decisions:**
  - Cosmos DB NoSQL (not Graph API) for knowledge storage — better vector search, serverless tier
  - Azure AI Search for vector indexing — hybrid search superior to Cosmos-native vectors for RAG
  - Service Bus queues + topics for all inter-service communication — DLQ critical for self-healing
  - Serverless AI model deployments (pay-per-token) — no GPU reservation for bursty workloads
  - Bicep IaC with azd — native Azure, no Terraform state management
  - Single managed identity with RBAC — no API keys in code
  - Three-layer self-healing: infrastructure (Azure-native), pipeline (Healer DLQ/circuit-break), cognitive (prompt tuning/strategy adjustment)
- **Owner preferences:** jmservera wants Azure AI Foundry (Microsoft Foundry), Container Apps, azd deployment
- **Project structure:** `infra/` (Bicep modules), `src/` (8 service dirs), `docs/`, `tests/`
- **Decision record:** `.squad/decisions/inbox/morpheus-system-architecture.md`
- **Partition strategy:** Cosmos DB partitioned by `topic` — co-locates all knowledge for efficient graph traversal
- **Models:** GPT-4o (reasoning/extraction), GPT-4o-mini (lightweight tasks), text-embedding-3-large (embeddings)

### 2026-03-12: Orchestrator and Healer implemented
- **Orchestrator** (`src/orchestrator/`, 9 files, 2538 lines): Full autonomous learning loop with Plan→Scrape→Extract→Organize→Reason→Evaluate→Improve cycle. Priority-based topic scheduling, gap-driven strategy management (breadth/depth/verification/diversify modes), working memory with relevance decay for LLM context, Cosmos DB persistence, Service Bus coordination.
- **Healer** (`src/healer/`, 7 files, 1973 lines): Health monitoring of all 7 services with circuit breaker pattern, DLQ scanning with triage (replay vs discard with backoff), Container Apps restart via management API, endpoint failover, prompt tuning analysis, queue-depth scaling recommendations.
- **Key patterns established:**
  - `pydantic-settings` for all service configuration via env vars
  - Async Service Bus listeners with completion-buffer pattern for pipeline coordination
  - Working memory decay model: on-topic items get boosted, off-topic items decay by configurable factor
  - Strategy modes drive query generation templates and reasoning task selection
  - Circuit breaker: closed→open (after N failures)→half-open (after timeout)→closed (after M successes)
  - DLQ triage: replay with exponential backoff, discard poison/max-retried messages, skip if circuit open
- **Commit:** `8825dd8` — `feat(orchestrator,healer): implement autonomous learning loop and self-healing system`

### 2026-03-12: Five-agent parallel spawn complete
- Trinity (Scraper), Oracle (Extractor + Reasoner), Tank (Knowledge + API Gateway), Niobe (Evaluator + Tests) all completed and committed
- **Total deliverables:** 61 Python source files, ~12,634 LOC production code, ~2,910 LOC test code
- **Test results:** 159 passing, 1 skipped across all test suites
- **Cross-team decisions merged:** 6 decision documents consolidated into `.squad/decisions.md`, inbox cleared
- **Design patterns established:** All services follow pydantic-settings config, FastAPI with lifespan, OpenTelemetry instrumentation, graceful degradation on startup
- **Integration ready:** All services coordinate via Service Bus (queues + pub/sub topics), Cosmos DB (partition key = topic), Azure AI Search (hybrid search)
- **System now complete:** Full 8-service pipeline ready: Trinity→Oracle→Tank→Niobe pipeline monitored/coordinated by me; Healer watches all for health/recovery
- **Governance established:** User directive "commit after every learning loop iteration" merged into decisions.md; all agents committed to atomic commits per loop
- **Next iteration:** Integration testing, first learning loop (scrape → extract → organize → reason → evaluate → improve), production deployment prep

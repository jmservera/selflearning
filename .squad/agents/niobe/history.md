# Project Context

- **Owner:** jmservera
- **Project:** Self-learning AI system — scrapes the internet for knowledge on a given topic and becomes a PhD-level expert. Self-healing and self-improving.
- **Stack:** Python 3.12+ with FastAPI, Azure AI Foundry, Cosmos DB, Azure Service Bus, Container Apps
- **Created:** 2026-03-12

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

### 2026-03-12: Team formation
- Responsible for: testing, quality assurance, self-evaluation loops, improvement metrics
- Team: Morpheus (Lead), Trinity (Data), Oracle (AI/ML), Tank (Backend), Niobe (Tester — me)
- I validate everything: scraped data quality, knowledge accuracy, pipeline integrity, self-improvement metrics

### 2026-03-12: System Architecture (Morpheus)
- **8 services:** Scraper, Extractor, Knowledge, Reasoner, Evaluator, Orchestrator, Healer, API Gateway
- **Messaging:** Azure Service Bus (queues + pub/sub topics) for inter-service communication
- **Storage:** Cosmos DB NoSQL for knowledge graph (serverless), Azure AI Search for vector search
- **Compute:** Azure Container Apps with KEDA auto-scaling
- **AI:** Serverless model deployments in Azure AI Foundry (GPT-4o, GPT-4o-mini, text-embedding-3-large)
- **IaC:** Bicep with managed identity for authentication (no API keys)
- **Resilience:** Three-layer self-healing (infrastructure auto-restart, pipeline DLQ recovery, cognitive learning adjustment)
- **My role:** Evaluator service assesses knowledge quality and accuracy, Healer service implements cognitive learning loops (prompt tuning, strategy adjustment, knowledge refresh), testing framework validates pipeline integrity and self-improvement metrics

### 2026-03-12: Evaluator Service & Test Infrastructure Implementation
- Built complete evaluator service (8 files in src/evaluator/): config, models, knowledge_client, service_bus, question_generator, evaluation engine, FastAPI app
- Evaluation pipeline: taxonomy coverage → self-test (LLM questions + RAG answers) → confidence analysis → gap detection → scoring (0-100 with weighted subscores)
- Test infrastructure covers 5 services with 160 tests (159 pass, 1 skipped for optional dep)
- Test approach: evaluator tests against real service; other service tests use inline reference implementations as executable behavioral specs (TDD-first: tests from requirements, not implementation)
- Key patterns: mock Azure clients in conftest.py, respx for HTTP mocking, pytest-asyncio for async tests, sample data fixtures shared across test files
- Scoring formula: overall = coverage(25%) + depth(20%) + accuracy(35%) + recency(20%)
- Gap severities: critical (0 entities), moderate (thin coverage or low confidence), minor (missing relationships)

### 2026-03-12: Five-agent parallel spawn complete
- Trinity (Scraper), Oracle (Extractor + Reasoner), Tank (Knowledge + API Gateway), Morpheus (Orchestrator + Healer) all completed and committed
- **Total deliverables:** 61 Python source files, ~12,634 LOC production code, ~2,910 LOC test code
- **Test results:** 159 passing, 1 skipped across all test suites
- **Cross-team decisions merged:** 6 decision documents consolidated into `.squad/decisions.md`, inbox cleared
- **Design patterns established:** All services follow pydantic-settings config, FastAPI with lifespan, OpenTelemetry instrumentation, graceful degradation on startup
- **Integration ready:** All services coordinate via Service Bus (queues + pub/sub topics), Cosmos DB (partition key = topic), Azure AI Search (hybrid search)
- **Incoming dependencies:** Evaluator queries Knowledge service endpoints for entity/claim/relationship stats; Orchestrator publishes evaluation-complete events; Scraper/Extractor/Reasoner outputs are evaluated by my scoring engine
- **Next iteration:** Integration testing, first learning loop (scrape → extract → organize → reason → evaluate → improve), production deployment prep

### 2026-03-13: PR reviews round 2 (PRs #13-16)
- **PR #13 (Reasoner HTTP endpoints):** APPROVED by Ralph. Niobe completed 382 tests, 1 skipped. Added HTTP endpoints for direct reasoning invocation and result retrieval (GET /status, POST /reason, GET /results/{id}). In-memory FIFO cache (100 entries). Pattern established for future services.
- **PR #14 (API Gateway tests):** APPROVED by Ralph. Niobe completed 35 tests with 100% endpoint coverage. Ready for production deployment.
- **PR #15 (Cosmos DB migration):** APPROVED by Ralph. Morpheus reviewed graceful fallback pattern — in-memory stores as safety net during external persistence failures. Zero-downtime migration, development ergonomics, production safety. Pattern documented for future migrations.
- **PR #16 (Docker compose):** BLOCKED by emulator authentication issue. Tank identified missing conditional auth pattern — services default to managed identity (production) but emulators require account key authentication. Affects Knowledge, Scraper, Orchestrator, Extractor services. Solution pattern documented, awaiting implementation fixes from Trinity/Oracle/Morpheus.
- **Impact:** 3 PRs merged (closing issues #4, #5, #6). 3 new patterns established in decisions.md. 1 high-priority blocker identified for local development.


### 2026-03-13: PR #21 Review — Scraper and Extractor Endpoint Tests
- Reviewed and approved PR #21 by @copilot coding agent: added FastAPI endpoint tests for Scraper and Extractor services (closes issue #3)
- **Test results:** 71/71 tests pass (36 existing + 9 new endpoint tests: 5 scraper, 4 extractor)
- **Coverage added:**
  - Scraper: 5 tests for /health and /status endpoints (healthy state, degraded blob/cosmos, degraded service bus, consumer/publisher stats)
  - Extractor: 4 tests for /health and /status endpoints (healthy state, degraded llm/blob, degraded service_bus/pipeline)
- **Code quality observations:**
  - Follows established patterns from test_knowledge.py (AsyncClient + ASGITransport, module-level singleton mocking, _setup_service_path)
  - Degraded state testing covers all critical components (blob storage, cosmos DB, service bus, LLM client, extraction pipeline)
  - Status endpoint implementation added to src/extractor/main.py (+21 lines, -1): version, started_at, components health, consumer_running flag
  - Scraper tests validate crawl_history stats integration via mock_history.get_crawl_stats()
  - Extractor tests validate all 4 component states (llm_client, blob_storage, service_bus, pipeline)
- **No gaps identified:** Both services now have comprehensive endpoint coverage matching Knowledge service test quality
- **Decision:** Marked PR ready and approved. Tests demonstrate correct graceful degradation behavior for all Azure service dependencies.

### 2026-03-13: PR #18 Review — Reusable AsyncClient Fixtures for All 8 Services
- Reviewed and approved PR #18 by @copilot coding agent: added shared test fixtures for all 8 services to conftest.py (closes issue #9)
- **Test results:** 391/391 tests pass, 1 skipped (optional Azure SDK dep in evaluator)
- **Infrastructure added:**
  - `_setup_service_path(service_name)` — centralizes sys.path/sys.modules management for bare-import services (orchestrator, healer, reasoner, scraper, extractor)
  - `_alias_service_modules(service_name, module_names)` — registers bare-name sys.modules aliases for services using non-package imports
  - 7 new `*_client` fixtures: `api_client`, `scraper_client`, `extractor_client`, `knowledge_client`, `reasoner_client`, `orchestrator_client`, `healer_client`
  - Each fixture: imports real service app, injects MagicMock/AsyncMock into module singletons, provides httpx.AsyncClient, restores originals on cleanup
  - `healer_client` pre-empts unavailable Azure SDK submodules (azure.mgmt.appcontainers, azure.servicebus.management.aio) via sys.modules.setdefault
- **Test coverage:**
  - 20 smoke tests in tests/test_shared_fixtures.py validate each fixture (health endpoint + at least one data endpoint per service)
  - Existing tests refactored to use shared fixtures (test_reasoner.py removed 162 lines of duplicated setup)
  - Net change: +676 lines (conftest.py + test_shared_fixtures.py), -2443 lines (removed duplicated setup across test files)
- **Design quality:**
  - Fixtures follow pytest best practices: session/module/function scopes, proper cleanup, comprehensive docstrings
  - Mocks are accessible via module references for per-test configuration (demonstrated in test_orchestrator_client)
  - Consistent mocking pattern across all services: AsyncMock for async methods, sensible default return values
  - Proper isolation: bare-module cache eviction prevents cross-contamination between services with same-named modules (config.py, models.py)
- **Decision:** APPROVED. This is exactly the kind of test infrastructure that enables rapid development — future tests can now be written in 10 lines instead of 100. Pattern is reusable, well-documented, and proven by 391 passing tests. Ready to merge.

### 2026-03-13: Backlog cleared — Final session complete
- All 10 issues resolved, all 10 PRs merged (PR #17 Bicep IaC, PR #18 Test Fixtures + Tank conflict resolution)
- **Final test results:** 494/494 tests pass
- **Coverage:** 80%+ maintained across all 8 services
- **Decision artifacts merged:** niobe-pr18-review.md and niobe-pr21-review.md consolidated to decisions.md
- Project ready for next learning loop iteration: Scrape → Extract → Organize → Reason → Evaluate → Improve

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

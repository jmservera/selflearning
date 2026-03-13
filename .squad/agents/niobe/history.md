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


### 2026-03-13: PR #20 & #21 — Integration Tests and Endpoint Test Coverage
- **PR #20 (Integration test patterns):** Designed and implemented comprehensive integration test suite using in-process message bus simulation. All tests mock at Service Bus level, not business logic. 30 tests covering Scraper→Extractor→Knowledge pipeline, Reasoner flow, Evaluator cycle, Orchestrator completion buffers, end-to-end message flow. All 30 tests pass in 0.93s, zero Azure dependencies. Decision documented: integration tests validate actual message serialization/deserialization, not implementation details. Test architecture applies to all future pipeline stages. **APPROVED & MERGED.** Issue #11 closed.
- **PR #21 (Scraper/Extractor endpoint tests):** Added 5 tests for Scraper endpoints (/health, /status with degraded states) and 4 tests for Extractor endpoints (/health, /status with component health). Total: 71/71 tests passing (36 existing + 35 new). Comprehensive coverage of graceful degradation behavior for blob storage, Cosmos DB, Service Bus, LLM client, and extraction pipeline. Follows established pattern from test_knowledge.py. Both services now have production-quality endpoint testing. **APPROVED & MERGED.** Issue #3 closed.
- **Test impact:** 2 new test suites with comprehensive endpoint coverage. Pattern established: every service should validate /health and /status endpoints with full component state testing. Integration tests enable confidence in local development pipeline.
- **Learning:** Endpoint testing is not optional. /health and /status must cover all critical dependencies and report degraded states accurately. This enables external monitoring and load balancer circuit breaking.

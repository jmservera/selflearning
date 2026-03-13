# Decision: Scraper & Extractor Endpoint Test Patterns

**Context:** PR #21 adds FastAPI endpoint tests for Scraper and Extractor services, completing the endpoint test coverage for all data ingestion services.

**Decision:** Approved the following test patterns for Scraper and Extractor services:

## Test Coverage Pattern
- `/health` endpoint: Basic liveness check (200 status, service name validation)
- `/status` endpoint: Detailed component health with multiple scenarios:
  - Healthy state: all components "connected" or "ready"
  - Degraded states: specific component failures (blob storage, cosmos DB, service bus, LLM client, extraction pipeline)
  - Runtime stats: started_at timestamp, consumer_running flag, crawl history, message processing counters

## Implementation Details

### Scraper Service (5 tests)
- Tests cover: blob storage, cosmos DB, service bus consumer/publisher
- Mock integration: `mock_history.get_crawl_stats()` returns crawl statistics
- Stats validation: consumer.stats (messages_processed), publisher.stats (messages_published)

### Extractor Service (4 tests)
- Tests cover: LLM client, blob storage, service bus, extraction pipeline
- Status endpoint added to src/extractor/main.py (+21 lines)
- Component states: connected/not_initialized for each dependency
- Consumer task monitoring: checks `_consumer_task.done()` status

## Test Infrastructure Pattern
Both services follow the established pattern from test_knowledge.py:
1. `_setup_{service}_path()` function to manage sys.path and module imports
2. Module-level singleton mocking (clients, consumers, publishers)
3. AsyncClient + ASGITransport for FastAPI testing
4. Fixture cleanup: restore sys.path, clear sys.modules after each test

## Quality Bar
- All tests pass cleanly (71/71 across both services)
- Degraded state testing covers all critical Azure dependencies
- Pattern consistency across Knowledge, Scraper, and Extractor services
- 80%+ coverage maintained (meets Niobe's quality threshold)

**Rationale:** These patterns ensure consistent endpoint testing across all services while validating graceful degradation behavior for Azure service dependencies. The test infrastructure safely handles module import conflicts when running the full test suite.

**Impact:** Completes endpoint test coverage for data ingestion pipeline (Scraper → Extractor → Knowledge). Establishes reusable pattern for remaining services (Reasoner, Orchestrator, Healer, API Gateway).

---
**Author:** Niobe (Tester/Evaluator)  
**Date:** 2026-03-13  
**Related:** PR #21, Issue #3

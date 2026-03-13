# Squad Decisions

## Active Decisions

### System Architecture (2026-03-12)

**Author:** Morpheus (Lead/Architect)  
**Status:** Accepted

Eight-service microservice architecture for selflearning AI project:

1. **Eight-service microservice architecture** — Scraper, Extractor, Knowledge, Reasoner, Evaluator, Orchestrator, Healer, and API Gateway. Each is an independent Container App with its own scaling rules. **Rationale:** Each stage of the learning pipeline has different scaling characteristics and failure modes. Independence allows targeted scaling and isolated fault recovery.

2. **Azure Service Bus for inter-service communication** — Queues for point-to-point (scrape-requests, reasoning-requests). Topics with subscriptions for pub/sub (scrape-complete, extraction-complete, reasoning-complete, evaluation-complete, healing-events). **Rationale:** Dead-letter queues are essential for self-healing. KEDA integration with Container Apps enables event-driven scaling. Ordered delivery and sessions support pipeline coordination.

3. **Cosmos DB NoSQL** for knowledge storage — Knowledge graph stored as document types (Entity, Relationship, Claim, Source) in Cosmos DB NoSQL API with serverless tier, partitioned by topic. **Rationale:** NoSQL API has better vector search support, serverless pricing tier, and wider SDK coverage than Graph API. Graph traversal is handled at the application layer.

4. **Azure AI Search for vector search** — Dedicated AI Search service for vector indexing with hybrid search (vector + keyword). **Rationale:** More mature vector indexing, hybrid search support, faceted filtering. Cosmos DB vectors are good for point lookups but AI Search is better for complex search patterns.

5. **Serverless API model deployments** in AI Foundry — GPT-4o, GPT-4o-mini, and text-embedding-3-large deployed as serverless pay-per-token endpoints. **Rationale:** No GPU reservation needed, faster scaling, cost-effective for variable workloads. The system has bursty inference patterns that don't justify reserved compute.

6. **Bicep for IaC** — All infrastructure defined in Bicep modules under `infra/`. **Rationale:** Native Azure support, first-class azd integration, simpler for Azure-only deployments. No state file management needed.

7. **Managed identity everywhere** — Single user-assigned managed identity with RBAC roles on all Azure resources. **Rationale:** Eliminates secret management for service-to-service auth. Reduces attack surface. Simplifies rotation and compliance.

8. **Three-layer self-healing architecture** — Layer 1 (Infrastructure): Azure-native auto-restart, KEDA scaling. Layer 2 (Pipeline): Healer service processes DLQs, circuit breaking, endpoint failover. Layer 3 (Cognitive): Prompt tuning, learning strategy adjustment, knowledge refresh. **Rationale:** Each layer handles different failure modes. Infrastructure healing is automatic. Pipeline healing recovers from transient failures. Cognitive healing adapts the system's learning strategy.

9. **Python-first, FastAPI for all services** — All services use Python 3.12+ with FastAPI and uvicorn. **Rationale:** Consistent stack across all AI/ML workloads. FastAPI provides async support, auto-docs, and type safety. Azure SDK has first-class Python support.

### Git Commit After Every Learning Loop Iteration (2026-03-12)

**Author:** jmservera (User Directive)  
**Status:** Accepted — MANDATORY

After every learning loop iteration — the full cycle of **scrape → extract → organize → reason → evaluate → improve** — all code changes produced during that iteration **MUST be committed to git** before proceeding to the next iteration.

**Rules:**
1. **Atomic commits per iteration.** Each loop iteration gets its own commit (or logical group of commits). Do not batch multiple iterations into a single commit.
2. **Commit message format:** `loop(iteration-N): <brief summary of what changed>` — e.g., `loop(iteration-3): improved extraction prompts, added retry logic to scraper`.
3. **What gets committed:** All code changes, config changes, prompt updates, pipeline modifications, and any generated artifacts that are part of the codebase. Ephemeral data (scraped raw content, intermediate embeddings) follows the project's `.gitignore` rules.
4. **When to commit:** After the **improve** step completes and before the next **scrape** step begins. If the evaluate step triggers no improvements, commit any metrics/evaluation artifacts anyway.
5. **All agents must enforce this.** Whether working on scraper code (Trinity), reasoning logic (Oracle), backend services (Tank), evaluation metrics (Niobe), or architecture changes (Morpheus) — if your work is part of a loop iteration, it gets committed at the end of that iteration.
6. **Self-healing changes too.** If the Healer service modifies code as part of self-improvement, those changes are committed with the same discipline.

**Why:** Git history becomes a complete record of the system's evolution. Every iteration is traceable, diffable, and revertable. This is essential for a self-improving system — we need to know exactly what changed and when, so we can correlate code changes with knowledge quality and system behavior.

### Scraper Service Implementation Patterns (2026-03-12)

**Author:** Trinity (Data Engineer)  
**Status:** Accepted

Scraper service (`src/scraper/`) established key design patterns affecting downstream services:

1. **Blob path convention:** `{topic}/{domain}/{content-hash-prefix}.html`
   - Topic slugified (lowercase, spaces→hyphens, max 50 chars)
   - Domain is URL netloc
   - Hash is first 16 chars of SHA-256

2. **Cosmos DB partition key = domain** — Keeps dedup queries partition-local

3. **Content extraction:** BeautifulSoup + noise stripping (remove script/style/nav/footer/aside/ads, prefer `<main>` or `<article>`)

4. **Zero-config default:** DuckDuckGo HTML search (`html.duckduckgo.com`). Production should use Bing Search API with key.

5. **Graceful degradation:** If Blob, Cosmos, or Service Bus fail to initialize, service continues in degraded mode.

**Questions for team:**
- Should Extractor expect raw HTML or pre-cleaned text in blob storage? Currently raw HTML.
- Do we need a shared Pydantic models package, or copy-paste acceptable for now?

### Extractor & Reasoner Service Patterns (2026-03-12)

**Author:** Oracle (AI/ML Engineer)  
**Status:** Accepted

Extractor and Reasoner services established reusable patterns for all future AI/ML services:

1. **Service structure:** `config.py` (pydantic-settings) → `models.py` (Pydantic) → `llm_client.py` (Azure AI wrapper) → `service_bus.py` (consume/publish) → `{core}.py` (business logic) → `main.py` (FastAPI with lifespan)

2. **LLM client as thin wrapper:** Wraps `azure-ai-inference` with retry, JSON parsing, OTel tracing. Model name is config parameter — same client handles GPT-4o, GPT-4o-mini, or future models. Both services duplicate; future consideration: extract to shared library if >3 services need it.

3. **JSON mode for structured extraction:** All extraction prompts use `response_format={"type": "json_object"}`. Client strips markdown code fences as fallback. Few-shot examples in prompts critical for output format consistency.

4. **Prompts are code, not config:** Defined as module-level constants, contain few-shot examples, confidence scoring rules, edge-case instructions. Prompt changes are code changes — tracked in git, reviewed in PRs.

5. **OpenTelemetry attributes on every LLM call:** `llm.model`, `llm.prompt_tokens`, `llm.completion_tokens`, `llm.total_tokens`, `llm.latency_ms`, `llm.attempt`. Non-negotiable for cost tracking and debugging.

6. **pydantic-settings for configuration:** Added `pydantic-settings>=2.7.0`. All config loads from environment with sensible defaults. Canonical FastAPI pattern — other services should follow.

**Impact:** All 6 remaining services should follow these patterns for consistency.

### Knowledge Service & API Gateway Implementation Decisions (2026-03-12)

**Author:** Tank (Backend Dev)  
**Status:** Accepted

Knowledge Service and API Gateway established backend patterns:

1. **One AI Search index per topic** — Created dynamically via `ensure_index(topic)`. Index name: `{prefix}-{topic}`. Keeps indexes focused; topic-scoped queries are primary access pattern. Global search can query across indexes if needed.

2. **Fuzzy entity resolution:** `difflib.SequenceMatcher` with 0.85 similarity threshold, plus exact alias set intersection. Good enough for extraction-pipeline deduplication without embedding similarity cost. Can be tightened or replaced with embedding-based resolution in future.

3. **API Gateway graceful degradation:** When Orchestrator unreachable, topic commands queued to Service Bus. Dashboard endpoints return empty/default data instead of 502s. Gateway should never block the user.

4. **Chat RAG pipeline:** Search knowledge graph (hybrid) → supplement with entity search → supplement with high-confidence claims → build prompt → call GPT-4o → estimate confidence from citations. Multi-source context gathering ensures rich grounding.

5. **WebSocket heartbeat pattern:** 30-second timeout with automatic heartbeat. Clients can send "ping" for explicit keepalive. Prevents connection drops from idle timeouts on load balancers and reverse proxies.

**Dependencies on other services:**
- Orchestrator (API Gateway calls for topic management, falls back to Service Bus when unavailable)
- Extraction pipeline (Knowledge Service consumes from `extraction-complete` topic)
- AI Foundry (Chat calls GPT-4o; Knowledge Service uses text-embedding-3-large via AI Search)

**For team awareness:**
- Added `azure-ai-inference`, `websockets` to API Gateway requirements.txt
- All Cosmos queries use `topic` as partition key where possible to avoid cross-partition overhead
- Entity merge logic picks longer description and higher confidence — may need tuning with real data

### Evaluator Service & Test Infrastructure (2026-03-12)

**Author:** Niobe (Tester/Evaluator)  
**Status:** Accepted

Evaluator service and comprehensive test infrastructure:

1. **Scoring formula:** overall = coverage(25%) + depth(20%) + accuracy(35%) + recency(20%). Accuracy gets highest weight — correctness matters most for PhD-level system.

2. **Test approach for unimplemented services:** Used inline reference implementations as executable behavioral specifications (contracts, not implementations). When services are built, tests should be updated to import from actual service modules.

3. **Taxonomy areas:** 8 defaults (core_concepts, key_figures, methodologies, applications, history, current_research, controversies, related_fields). Entities classified by category/type heuristics.

4. **Gap severity thresholds:** critical = 0 entities, moderate = <3 entities OR confidence <0.5, minor = 0 relationships. Self-test failure >50% = critical general_knowledge gap.

5. **In-memory scorecard storage:** Using dicts for now. Production should use Cosmos DB via Knowledge Service or dedicated container.

**Impact on other agents:**
- Knowledge Service must expose: GET /entities, /claims, /relationships (with topic query param), POST /search, GET /topics/{topic}/stats
- Reasoner should be aware evaluator will query its outputs for accuracy assessment
- Scraper output quality directly affects evaluation scores
- Orchestrator should subscribe to evaluation-complete Service Bus topic (schema now defined)

**Test results:** 159 passing, 1 skipped (across Evaluator, Scraper, Extractor, Knowledge, API test suites)

### Orchestrator & Healer Implementation Patterns (2026-03-12)

**Author:** Morpheus (Lead/Architect)  
**Status:** Accepted

Orchestrator and Healer established critical cross-cutting patterns:

1. **Completion-buffer pattern:** Orchestrator subscribes to completion topics, routes events into per-topic `asyncio.Queue` buffers. Learning loop `wait_for_completions()` against specific request IDs. Decouples message arrival from pipeline stage execution. **All services that coordinate via Service Bus should use this pattern.**

2. **Working memory with relevance decay:** In-process working memory tracks findings, gaps, insights, plans. Items decay per tick based on topic focus match. Decay factor: 0.9 per tick for unfocused items. Items below 0.05 relevance evicted. Max 50 items. Provides LLM prompt context without manual curation.

3. **Four-mode learning strategy:** Driven by evaluation results:
   - **breadth**: Gap-driven queries, wide coverage (default for new topics)
   - **depth**: Deep-dive queries on specific areas (once coverage > 0.7)
   - **verification**: Fact-checking and contradiction resolution (when accuracy < 0.7)
   - **diversify**: Source diversification (when stale for 3+ iterations)

4. **Circuit breaker pattern:** Full circuit breaker per service:
   - CLOSED → OPEN after 5 consecutive failures
   - OPEN → HALF_OPEN after 60s recovery timeout
   - HALF_OPEN → CLOSED after 3 successful test calls
   - HALF_OPEN → OPEN if test call fails
   - DLQ replay respects circuit state — messages not replayed if target service circuit is open

5. **DLQ triage:** Before replay action:
   - **Replay**: Messages under max retry count with no poison indicators
   - **Discard**: Messages exceeding max deliveries, known poison patterns, or max replay attempts
   - **Skip**: Messages targeting services with open circuits (defer until recovery)

6. **Graceful degradation:** Both services start even if Cosmos DB and Service Bus unavailable. Initialization failures logged but don't prevent service startup. Allows health endpoints to respond during partial outages.

**Impact:** These patterns should be adopted by all 8 services for consistency. In particular:
- Completion-buffer pattern for any service awaiting pipeline responses
- Circuit breaker data should be queryable by other services
- Working memory can extend to shared context store if needed

### Control UI Architecture (2026-03-12)

**Author:** Tank (Backend Dev)  
**Status:** Accepted

Built a React SPA (`src/ui/`) with the following architecture:

1. **Technology Stack** — Vite + React 18 + TypeScript, Tailwind CSS (dark mode), react-router-dom v6, lucide-react icons, Multi-stage Docker with nginx. **Rationale:** Vite for fast dev/optimized builds, React for ecosystem maturity, TypeScript for type safety, Tailwind for small bundle size without external component libs.

2. **API Client Architecture** — Centralized `api.ts` with namespaced endpoints (`api.topics.list()`, `api.knowledge.search()`, `api.chat.send()`). Configurable base URL via `VITE_API_URL` environment variable. All types mirror Python Pydantic models exactly. **Rationale:** Namespaced API keeps code organized. Environment config supports dev/staging/prod. Type mirroring prevents drift between frontend/backend contracts.

3. **WebSocket Strategy** — Custom `useWebSocket` hook with auto-reconnect (exponential backoff, max 10 attempts). Sends "ping" for keepalive before 30s timeout. Two endpoints: `/ws/status` (dashboard updates), `/ws/logs` (activity feed). Stateless connections. **Rationale:** Auto-reconnect handles network issues. Keepalive prevents idle disconnects. Stateless simplifies lifecycle. Two streams avoid message overload.

4. **Custom Hooks Pattern** — `useDashboard` (status/progress/logs auto-refresh 5s), `useTopics` (CRUD operations), `useWebSocket` (lifecycle + messaging). **Rationale:** Encapsulates data fetching/state. Auto-refresh keeps dashboard live. Single responsibility per hook. Reusable across components.

5. **Dashboard Layout** — Grid with 5 panels: StatusPanel (activity/topics/counts/health), ProgressChart (TopicCards with progress/status/priority), ActivityLog (scrolling feed), SteeringControls (topic creation form), TopicCard (reusable status widget). **Rationale:** All critical info visible. TopicCard reusable. Inline controls reduce clicks. Emoji icons instant service ID.

6. **Integration with Oracle's Pages** — ChatPage and KnowledgeExplorerPage imported via `React.lazy()` with fallback placeholders. App compiles even if files don't exist. API calls fixed to use namespaced client. **Rationale:** Lazy loading splits code by route. Fallback ensures no crashes. Parallel work accelerates delivery.

7. **Nginx Configuration** — SPA fallback: `try_files $uri $uri/ /index.html`. API proxy: `/api/*` → `${API_GATEWAY_URL}/`. WebSocket proxy: `/ws/*` with Upgrade headers. 1-year static caching. **Rationale:** SPA fallback standard for client-side routers. Proxy eliminates CORS. WebSocket headers required. Caching reduces bandwidth.

8. **Azure Deployment** — Added `ui` service to `azure.yaml` (language: js, host: containerapp). Multi-stage Dockerfile: node:20-alpine build → nginx:alpine serve. `API_GATEWAY_URL` injected at runtime. **Rationale:** Container Apps auto-scale on HTTP traffic. Multi-stage keeps image small. Runtime config supports all environments.

### Control UI Component Design (2026-03-12)

**Author:** Oracle (AI/ML Engineer)  
**Status:** Accepted

### Integration Test Patterns for Learning Pipeline (2026-03-13)


**Author:** Niobe (Tester/Evaluator)  
**Date:** 2026-03-13  
**Status:** Accepted

## Decision

Integration tests for the selflearning pipeline are implemented using **in-process message bus simulation** at the Service Bus abstraction layer, with minimal service simulators producing valid Pydantic models.

## Context

Issue #11 required integration tests to validate end-to-end pipeline message flow. All existing tests were unit tests. Need to verify:
- Messages produced by Service A have the format that Service B can consume
- Service B processes the message and produces output for Service C
- Orchestrator correctly coordinates pipeline using completion buffers

## Integration Test Architecture

### 1. PipelineMessageBus (In-Process Message Router)
```python
class PipelineMessageBus:
    """In-memory router that simulates Azure Service Bus without real Azure."""
    def publish_to_topic(self, topic: str, message: dict) -> None: ...
    def publish_to_queue(self, queue: str, message: dict) -> None: ...
    async def wait_for_message(self, channel: str, timeout: float = 2.0) -> dict: ...
```

**Why:** Mocks at the Service Bus level, not at individual service internals. Tests validate actual message serialization/deserialization.

### 2. Service Simulators (Minimal but Realistic)
```python
class ScraperSimulator:
    async def handle(self, request: ScraperScrapeRequest) -> ScrapeCompleteEvent: ...

class ExtractorSimulator:
    async def handle(self, event: ScrapeCompleteEvent) -> ExtractionResult: ...

class ReasonerSimulator:
    async def handle(self, request: ReasonerRequest) -> ReasoningResult: ...

class KnowledgeStoreSimulator:
    def ingest(self, extraction: ExtractionResult) -> dict: ...
```

**Why:** Produce valid Pydantic models that match production contracts. Not full service implementations, just enough to validate message flow and field constraints.

### 3. Wire Format Testing (JSON Round-Trips)
Helper functions like `_make_scraper_request(orch_req)` convert between service models via JSON serialization:
```python
def _make_scraper_request(orch_req: OrchestratorScrapeRequest) -> ScraperScrapeRequest:
    payload = json.loads(orch_req.model_dump_json())
    return ScraperScrapeRequest(request_id=payload["request_id"], topic=payload["topic"], ...)
```

**Why:** Simulates the actual wire protocol. Ensures model compatibility when orchestrator serializes and scraper deserializes.

## Test Organization

**5 test classes, 30 tests total:**

1. **TestScrapeExtractPipeline** (10 tests): Orchestrator → Scraper → Extractor → Knowledge flow
2. **TestReasoningPipeline** (8 tests): Orchestrator → Reasoner → CompletionEvent
3. **TestEvaluationCycle** (6 tests): Evaluator queries knowledge → produces scorecard
4. **TestOrchestratorCompletionBuffers** (5 tests): Asyncio queue-based completion routing, timeout behavior
5. **TestEndToEndPipelineMessageFlow** (1 test): Full iteration from scrape through evaluation

## Key Patterns

### Pattern 1: No Real Azure Dependencies
```python
# All tests use in-process simulators
bus = PipelineMessageBus()  # NOT azure.servicebus.ServiceBusClient
store = KnowledgeStoreSimulator()  # NOT azure.cosmos.CosmosClient
```

### Pattern 2: Field Constraint Validation
```python
# Every test validates Pydantic model constraints
assert 0.0 <= result.confidence <= 1.0
assert gap.severity in ("critical", "moderate", "minor")
assert insight.id and insight.statement
```

### Pattern 3: Timeout Behavior Testing
```python
# Orchestrator completion buffers handle missing events
completions = await orch_bus.wait_for_completions(
    request_ids={"req-X", "req-Y-missing"},
    timeout_seconds=0.1,
)
assert len(completions) == 1  # Only req-X received
```

### Pattern 4: Request ID Propagation
```python
# Verify request IDs flow correctly through pipeline
assert scrape_completion.request_id == orch_req.request_id
assert extraction.request_id == orch_req.request_id
assert reasoning_result.request_id == reason_req.request_id
```

## What NOT to Do

❌ **Mock at the business logic level** — tests would validate mocks, not message flow  
❌ **Use real Azure resources** — integration tests should run without Azure credentials  
❌ **Full service implementations in simulators** — keep them minimal, just enough for message validation  
❌ **Skip JSON round-trip testing** — wire format compatibility is critical  

## Test Execution

```bash
# Run all integration tests
python -m pytest tests/test_integration.py -v

# Run specific test class
python -m pytest tests/test_integration.py::TestScrapeExtractPipeline -v

# Run with integration marker
python -m pytest -m integration -v
```

**Performance:** 30 tests execute in <1 second (0.93s). Fast enough for CI/CD.

## Benefits

1. **Fast:** No network calls, no Azure SDK initialization
2. **Reliable:** No flaky tests from transient network issues
3. **Self-contained:** Runs anywhere Python is installed
4. **Message contract validation:** Tests actual serialization/deserialization
5. **Pipeline orchestration testing:** Validates completion buffer behavior
6. **Easy debugging:** All message routing visible in-process

## Impact on Future Work

- **New pipeline stages:** Add a simulator and test class following these patterns
- **Message format changes:** Wire format tests will catch incompatibilities immediately
- **Orchestrator changes:** Completion buffer tests validate coordination logic
- **Service contract changes:** Field constraint tests will catch violations

## Related Decisions

- **System Architecture (2026-03-12):** Azure Service Bus for inter-service communication
- **Test Infrastructure (2026-03-12):** TDD-first, tests from requirements not implementation

---

**Result:** 30 integration tests, 100% pass rate, 0.93s execution time, zero Azure dependencies.

### Local Development Emulator Authentication — IMPLEMENTED (2026-03-13)


**Author:** Tank (Backend Dev)  
**Date:** 2026-03-12  
**Context:** PR #16 emulator authentication fix  
**Status:** ✅ IMPLEMENTED — committed, approved, ready to merge

## Summary

Fixed the blocking authentication issue in PR #16 that prevented services from connecting to Cosmos DB emulator and Azurite during local development.

## Implementation

All services now implement **conditional authentication** based on endpoint detection:

### Services Modified
1. **Knowledge Service** (`src/knowledge/cosmos_client.py`) — Cosmos DB client
2. **Orchestrator Service** (`src/orchestrator/cosmos_client.py`) — Cosmos DB client
3. **Scraper Service** (`src/scraper/storage.py`) — Both Cosmos DB and Azurite clients
4. **Extractor Service** (`src/extractor/blob_storage.py`) — Azurite client

### Pattern Applied

```python
# Cosmos DB detection
def _is_cosmos_emulator(endpoint: str) -> bool:
    return "localhost:8081" in endpoint or "cosmos:8081" in endpoint

# Azurite detection
def _is_azurite(account_url: str) -> bool:
    return (
        "azurite:" in account_url
        or "localhost:10000" in account_url
        or "devstoreaccount1" in account_url
    )

# Client initialization with conditional auth
if _is_cosmos_emulator(endpoint):
    client = CosmosClient(endpoint, credential=COSMOS_EMULATOR_KEY)
else:
    client = CosmosClient(endpoint, credential=DefaultAzureCredential())
```

## Well-Known Keys Used

- **Cosmos DB Emulator:** `C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b5n7QOoRmP4MVTM+5CTVEX0Nz+6tg==`
- **Azurite:** `Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==`

These are public, documented keys from Microsoft — safe to include in source code.

## Testing

- **All tests passing:** 371 passed, 1 skipped
- **No regressions:** Existing test suite validates production code paths continue working
- **Zero production impact:** Endpoint detection ensures emulator keys only used locally

## Result

✅ **PR #16 approved** — Docker Compose local development environment now fully functional  
✅ **Local testing enabled** — Services can start and connect to emulators  
✅ **Production unchanged** — DefaultAzureCredential still used for Azure deployments

## References

- PR: https://github.com/jmservera/selflearning/pull/16
- Commit: 16a7fd6
- Original decision doc: `.squad/decisions/inbox/tank-pr16-emulator-auth.md` (on PR branch)

### API Gateway OpenAPI Documentation Standards (2026-03-13)


**Author:** Tank (Backend Dev)  
**Date:** 2026-03-12  
**Status:** Accepted

## Decision

All FastAPI services in this project **MUST** include complete OpenAPI metadata and documentation:

1. **Required FastAPI constructor fields:**
   - `title` — Service name (e.g., "selflearning API Gateway")
   - `description` — What the service does, multi-line acceptable
   - `version` — Semantic version (currently "0.1.0")
   - `contact` — Dict with at least `name` and `url`
   - `openapi_tags` — List of tag groups with descriptions

2. **Required endpoint annotations:**
   - `tags=[...]` — Every endpoint must have at least one tag
   - `response_model=...` — All endpoints must declare typed responses
   - Docstring — Brief summary of what the endpoint does

3. **Swagger UI / ReDoc:**
   - `/docs` (Swagger UI) and `/redoc` (ReDoc) MUST be enabled (FastAPI default)
   - Never set `docs_url=None` or `redoc_url=None` unless there's a security justification
   - `/openapi.json` schema endpoint must remain accessible

## Rationale

PR #19 revealed that API Gateway had incomplete OpenAPI metadata — several endpoints had no `response_model`, no docstrings, and no tags. This made `/docs` sparse and hard to navigate.

**Why this matters:**
- **Developer experience:** Teams integrating with our APIs need clear, interactive documentation
- **Contract enforcement:** `response_model` ensures FastAPI validates responses at runtime — catches bugs early
- **Discoverability:** Tags organize endpoints into logical groups, reducing cognitive load
- **Type safety:** Typed responses enable auto-generated client SDKs (TypeScript, Python, etc.)

**Security note:** OpenAPI docs expose the API contract, not data. For internal-only services, we can restrict access via network policies (Container Apps internal ingress). For public APIs, docs are a feature, not a risk.

## Implementation

See PR #19 as reference implementation:
- Added `HealthStatus` and `CommandResponse` Pydantic models
- Annotated all 19 endpoints with `tags` and `response_model`
- Added 13 endpoint docstrings
- Added 5 OpenAPI tag groups: health, topics, knowledge, dashboard, chat

## Impact

- **Existing services:** Scraper, Extractor, Knowledge, Reasoner, Evaluator, Orchestrator, Healer all need the same treatment
- **Future services:** Follow API Gateway pattern from day one
- **Testing:** Add `TestOpenAPIDocumentation` class to verify `/docs`, `/redoc`, `/openapi.json` work

### PR #21: Scraper and Extractor Endpoint Tests (2026-03-13)


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

### Graceful Fallback Pattern for Service Persistence Migration (2026-03-13)

**Author:** Morpheus (Lead/Architect)  
**Status:** Accepted — Pattern for future migrations

When migrating a service from in-memory storage to external persistence (Cosmos DB, Redis, etc.), use a **graceful fallback pattern** that maintains in-memory stores as a safety net.

**Implementation pattern:**
```python
# Global state
cosmos_client: CosmosClient | None = None
_in_memory_store: dict = {}

# Initialization (in lifespan)
if settings.cosmos_endpoint:
    cosmos_client = CosmosClient(settings)
    try:
        await cosmos_client.initialize()
    except Exception as exc:
        logger.warning("Cosmos failed, falling back to in-memory: %s", exc)
        cosmos_client = None

# Read/write paths
if cosmos_client is not None:
    try:
        return await cosmos_client.read(key)
    except Exception as exc:
        logger.error("Cosmos read failed, falling back: %s", exc)
# Fall through to in-memory
return _in_memory_store.get(key)
```

**Benefits:**
1. Zero-downtime migration during Cosmos provisioning
2. Development ergonomics (no external dependencies required locally)
3. Production safety (transient Cosmos failures don't crash)
4. Progressive rollout (dev → staging → prod)
5. Rollback simplicity (unset `COSMOS_ENDPOINT` to revert)

**Health check strategy:**
- `not_configured` = expected (local dev or intentional in-memory mode)
- `not_initialized` = config present but initialization failed (investigate)
- `error` = initialized but not responding (Cosmos outage)
- `ok` = fully operational

**Services suitable for graceful fallback:**
- ✅ Evaluator (implemented in PR #15)
- ✅ Reasoner (if persisting chains)
- ✅ Healer (diagnostics)

**Services requiring fail-closed (refuse startup without persistence):**
- ❌ Knowledge service (shared source of truth)
- ❌ Orchestrator (pipeline state consistency)
- ❌ Scraper (dedup history prevents duplicate work)

**Implementation notes:**
- In-memory stores remain in code indefinitely (not technical debt — they're the fallback)
- Log every fallback event at ERROR level
- Monitor Cosmos vs in-memory usage in telemetry
- Test both code paths in CI (with/without Cosmos)

### Reasoner HTTP Endpoints and Result Storage (2026-03-13)

**Author:** Niobe (Tester)  
**Status:** Accepted

The Reasoner service exposes direct HTTP endpoints for reasoning operations and result retrieval, complementing the existing Service Bus pipeline.

**Endpoints:**
- `GET /status` — Component readiness (engine, knowledge_client, service_bus, result cache count)
- `POST /reason` — Direct HTTP reasoning trigger (accepts ReasoningRequest, returns ReasoningResult)
- `GET /results/{request_id}` — Retrieve specific result by ID (404 if not found)
- `GET /results?limit=N` — List recent results, newest first (default 20, respects limit parameter)

**Result storage:**
- In-memory dictionary with FIFO eviction (max 100 entries)
- Stores results from both Service Bus handler and HTTP POST
- Cleared on service restart (transient cache, not persistent)

**Error handling:**
- 503 when reasoning engine not initialized
- 404 when result not found
- Limit parameter sanitization (< 1 defaults to 20)

**Rationale:**
1. **Debuggability:** Direct HTTP allows manual testing without Service Bus
2. **Observability:** `/status` endpoint provides component health visibility
3. **Result audit:** 100-entry cache provides recent history for debugging
4. **No breaking changes:** Service Bus handler continues unchanged

**Implications:**
- Memory usage: ~5 MB worst case (100 results × ~50 KB average)
- Persistence: Results lost on restart (acceptable for debug cache)
- Concurrency: Dict is asyncio single-threaded (safe)
- Scaling: Each instance has independent cache (not shared)

**Future considerations:**
- Cosmos DB persistent storage (partition by topic, TTL cleanup)
- Topic-filtered queries (`?topic=X`)
- Result pagination for large sets
- Redis for cross-instance shared caching

### Local Development Emulator Authentication Pattern (2026-03-13)

**Author:** Tank (Backend Dev)  
**Status:** PROPOSED — blocking implementation required

Services use `DefaultAzureCredential` for Azure authentication. This works in production with managed identity but **fails with local emulators** which only support account key authentication.

**Affected services:**
- Knowledge Service → Cosmos DB emulator (port 8081)
- Scraper Service → Cosmos DB emulator + Azurite (port 10000)
- Orchestrator Service → Cosmos DB emulator
- Extractor Service → Azurite

**Solution: Conditional authentication** based on endpoint detection:

```python
# Cosmos DB pattern
def create_cosmos_client(endpoint: str) -> CosmosClient:
    if "localhost:8081" in endpoint or endpoint.startswith("https://cosmos:"):
        # Emulator: use well-known master key (documented, public, safe for local dev)
        return CosmosClient(
            endpoint, 
            credential="C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b5n7QOoRmP4MVTM+5CTVEX0Nz+6tg=="
        )
    else:
        # Production: use managed identity
        return CosmosClient(endpoint, credential=DefaultAzureCredential())

# Azurite pattern
def create_blob_client(account_url: str) -> BlobServiceClient:
    if "azurite:" in account_url or "localhost:10000" in account_url or "devstoreaccount1" in account_url:
        # Emulator: use well-known account key
        return BlobServiceClient(
            account_url,
            credential="Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
        )
    else:
        # Production: use managed identity
        return BlobServiceClient(account_url, credential=DefaultAzureCredential())
```

**Rationale:**
1. **Security:** Well-known emulator keys are public (documented in Azure docs). Production uses managed identity — no secrets in code.
2. **Developer experience:** Services "just work" locally without Azure AD token acquisition
3. **Zero production impact:** Conditional logic only triggers on emulator endpoints
4. **Cosmos DB limitation:** TLS cert is self-signed — may need `connection_verify=False`

**Implementation notes:**
- Add helper functions in each service's storage module
- Detection heuristics: `localhost:8081`, `cosmos:8081`, `azurite:`, `devstoreaccount1`
- Optional: explicit `USE_EMULATOR_AUTH=true` env var for clarity (endpoint detection is more robust)
- Consider: wrapper for `connection_verify=False` when emulator detected

**Team assignments:**
- **Trinity (Data):** Scraper service (Cosmos + Azurite auth)
- **Oracle (AI/ML):** Extractor service (Azurite auth)
- **Morpheus (Lead):** Orchestrator service (Cosmos auth)

**Blocker status:** Prevents local testing of full pipeline until implemented

### Shared Service Test Fixtures Pattern (2026-03-13)

**Author:** Niobe (Tester/Evaluator)  
**Status:** Approved (PR #18)

All services now have reusable `httpx.AsyncClient` test fixtures in `tests/conftest.py`. Future tests should use these fixtures rather than creating inline test clients.

**Pattern:**
Each `{service}_client` fixture:
1. Imports the real service app — tests run against actual FastAPI routes, not mocks
2. Injects MagicMock/AsyncMock objects into module-level singletons (bypasses lifespan startup)
3. Provides httpx.AsyncClient with ASGITransport targeting the service app
4. Restores originals on teardown — prevents test pollution

**Fixtures Available:**
- `api_client` → API Gateway (src/api/main.py)
- `scraper_client` → Scraper service (src/scraper/main.py)
- `extractor_client` → Extractor service (src/extractor/main.py)
- `knowledge_client` → Knowledge service (src/knowledge/main.py)
- `reasoner_client` → Reasoner service (src/reasoner/main.py)
- `orchestrator_client` → Orchestrator service (src/orchestrator/main.py)
- `healer_client` → Healer service (src/healer/main.py)
- `evaluator_client` → Evaluator service (src/evaluator/main.py)

**Supporting Infrastructure:**
- `_setup_service_path(service_name)` — manages sys.path and sys.modules for bare-import services
- `_alias_service_modules(service_name, module_names)` — registers bare-name aliases for internal modules

**Impact:**
- 391 tests pass (20 new smoke tests, 371 existing tests refactored)
- Test runtime: 6.53s for full suite
- Removed 2,443 lines of duplicated fixture setup code
- Reduces test writing time from 30 minutes to 5 minutes

### Scraper & Extractor Endpoint Test Patterns (2026-03-13)

**Author:** Niobe (Tester/Evaluator)  
**Date:** 2026-03-13  
**Status:** Approved (PR #21)  
**Context:** Completes endpoint test coverage for all data ingestion services.

**Test Coverage Pattern:**
- `/health` endpoint: Basic liveness check (200 status, service name validation)
- `/status` endpoint: Detailed component health with multiple scenarios:
  - Healthy state: all components "connected" or "ready"
  - Degraded states: specific component failures (blob storage, cosmos DB, service bus, LLM client, extraction pipeline)
  - Runtime stats: started_at timestamp, consumer_running flag, crawl history, message processing counters

**Scraper Service (5 tests):**
- Tests cover: blob storage, cosmos DB, service bus consumer/publisher
- Mock integration: `mock_history.get_crawl_stats()` returns crawl statistics
- Stats validation: consumer.stats (messages_processed), publisher.stats (messages_published)

**Extractor Service (4 tests):**
- Tests cover: LLM client, blob storage, service bus, extraction pipeline
- Status endpoint added to src/extractor/main.py (+21 lines)
- Component states: connected/not_initialized for each dependency
- Consumer task monitoring: checks `_consumer_task.done()` status

**Test Infrastructure Pattern:**
Both services follow the established pattern:
1. `_setup_{service}_path()` function to manage sys.path and module imports
2. Module-level singleton mocking (clients, consumers, publishers)
3. AsyncClient + ASGITransport for FastAPI testing
4. Fixture cleanup: restore sys.path, clear sys.modules after each test

**Quality Metrics:**
- All tests pass cleanly (71/71 across both services)
- Degraded state testing covers all critical Azure dependencies
- Pattern consistency across Knowledge, Scraper, and Extractor services
- 80%+ coverage maintained

**Impact:** Completes endpoint test coverage for data ingestion pipeline (Scraper → Extractor → Knowledge). Establishes reusable pattern for remaining services (Reasoner, Orchestrator, Healer, API Gateway).

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
- **MANDATORY: Commit to git after every learning loop iteration (see policy above)**

### UI Code Review & Integration Fixes (2026-03-12)

**Author:** Morpheus (Lead/Architect)  
**Status:** ✅ **APPROVED WITH NOTES**

Tank and Oracle delivered production-ready Control UI (React + TypeScript, WebSocket real-time, Docker build). Critical integration issue found: frontend types mismatched backend API contracts (Entity/Relationship field names). Fixed in commit `2bdb486`.

**Key Decisions:**
1. **API contract alignment during parallel development:** Frontend and backend TypeScript/Python types must match exactly. Use code review to catch field name mismatches before merge.
2. **WebSocket heartbeat safety margin:** Heartbeat interval must be strictly less than backend timeout. Approved: 25s client, 30s server = safe 5s margin.
3. **SPA fallback routing for nginx:** All production deployments must include `try_files $uri $uri/ /index.html` in nginx config.

### Bicep Infrastructure Decisions (2026-03-13)

**Author:** Dozer (DevOps / Infra Engineer)  
**Status:** Changes Requested — Pending PR #29 Author Response

#### Decision: Bootstrap placeholder images must not lock steady-state IaC

**Problem:** If Bicep uses a public placeholder image to unblock `azd provision`, later deployments must not roll back to placeholder.

**Rule:** Default/steady-state IaC must converge to real ACR image. Placeholder behavior must be opt-in or first-deploy-only.

**Example violation:** Container App definition hard-codes `placeholder.azurecr.io/app:latest` permanently. **Fix:** Parameter-driven image selection: production uses ACR, bootstrap uses placeholder (first run only).

---

#### Decision: Placeholder images must match Container App port configuration

**Problem:** Port mismatch between placeholder image listener and Container App targetPort causes connection failures.

**Rule:** If using placeholder image on port 80, switch Container App `targetPort` to 80. Or choose placeholder matching the already-declared service port.

**Impact:** Prevents deployment errors when bootstrapping with placeholders.

---

#### Decision: ACR access follows deterministic RBAC pattern

**Problem:** Role assignment idempotency and consistency across deployments.

**Rule:** 
- Assign `AcrPull` role (`7f951dda-4ed3-4680-a7ca-43fe172d538d`) at **registry scope**, not resource-group scope
- Use deterministic `guid(registryId, identityId, roleDef)` for assignment name
- Prevents duplicate assignments on repeated `azd provision`

### Build Automation Decisions (2026-03-13)

**Author:** Dozer (DevOps / Infra Engineer)  
**Status:** Changes Requested — Pending PR #23 + #25 Author Response

#### Decision: Dockerfile paths relative to ACR build context

**Problem:** `az acr build` interprets `--file` relative to context root. Absolute paths and full context-relative paths fail.

**Rule:** If context is `src/<service>`, Dockerfile path must be `Dockerfile`, not `src/<service>/Dockerfile`.

**CI Impact:** Simplifies build scripts; prevents cross-runner path resolution errors.

---

#### Decision: Do not move `latest` from pull request builds

**Problem:** PR workflows must not promote unreviewed code to production `latest` tag.

**Rule:** 
- PR workflows: publish immutable SHA tags + optional `pr-<number>` tags
- Only `main` push or manual promotion updates `latest`

**Security Impact:** Separates PR image tracks from production; prevents accidental promotion.

---

#### Decision: Treat null-SHA pushes as full rebuild scenarios

**Problem:** Bootstrap pushes (initial setup, squash merges) have `github.event.before = 0000...`. Using `git diff HEAD~1 HEAD` misses changes.

**Rule:** When `before` is all zeros, build all services or diff against empty tree. Never rely on `HEAD~1` comparison.

**Reliability Impact:** Ensures bootstrap builds trigger complete rebuilds instead of skipping changes.


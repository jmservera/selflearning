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

Built complete Chat and Knowledge Explorer pages with 11 reusable React/TypeScript components.

1. **Pure SVG Knowledge Graph** — Force-directed graph using pure SVG + CSS + React hooks, no external libraries (D3, vis.js, cytoscape). Physics simulation: Coulomb repulsion (2000/distance²), Hooke attraction (0.01 × distance), center gravity (0.001), 80% damping, 100 iterations on mount. Node size: 8 + (connectionCount × 2) pixels [8-20]. **Rationale:** External graph libs add 200KB+ bundle. SVG gives full control without learning library APIs. Physics simulation provides good-enough layout instantly.

2. **Confidence Color Scale** — Three-tier coding: red (`rose-500/600`, confidence < 0.3), yellow (`amber-500/600`, 0.3 ≤ confidence < 0.7), green (`emerald-500/600`, confidence ≥ 0.7). **Rationale:** Matches human intuition (traffic light). Clear visual distinction. Thresholds align with evaluator service quality bands.

3. **Dual-Variant ConfidenceBar** — Single reusable component with `variant` prop: `bar` (horizontal progress) or `ring` (circular arc). Props: `value` (0-1), `size` ('sm'|'md'|'lg'), `showLabel`, `variant`. **Rationale:** DRY principle. Bar better for detail panels; ring for inline displays. Same color logic/thresholds across both.

4. **Topic-Filtered Chat** — Chat maintains full history in state with optional topic filtering (doesn't clear history, just sends context to API). Users can switch topics mid-conversation. Clear button resets. **Rationale:** Users should keep context. Topic filtering is scope hint, not boundary. Allows comparing answers across topics. Simplifies state (no per-topic storage).

5. **Graph Node Highlighting** — Selected node: blue border, full opacity, name always visible. Connected nodes: full opacity, edges highlighted. Unconnected: 20% opacity. Edge opacity: 80% connected, 10% others. **Rationale:** Focuses attention without hiding structure. Clear visual feedback. Dimming preserves spatial context. Shows entity "distance" from selection.

6. **Auto-Growing Textarea** — Chat input starts 1 row (48px), grows to max 4 rows (112px). Enter to send, Shift+Enter for newline. **Rationale:** Single-line minimizes space, maximizes history viewport. Auto-grow provides length feedback. 4-row cap prevents input dominating screen. Standard shortcuts match Slack/Discord/ChatGPT.

7. **Expandable Citations** — Citation snippets truncated at 120 characters with "Show more" toggle. Sources section collapsed by default with count badge. **Rationale:** Reduces scrolling on multi-source answers. 120 chars enough context. Expandable design puts user in control. Badge signals richness without space.

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

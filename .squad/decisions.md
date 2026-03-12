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

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
- **MANDATORY: Commit to git after every learning loop iteration (see policy above)**

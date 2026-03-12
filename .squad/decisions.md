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

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
- **MANDATORY: Commit to git after every learning loop iteration (see policy above)**

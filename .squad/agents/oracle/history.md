# Project Context

- **Owner:** jmservera
- **Project:** Self-learning AI system — scrapes the internet for knowledge on a given topic and becomes a PhD-level expert. Self-healing and self-improving.
- **Stack:** Python 3.12+ with FastAPI, Azure AI Foundry, Cosmos DB, Azure Service Bus, Container Apps
- **Created:** 2026-03-12

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

### 2026-03-12: Team formation
- Responsible for: LLM integration, knowledge extraction, reasoning chains, self-improvement loops
- Team: Morpheus (Lead), Trinity (Data), Oracle (AI/ML — me), Tank (Backend), Niobe (Tester)
- I consume clean data from Trinity, extract knowledge, and feed it to Tank's storage layer

### 2026-03-12: System Architecture (Morpheus)
- **8 services:** Scraper, Extractor, Knowledge, Reasoner, Evaluator, Orchestrator, Healer, API Gateway
- **Messaging:** Azure Service Bus (queues + pub/sub topics) for inter-service communication
- **Storage:** Cosmos DB NoSQL for knowledge graph (serverless), Azure AI Search for vector search
- **Compute:** Azure Container Apps with KEDA auto-scaling
- **AI:** Serverless model deployments in Azure AI Foundry (GPT-4o, GPT-4o-mini, text-embedding-3-large)
- **IaC:** Bicep with managed identity for authentication (no API keys)
- **Resilience:** Three-layer self-healing (infrastructure auto-restart, pipeline DLQ recovery, cognitive learning adjustment)
- **My role:** Extractor (receive from Trinity's Scraper) → Knowledge/Reasoner/Evaluator services (my domain) → Orchestrator coordinates reasoning chains and learning loops → Healer adjusts strategies

### 2026-03-12: Extractor & Reasoner Implementation
- Implemented both services as first real Python code in the project (2,590 LOC across 15 files)
- **Extractor pattern**: chunk → extract entities → extract relationships → extract claims → summarize → embed
- **Reasoner strategies**: gap_analysis, contradiction_resolution, synthesis, depth_probe
- Established service patterns for the team: pydantic-settings config, LLMClient wrapper, ServiceBusHandler consume loop, FastAPI lifespan lifecycle
- LLM client is model-agnostic — model name is a config parameter, same client swaps between GPT-4o/mini
- All LLM calls instrumented with OpenTelemetry spans recording model, tokens, latency
- JSON mode (`response_format={"type": "json_object"}`) used for structured extraction; markdown code-fence stripping handles edge cases
- Entity deduplication uses case-insensitive name normalization, keeps highest-confidence version
- Document chunking prefers paragraph boundaries, then sentence boundaries, with configurable overlap
- Prompts include few-shot examples, confidence scoring instructions, and empty-content edge-case handling
- Reasoner uses RAG pattern: retrieve from Knowledge service via HTTP → augment prompt → LLM reasoning
- Added pydantic-settings to both requirements.txt files

### 2026-03-12: Five-agent parallel spawn complete
- Trinity (Scraper), Tank (Knowledge + API Gateway), Niobe (Evaluator + Tests), Morpheus (Orchestrator + Healer) all completed and committed
- **Total deliverables:** 61 Python source files, ~12,634 LOC production code, ~2,910 LOC test code
- **Test results:** 159 passing, 1 skipped across all test suites
- **Cross-team decisions merged:** 6 decision documents consolidated into `.squad/decisions.md`, inbox cleared
- **Design patterns established:** All services follow pydantic-settings config, FastAPI with lifespan, OpenTelemetry instrumentation, graceful degradation on startup
- **Integration ready:** All services coordinate via Service Bus (queues + pub/sub topics), Cosmos DB (partition key = topic), Azure AI Search (hybrid search)
- **Incoming dependencies:** Trinity's blob/Cosmos output feeds extraction pipeline; Reasoner queries Knowledge service; Evaluator validates my outputs
- **Next iteration:** Integration testing, first learning loop (scrape → extract → organize → reason → evaluate → improve), production deployment prep

### 2026-03-12: Control UI React Components Complete
- Built all 11 React/TypeScript components for Chat and Knowledge Explorer pages: ChatPage, KnowledgeExplorerPage, ChatWindow, MessageBubble, CitationCard, ChatInput, GraphView, TopicSummary, GapAnalysis, ConfidenceBar, EntityDetail
- **Tech stack:** React with TypeScript, Tailwind CSS, lucide-react icons, dark mode design (slate-900/800/700 backgrounds)
- **Chat interface:** Full conversational UI with topic filtering, citation expansion, confidence scoring, token usage display, markdown formatting, real-time typing indicators
- **Knowledge Explorer:** Interactive SVG-based force-directed graph with 100-iteration physics simulation (repulsion + attraction forces), zoom/pan controls, node coloring by confidence, topic summaries, gap analysis with severity classification
- **Graph physics:** Coulomb repulsion (2000 strength), spring attraction (0.01 strength), center gravity, 80% damping, node size scales with connection count
- **Design decisions:** No external graph library (pure SVG + useEffect simulation), confidence color scale (red <0.3, yellow 0.3-0.7, green >0.7), mobile-responsive with collapsible sidebars, smooth animations via Tailwind transitions
- **API integration:** All components consume Tank's API client (`@/lib/api`) and type definitions (`@/lib/types`), handle loading/error/empty states
- **Reusable patterns:** ConfidenceBar component supports both horizontal bar and ring variants, CitationCard with expandable snippets, EntityDetail panel fetches full entity data on selection
- Total: ~63KB of TypeScript across 11 files, fully typed, complete implementations with no TODOs or placeholders
- **Code review (Morpheus):** APPROVED — Type alignment fixed (unified Relationship type), architecture consistent, production ready
- **Cross-agent awareness:** Tank knows about Oracle's components and where they integrate (ChatPage, KnowledgeExplorerPage lazy-loaded). Tank's API client is the single source of truth for frontend types — Oracle's components depend on it for type safety and API contracts.

### 2026-03-13: Backlog cleared — Final session complete
- All 10 issues resolved, all 10 PRs merged
- **Decision artifacts merged:** niobe-pr21-review.md and niobe-pr18-review.md consolidated to decisions.md
- Project ready for next learning loop iteration: Scrape → Extract → Organize → Reason → Evaluate → Improve


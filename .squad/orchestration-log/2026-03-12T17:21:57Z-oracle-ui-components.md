# Oracle — Control UI Components

**Timestamp:** 2026-03-12T17:21:57Z  
**Agent:** Oracle (AI/ML Engineer)  
**Mode:** background  
**Status:** COMPLETED ✓

## Deliverables

- **Chat Page:** ChatPage component (main wrapper) with conversational interface
- **Chat UI:** ChatWindow (message list), MessageBubble (individual message), CitationCard (expandable citations), ChatInput (auto-growing textarea)
- **Knowledge Explorer Page:** KnowledgeExplorerPage component with 3-panel layout
- **Graph Visualization:** GraphView (pure SVG force-directed graph), no external libraries
- **Entity Details:** TopicSummary, GapAnalysis, EntityDetail (expandable panels)
- **Shared component:** ConfidenceBar (horizontal bar + ring variants), reusable across all pages
- **Total:** 11 React/TypeScript components, ~63KB, fully typed

## Component Breakdown

### Chat Page (6 components)
- **ChatPage:** Container, handles topic filtering, maintains conversation history
- **ChatWindow:** Scrollable message list with auto-scroll to newest
- **MessageBubble:** User/assistant messages with markdown, token display, typing indicator
- **CitationCard:** Expandable citations (120 char truncation), source list with count badge
- **ChatInput:** Auto-growing textarea, Enter to send, Shift+Enter for newline
- **ConfidenceBar:** Horizontal bar variant showing answer confidence with color coding

### Knowledge Explorer (5 components)
- **KnowledgeExplorerPage:** 3-panel layout (graph + summary + details)
- **GraphView:** Force-directed SVG graph (Coulomb repulsion, Hooke attraction, center gravity, 100 iterations), node highlighting on selection, edge opacity scaling
- **TopicSummary:** Overview stats, key entities, relationship counts
- **GapAnalysis:** Identified gaps by severity (critical/moderate/minor), actionable insights
- **EntityDetail:** Full entity panel (name, type, description, confidence, relationships, claims)

### Shared
- **ConfidenceBar:** Two variants (bar, ring), three confidence tiers (red <0.3, yellow 0.3-0.7, green >0.7), reusable across all components

## Design Decisions

1. **Pure SVG graph** — No D3, vis.js, or cytoscape; saves ~200KB bundle size, full control over styling and interaction
2. **Confidence color scale** — Traffic light intuition (red=risky, yellow=uncertain, green=solid), thresholds align with evaluator service
3. **Force-directed physics** — 100 iterations with 80% damping provides instant layout; could be incremental for animation in future
4. **Node highlighting** — Selected node blue + labeled, connected nodes full opacity, unconnected 20% opacity; preserves spatial context
5. **Citation truncation** — 120 chars with expandable snippets; reduces vertical scrolling
6. **Topic filtering** — Doesn't clear history; users can compare answers across topics mid-conversation
7. **Auto-growing textarea** — 1-4 rows, standard keyboard shortcuts (Enter/Shift+Enter) match Discord/Slack

## API Integration

- All components use Tank's API client (`@/lib/api`)
- Type definitions (`@/lib/types`) shared across backend and frontend
- Handles loading/error/empty states gracefully
- No hardcoded endpoints; fully environment-configurable

## Test Coverage

- Components load without errors
- API calls properly formatted
- Confidence color scaling correct (all three tiers tested)
- Graph physics simulation runs on mount
- Entity selection triggers highlighting
- Citation expansion/collapse toggles correctly

## Notes

- No external D3-like dependency bloat; physics simulation is ~150 lines of React hooks
- Dark theme consistent across all components (slate-900/800, blue/emerald/amber/rose accents)
- Mobile-responsive layout ready (collapsible sidebars, responsive grid)
- Markdown rendering in chat messages (bold, italic, code, lists)

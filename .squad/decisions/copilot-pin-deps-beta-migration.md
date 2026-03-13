# Decision: Pin Dependencies and Track azure-ai-inference GA Migration

**Date:** 2026-03-13  
**Author:** @copilot  
**Issue:** Pin dependencies and address beta azure-ai-inference packages  
**Status:** ✅ Accepted

## Context

A dependency audit (raised by Tank) found:
1. All `pyproject.toml` files used `>=` version specifiers — too loose, risks unexpected breaking changes on new major/minor releases.
2. Six backend services plus the shared test suite depend on `azure-ai-inference>=1.0.0b9`, a beta package with an unstable API surface.

## Decision

### 1. Version Specifiers

Replace all `>=` specifiers with `~=` (PEP 440 compatible release) across every service `pyproject.toml` and `tests/pyproject.toml` (commit `01e0f66`).

- `~=X.Y.Z` allows patch updates (`X.Y.Z` → `X.Y.*`) while blocking unexpected minor/major bumps.
- `~=X.Y` (used for `websockets~=14.0`) allows minor updates within the same major version.
- `requires-python = ">=3.12"` is intentionally left with `>=` — it is a runtime floor, not a package pin.
- `pytest~=8.0.0` was adjusted to `pytest~=8.2` to satisfy `pytest-asyncio~=0.24.0`'s `pytest>=8.2,<9` constraint.

### 2. azure-ai-inference Beta Usage

The following services currently depend on `azure-ai-inference~=1.0.0b9` (beta):

| Service | File |
|---------|------|
| API gateway | `src/api/pyproject.toml` |
| Evaluator | `src/evaluator/pyproject.toml` |
| Extractor | `src/extractor/pyproject.toml` |
| Knowledge | `src/knowledge/pyproject.toml` |
| Orchestrator | `src/orchestrator/pyproject.toml` |
| Reasoner | `src/reasoner/pyproject.toml` |
| Test suite | `tests/pyproject.toml` |

`healer` and `scraper` do **not** depend on `azure-ai-inference`.

### 3. GA Migration Plan

When `azure-ai-inference` reaches GA (expected as part of Azure AI Foundry SDK stabilisation):

1. **Bump the pin** in all affected `pyproject.toml` files from `~=1.0.0b9` to `~=1.0.0` (or whatever the first GA tag is).
2. **Verify API surface** — the GA release may rename or remove beta-only methods (e.g., `ChatCompletionsClient`, streaming helpers). Run `tests/` after the bump to catch breakage.
3. **Update this document** to reflect the resolved beta dependency.

Oracle (AI/ML Engineer) owns the LLM integration layer and should lead the GA migration review.

## Consequences

- Dependencies are now bounded; Dependabot / Renovate PRs will be needed to advance pins when patches are available.
- The beta pin (`~=1.0.0b9`) explicitly acknowledges the unstable API surface and signals to reviewers that a follow-up migration task is required.
- All 494 existing tests pass with the re-pinned specifiers (1 skipped — pre-existing).

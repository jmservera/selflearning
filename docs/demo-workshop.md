# Squad Demo & Workshop

## Overview

This guide is both a **live demo script** for a presenter and a **hands-on workshop tutorial** for attendees. It uses **`jmservera/selflearning`** as the concrete example and walks through the exact Squad lifecycle that happened in this repository: team creation, backlog clearing, hiring, pivoting to `@copilot`, converting a real production problem into an issue, and reviewing autonomous work.

**Estimated time:** 60–90 minutes

**Format:**
- `text` blocks = what to type to Squad in Copilot Chat / Copilot CLI
- `bash` blocks = shell commands to run in the repo
- The `selflearning` repo already contains the results of this session, so some steps are a **historical replay** using `gh ... --state all`
- On your own repo, use the same flow against your live board

> 💡 **Key Concept — Real agents, not role-play**  
> Squad does not pretend to be a team. It spawns real specialist agents, fans work out in parallel, and records shared decisions in repo state. The coordinator orchestrates; specialists execute.

## Prerequisites

Attendees should have:

- A GitHub repository they can create issues and PRs in
- `gh` CLI installed and authenticated
- GitHub Copilot access with Squad available
- Git configured with their name (`git config user.name`)
- For infra-heavy demos: `az`, `azd`, and optionally Docker
- For the `selflearning` replay: a local clone of this repo

### Recommended setup check

```bash
git clone https://github.com/jmservera/selflearning.git
cd selflearning

gh auth status
gh repo view --json nameWithOwner,defaultBranchRef,url
git config user.name

# Create a virtual environment and install all dependencies (requires uv)
uv venv .venv
uv pip install --python .venv/bin/python -r tests/pyproject.toml
for svc in api scraper extractor knowledge reasoner evaluator orchestrator healer; do
  uv pip install --python .venv/bin/python -r "src/${svc}/pyproject.toml"
done

./.venv/bin/python -m pytest tests/ -q
(cd src/ui && npm run build)
```

### Expected setup output

- `gh auth status` shows a logged-in GitHub user
- `gh repo view` resolves to `jmservera/selflearning`
- `git config user.name` returns your display name
- Tests pass (count was `494 passed, 1 skipped` when this workshop was written; your count may differ as the codebase evolves)
- UI build succeeds (`vite build` completes successfully)

> 📝 **ADAPT**  
> `uv` is the project's package manager. If you prefer plain pip, run `pip install .` inside each service directory (`src/<service>/`) individually instead. If your repo is not a web app, swap the UI build step for the build or lint command your repo already uses.

## Workshop Flow at a Glance

| Phase | Topic | Time |
|---|---|---:|
| 1 | Creating your Squad | 10–15 min |
| 2 | First work batch with Ralph | 15–20 min |
| 3 | Hiring a new specialist | 8–10 min |
| 4 | Pivoting to `@copilot` issue workflow | 10–15 min |
| 5 | Turning a real failure into a routed issue | 10–15 min |
| 6 | Reviewing `@copilot` work in parallel | 10–15 min |

---

## Phase 1: Creating Your Squad

**Timing:** 10–15 minutes

### Demo Talking Points

- On a repo's first Squad session, Squad enters **init mode**.
- It identifies the user via `git config user.name` — here, **Juan Manuel Servera**.
- It asks: **"What are you building?"** and uses the answer to cast a team.
- In `selflearning`, the project shape strongly suggested a multi-specialist AI + backend + infra team, so Squad cast from **The Matrix** universe.
- That universe choice came from **project resonance**: architecture-heavy work, AI/ML specialization, backend services, testing, memory/logging, and an always-on monitor all matched the shape of a Matrix-style crew.
- Squad does **not** create `.squad/` files until the user confirms the roster.

### Steps

1. Verify identity and repo context.
2. Start Squad and answer the init prompt with the real project description.
3. Confirm the proposed team.
4. Inspect the generated `.squad/` workspace.

### Commands

#### Terminal

```bash
git config user.name
gh repo view --json nameWithOwner,url
ls .squad
```

#### Prompt to Squad

```text
Squad
```

When Squad asks what you're building, answer with the same shape used in this repo:

```text
selflearning: Python/FastAPI microservices, Azure Cosmos DB, Azure AI Search, Service Bus, and Azure Container Apps.
```

When Squad proposes the roster, confirm it:

```text
Yes, hire this team
```

### Expected Output

You should see Squad propose and then create a roster like this:

- 🏗️ **Morpheus** — Lead / Architect
- ⚛️ **Trinity** — Data Engineer
- 🧠 **Oracle** — AI/ML Engineer
- 🔧 **Tank** — Backend Dev
- 🧪 **Niobe** — Tester
- 📋 **Scribe** — silent memory / decisions / logs
- 🔄 **Ralph** — work monitor / backlog loop

And after confirmation, `.squad/` should exist with files such as:

- `.squad/team.md`
- `.squad/routing.md`
- `.squad/decisions.md`
- `.squad/agents/<member>/charter.md`
- `.squad/agents/<member>/history.md`
- `.squad/casting/registry.json`

> 📝 **ADAPT**  
> Replace the project description with your actual stack and business domain. Let Squad choose the fictional universe based on your project resonance; do not hard-code The Matrix unless it genuinely fits your repo.

> 💡 **Key Concept — Casting system**  
> Squad names are persistent identities, not cosmetic nicknames. The universe can be thematic, but role ownership still comes from the roster and routing rules. `Scribe`, `Ralph`, and `@copilot` are special cases with fixed behavior.

> 💡 **Key Concept — Scribe is the silent logger**  
> Scribe does not compete for feature work. Scribe maintains the shared memory: session logs, merged decisions, and cross-agent context so the team remembers what it learned.

---

## Phase 2: First Work Batch — Ralph Clears the Backlog

**Timing:** 15–20 minutes

### Demo Talking Points

- In this repo, the first real backlog was **10 GitHub issues**: **#2–#11**.
- All were labeled **`squad:copilot`**, so GitHub Copilot picked them up asynchronously and opened draft PRs.
- The user said **"Ralph, go"** to activate the work monitor.
- Ralph's job is a loop: **scan → act → scan → act** until the board is clear.
- Reviews fanned out in parallel:
  - **Niobe** reviewed testing PRs
  - **Morpheus** reviewed architecture / design-sensitive PRs
  - **Tank** reviewed infra / backend PRs
- This session also demonstrated the **reviewer rejection protocol** and a real **merge conflict resolution**.

### Steps

1. Replay the historical backlog in `selflearning`.
2. Trigger Ralph's work loop.
3. Verify merged PR history.
4. Show the rejected PR and the follow-up fix.
5. Re-run the repo test suite to show the board ended in a healthy state.

### Commands

#### Terminal — replay the board

```bash
gh issue list --state all --limit 20
gh pr list --state all --limit 20
./.venv/bin/python -m pytest tests/ -q
```

#### Prompt to Squad

```text
Ralph, go
```

#### Terminal — inspect the specific historical PRs

```bash
gh pr view 16 --json number,title,reviewDecision,isDraft,author
gh pr view 18 --json number,title,reviewDecision,isDraft,author
gh pr view 21 --json number,title,reviewDecision,isDraft,author
gh pr view 17 --json number,title,reviewDecision,isDraft,author
```

### Expected Output

The historical replay should show:

- Issues **#2–#11** closed
- PRs **#12–#21** merged
- A batch of `@copilot`-authored work on `copilot/*` branches
- A healthy test suite at the end (`494 passed, 1 skipped` in the current repo state)

Narratively, highlight these outcomes:

- Ralph initially found the backlog wave — 10 issues and active `@copilot` PR work already in motion — and kept working until it was empty
- `@copilot` worked multiple issues in parallel (about four at a time)
- That first delivery wave added **~1,500+ tests / coverage points** across the services in this project history
- **PR #16** was rejected because `DefaultAzureCredential` does not work against local emulators
- Per the lockout rule, the original author did **not** do the fix; **Tank** implemented the conditional emulator key-based auth himself
- **PR #18** hit merge conflicts after earlier PRs merged; Tank resolved the conflict by bringing in `main`, fixing the overlap, and finishing the merge
- All 10 issues closed and all 10 PRs merged in one session

> 📝 **ADAPT**  
> On your own repo, use `gh issue list --state open` and `gh pr list --state open` instead of historical replay. Your issue numbers and PR numbers will differ, but the orchestration pattern should be the same.

> 💡 **Key Concept — Ralph work monitor**  
> Ralph is not a one-shot command. When active, he keeps cycling until the board is empty or the user explicitly says `Ralph, idle`.

> 💡 **Key Concept — Reviewer lockout**  
> If a reviewer rejects work, the original author is locked out from being the reviser. A different agent must fix it. This prevents "author reviews own homework" loops and forces real handoffs.

---

## Phase 3: Hiring a New Team Member

**Timing:** 8–10 minutes

### Demo Talking Points

- The team hit a new kind of work: Docker / ACR expertise.
- No one on the roster owned that lane yet.
- Instead of overloading an existing role, Squad **expanded the team** and hired a new specialist.
- The new member was **Dozer** — DevOps / Infra Engineer.
- Hiring updated the roster, routing rules, casting registry, and the new member's seeded history.

### Steps

1. Ask Squad to fill the missing capability.
2. Inspect the resulting roster and routing changes.
3. Show that the new member is now available for future work immediately.

### Commands

#### Prompt to Squad

```text
If you don't have an ACR/Docker expert, hire one.
```

#### Terminal

```bash
grep -n "Dozer\|Docker\|CI/CD\|Infrastructure automation" .squad/team.md .squad/routing.md
ls .squad/agents/dozer
```

### Expected Output

You should be able to point to:

- A new roster entry for **⚙️ Dozer — DevOps / Infra Engineer**
- A new charter and history at `.squad/agents/dozer/`
- New routing ownership for Docker, CI/CD, and infrastructure automation
- Updated casting state so the hire is now part of the persistent team identity

> 📝 **ADAPT**  
> Hire for the missing specialty in your project: mobile, security, frontend design systems, data infra, SRE, etc. The important part is that the team grows because the work changed, not because an existing agent was convenient.

> 💡 **Key Concept — Dynamic hiring**  
> Squad can expand mid-project. New hires are first-class citizens: they get a charter, personal history, routing rules, and a stable identity going forward.

---

## Phase 4: Pivoting to `@copilot` Integration

**Timing:** 10–15 minutes

### Demo Talking Points

- The user changed the delivery model: **all development work should become GitHub issues and be assigned to `@copilot`.**
- Squad pivoted immediately:
  - kept Dozer on the roster
  - reverted direct implementation work
  - added `@copilot` as a team member with a capability profile
  - routed development via issue labels instead of direct agent spawning
- This created a clean split:
  - Squad members handle architecture, triage, review, and corrections
  - `@copilot` handles well-scoped coding issues asynchronously through GitHub

### Steps

1. Give the routing directive.
2. Verify `@copilot` exists in the roster with auto-assign enabled.
3. Replay the three ACR-related issues created in this repo.
4. Replay the draft PRs created by `@copilot`.

### Commands

#### Prompt to Squad

```text
I would like that all the development job to be done is created as an issue and you assign it to copilot.
```

#### Terminal — verify roster and auto-assign

```bash
grep -n "@copilot\|copilot-auto-assign" .squad/team.md
gh issue list --state all --label "squad:copilot" --limit 20
gh pr list --state all --author app/copilot-swe-agent --limit 20
```

#### Optional manual seeding commands for attendees on their own repo

```bash
gh issue create \
  --title "Create ACR remote build script (scripts/acr-build.sh)" \
  --label squad \
  --label squad:copilot \
  --label go:needs-research

gh issue create \
  --title "Create GitHub Actions workflow for ACR remote builds" \
  --label squad \
  --label squad:copilot \
  --label go:needs-research

gh issue create \
  --title "Document remote ACR build workflow for developers" \
  --label squad \
  --label squad:copilot \
  --label go:needs-research
```

### Expected Output

In `selflearning`, replay the historical artifacts:

- Issues **#22, #24, #26**
- Draft PRs **#23, #25, #27**
- `@copilot` listed in `.squad/team.md`
- `<!-- copilot-auto-assign: true -->` present in the roster file

Use the talking point that the board now supports two lanes:

1. **Synchronous Squad lane** — humans talk to Squad; Squad routes, reviews, and decides
2. **Asynchronous `@copilot` lane** — GitHub issues labeled `squad:copilot` are picked up autonomously

> 📝 **ADAPT**  
> Tune the capability profile to your repo's risk tolerance. For example, you may allow `@copilot` on CI changes and tests, but keep architecture, security, and breaking API changes with named squad members.

> 💡 **Key Concept — `@copilot` integration**  
> `@copilot` is a team member, but it is **not spawnable like the other agents**. It works through GitHub issue assignment and draft PRs. That makes it ideal for a continuous stream of bounded implementation work.

---

## Phase 5: Real-World Problem → Issue Creation

**Timing:** 10–15 minutes

### Demo Talking Points

- This phase shows one of the most valuable Squad patterns: turning raw operational failure into structured engineering work.
- In this repo, the user pasted a failing `azd provision` run where **all 8 Container Apps failed**.
- Squad analyzed the error and found **two root causes**:
  1. Missing **AcrPull** RBAC in `identity.bicep`
  2. A first-deploy **chicken-and-egg** problem: the apps referenced ACR images that did not exist yet
- Squad then created **issue #28** with acceptance criteria and routed it to `@copilot`, which opened **PR #29**.

### Steps

1. Reproduce or inspect the failing command.
2. Paste the error into Squad.
3. Ask Squad to convert the analysis into a routed issue.
4. Verify the resulting issue and PR.

### Commands

#### Terminal — reproduce or inspect

```bash
azd provision
```

#### Prompt to Squad

```text
Here is the azd provision failure output. Analyze it, explain the root cause, create a GitHub issue with acceptance criteria, and route it correctly.
```

Paste the error output after that prompt.

#### Terminal — verify the created artifacts

```bash
gh issue view 28
gh pr view 29 --json number,title,reviewDecision,isDraft,author
```

### Expected Output

For `selflearning`, the replay should show:

- **Issue #28** titled `Fix azd provision failure: missing AcrPull RBAC and chicken-and-egg image pull`
- Acceptance criteria covering:
  - AcrPull role assignment in `identity.bicep`
  - passing the container registry name from `main.bicep`
  - first-deploy handling in `container-app.bicep`
- **PR #29** created by `app/copilot-swe-agent`

Use the talking point that Squad did not merely summarize the error; it transformed it into **actionable backlog with ownership and acceptance criteria**.

> 📝 **ADAPT**  
> Any real failure can enter the system this way: failing CI logs, `pytest` output, `terraform plan` errors, deployment failures, flaky tests, or production traces. The key is to preserve the raw evidence and turn it into a scoped issue.

> 💡 **Key Concept — Ops-to-backlog loop**  
> A real engineering team does not separate delivery from operations. Squad can ingest failures directly, analyze them, and route them into the same issue/PR system the team already uses.

---

## Phase 6: Squad Reviews `@copilot`'s Work

**Timing:** 10–15 minutes

### Demo Talking Points

- After `@copilot` opened PRs, the user said **"Ralph, go"** again.
- Ralph scanned the board and found **four draft PRs** with real content.
- Review then fanned out in parallel:
  - **Dozer** reviewed **PR #29** and requested changes
  - **Dozer** reviewed **PR #23** and **PR #25** and requested changes
  - A lightweight documentation reviewer commented on **PR #27**
- Scribe recorded and consolidated team knowledge into the decision ledger.
- The board ended in a healthy waiting state: feedback is clear, ownership is clear, and the team is waiting for `@copilot` to respond.

### Steps

1. Trigger Ralph again.
2. Inspect the four open PRs.
3. Verify which ones have changes requested.
4. Show the review themes.
5. Point out the shared memory effect in `.squad/decisions.md`.

### Commands

#### Prompt to Squad

```text
Ralph, go
```

#### Terminal — inspect the open draft PRs

```bash
gh pr list --state open --draft --limit 20
gh pr view 23 --json number,title,reviewDecision,isDraft,author
gh pr view 25 --json number,title,reviewDecision,isDraft,author
gh pr view 27 --json number,title,reviewDecision,isDraft,author
gh pr view 29 --json number,title,reviewDecision,isDraft,author
```

#### Terminal — inspect the review themes from the repo history

```bash
grep -n "AcrPull\|placeholder\|Dockerfile path\|latest\|null-SHA" .squad/agents/dozer/history.md
ls .squad/decisions/inbox
```

### Expected Output

Current historical state in `selflearning`:

- **PR #23** — `CHANGES_REQUESTED`
- **PR #25** — `CHANGES_REQUESTED`
- **PR #27** — comments only / no blocking review decision
- **PR #29** — `CHANGES_REQUESTED`

Use these review talking points:

- **PR #23**: remote ACR build script used the wrong Dockerfile path for the selected build context
- **PR #25**: workflow should not move `:latest` on PR builds; null-SHA handling also needed fixing
- **PR #27**: documentation quality was good, but it referenced work that had not merged yet
- **PR #29**: AcrPull fix was correct, but the placeholder image strategy would have converged the system to the wrong steady state and mismatched ports

Also note:

- Scribe logged the round and merged **6 team decisions** into `.squad/decisions.md`
- `.squad/decisions/inbox/` is empty now because Scribe already consolidated the drop-box entries

> 📝 **ADAPT**  
> Choose reviewers by domain, not by convenience. Let the infra person review infra, the tester review tests, and the lead review architecture-sensitive changes. That division is where the signal comes from.

> 💡 **Key Concept — Parallel review fan-out**  
> Squad does not review one PR at a time unless it has to. When multiple PRs are ready, review them in parallel and collapse the waiting time.

> 💡 **Key Concept — Drop-box pattern**  
> Agents do not all edit the canonical shared files directly. They write individual decision notes to an inbox, and Scribe merges them into the shared ledger. That keeps parallel work conflict-free.

---

## Cheat Sheet

### Core prompts

```text
Ralph, go
Ralph, status
Ralph, idle
If you don't have a <specialty> expert, hire one.
Create a GitHub issue for this problem and route it correctly.
Review PR #<n>.
```

### Core `gh` commands

```bash
gh issue list --state open --limit 20
gh issue list --state all --limit 20
gh issue list --state all --label "squad:copilot" --limit 20
gh issue view <issue-number>

gh pr list --state open --limit 20
gh pr list --state open --draft --limit 20
gh pr list --state all --author app/copilot-swe-agent --limit 20
gh pr view <pr-number> --json number,title,reviewDecision,isDraft,author
```

### Useful repo inspection commands

```bash
grep -n "@copilot\|copilot-auto-assign" .squad/team.md
grep -n "Dozer\|Docker\|CI/CD\|Infrastructure automation" .squad/team.md .squad/routing.md
ls .squad/agents
ls .squad/decisions/inbox
./.venv/bin/python -m pytest tests/ -q
(cd src/ui && npm run build)
```

---

## Troubleshooting

### `gh` commands fail or show no data

- Run `gh auth status`
- Confirm you are in the correct repo: `gh repo view --json nameWithOwner,url`
- For the historical `selflearning` replay, use `--state all`, not `--state open`

### Squad does not assign `@copilot`

- Confirm `@copilot` is in `.squad/team.md`
- Confirm this line exists exactly:

```md
<!-- copilot-auto-assign: true -->
```

- Confirm the repo has the label `squad:copilot`
- Confirm GitHub Actions for issue assignment are enabled

### Ralph appears idle even though work exists

- Use `Ralph, status` for a one-cycle diagnostic
- Check whether issues are labeled only `squad` and still need triage
- Check whether PRs are draft-only and waiting on review or feedback

### Local emulators fail with Azure identity

- `DefaultAzureCredential` is the right production default, but local emulators like Cosmos DB Emulator and Azurite typically require well-known keys instead
- Use environment-aware auth logic in local development paths
- This exact mismatch was the blocker on historical **PR #16**

### Remote ACR builds fail unexpectedly

Common causes from this repo's review cycle:

- Dockerfile path must be **relative to the selected build context**
- PR builds should not move `:latest`
- First-push / null-SHA handling must account for the all-zero SHA case

### `azd provision` fails on first Container App deploy

Check for both conditions:

1. The Container Apps' managed identity has **AcrPull** on the registry
2. First deploy can handle the case where ACR images do not exist yet

Also ensure any placeholder image strategy is:

- opt-in or first-deploy-only
- aligned with the correct app port
- not the steady-state desired image after real deploys

---

## Suggested Presenter Closing

Use this summary to close the session:

> We started with no team, cast a persistent squad, cleared a real backlog, hired a new specialist when the work changed, pivoted implementation to GitHub issues assigned to `@copilot`, converted a real deployment failure into an actionable issue, and then reviewed autonomous work in parallel. The important takeaway is not the Matrix theme — it is the operating model: clear roles, real handoffs, shared memory, and a backlog that keeps moving.

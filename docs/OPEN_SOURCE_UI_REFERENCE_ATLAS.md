# Open Source UI Reference Atlas

_Audit date: 2026-06-14_

This atlas records the open-source UI references inspected before building the AgentOps MIS Pixel Operating Map. The intent is not to select one project as the product base. AgentOps MIS remains the authority system for agents, tasks, runs, tool calls, approvals, memory, evaluations, audit, runtime connectors, external bases and templates.

## Executive decision

- **Do not fork a whole product for v1.3.** Use external repositories as reference material only.
- **Build original React/Vite UI inside `ui/start-building-app`.** The first Pixel Operating Map should be a native AgentOps MIS page, not an iframe and not a cloned game engine.
- **Do not copy third-party art assets into this repository.** Even permissive-looking pixel packs must be verified separately before any commercial use.
- **Keep Star-Office-UI as a legacy/reference visualizer.** Its code is MIT, but its art assets are explicitly non-commercial.
- **Prefer module-by-module pattern borrowing.** Plane is a better Task Hall reference than any pixel office. Langfuse is a better Evaluation Room reference than any workflow builder. Activepieces is a better Tool Workshop reference than a knowledge base.

## Evidence strength scale

| Rating | Meaning |
|---|---|
| Strong | README plus license and at least one package/config/code/entrypoint or architecture file inspected. |
| Medium | README, docs and license inspected, but not enough code files to judge implementation details. |
| Weak | Repository name, secondary docs or public description only. Do not base implementation decisions solely on this. |

This document is an engineering/product audit, not legal advice. Before commercial reuse of any external code or asset, perform a final license review.

---

# Module reference atlas

## 1. Pixel Operating Map

| Candidate | Repository URL | License | Tech stack | Active? | Useful UI patterns | Useful code patterns | Asset reuse | Commercial asset risk | Recommendation | How it maps to AgentOps MIS | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Star-Office-UI | https://github.com/ringhyacinth/Star-Office-UI | Code MIT; art non-commercial | Flask, vanilla frontend/static assets, Pillow | Appears active; README modified in 2026 | Pixel office status board, simple state-to-area mapping, multi-agent status, legacy visualizer concept | `/set_state`, `/agents`, `/agent-push`, `state.json`, simple local server | **No for product**; demo/reference only | **High**: art assets explicitly non-commercial; LimeZu attribution required | Reference only; keep optional legacy link | Proves a pixel office can visualize agent state, but AgentOps MIS must own authority, routing and data model | Strong |
| openclaw-virtual-office | https://github.com/thx0701/openclaw-virtual-office | MIT; README credits commercial-friendly upstream assets, still verify | Node.js, static HTML/CSS/JS, custom WebSocket, OpenClaw CLI polling | Appears active; README modified in 2026 | Group chat = virtual worker; busy/online/idle/offline visual states; desks and rest zones | Polls `openclaw sessions list --json`; broadcasts via WebSocket; config-driven agents | Do not copy; use concept only | Medium: upstream art licenses need separate verification | Reference only | Strong reference for OpenClaw session-to-presence mapping, not for AgentOps MIS architecture | Strong |
| pixel-agents / pixel-agents-hq | https://github.com/pixel-agents-hq/pixel-agents and mirrored/forked at https://github.com/arpdale/virtual-office | MIT; assets claim open-source, characters based on MetroCity; verify | VS Code extension, React, TypeScript, Vite, Canvas 2D | Active project family | Agent as character; task panel; sub-agent visualization; layout editor; speech bubbles | JSONL transcript watcher, Canvas loop, BFS pathfinding, state machine | Not for v1.3 | Medium: character and furniture asset provenance must be checked | Reference only | Best reference for future richer map behavior; too game-like for v1.3 | Strong |
| pixel-agents-standalone | https://github.com/rolandal/pixel-agents-standalone | MIT; Donarg full tileset purchased separately | Express, WebSocket, React, TypeScript, Vite, Canvas 2D | Appears active; README modified in 2026 | Standalone browser pixel office, layout editor, session activity visualization | Watches Claude JSONL, parses tool/subagent/permission/idle, renders Canvas | No | High if Donarg paid tileset is used without purchase/license | Reference only | Useful movement and status logic reference; do not import engine | Strong |
| hootbu/pixel-agents | https://github.com/hootbu/pixel-agents | MIT; paid Donarg tileset not included | VS Code extension, React 19, TypeScript, Vite, Canvas 2D | Appears active; README modified in 2026 | Task panel, token usage panel, mood bubbles, achievements, pets, costumes, seat assignment | Adaptive status detection, sub-agent spawning, layout persistence | No | High for full furniture catalog; paid asset workflow | Reference only | Useful for Run Stream and agent activity visualization, but not for MIS authority | Medium |
| Claude-Office | https://github.com/W17ant/Claude-Office | MIT for code, but content/IP issues | React, TypeScript, Vite, Express, WebSocket, SQLite, Electron optional | Appears active; README modified in 2026 | Isometric office, chat panel, event lifecycle, day/night | Claude hooks to local WebSocket server; event endpoint token | **No** | **Very high**: TV show tribute mode, named characters, props and generated art | Avoid assets/content; reference lifecycle only | Useful warning example: entertaining UI can drift away from MIS control-plane seriousness | Medium |
| agent-office | https://github.com/Pixel-Process-UG/agent-office | MIT | Vite/Node-oriented app, optional SQLite/Postgres, integrations | Early development; explicitly unstable | Live presence, task assignment, speech bubbles, decisions/voting, accessibility/mobile | Setup wizard, integrations, Telegram sync | No | Medium/high: paid Donarg office map optional | Reference only | Good for task assignment and live presence, but too unstable to base product on | Medium |
| agent-virtual-office | https://github.com/k1dav-c/agent-virtual-office | MIT | React 19, Vite, Tailwind, FastAPI, MCP, Hasura, Postgres, RabbitMQ, Docker | Appears active; README modified in 2026 | Role badges, status colors, session grouping, deep links, append-only activity log | MCP `report_status`, GraphQL subscriptions, hashed API keys, role inference | No | Low for CSS/SVG ideas, but still do not copy | Reference only | Strong state-reporting and auditability reference; too heavy for v1.3 | Strong |
| pixel-agents-desktop | https://github.com/Dsantiagomj/pixel-agents-desktop | MIT | Electron, React, Vite, TypeScript, Canvas 2D | Appears active; README modified in 2026 | Desktop tray, automatic session discovery, dormancy/despawn | JSONL watcher, transcript parser, IPC bridge, preserved game engine | No | Medium: inherited assets from pixel-agents family | Reference only | Useful future desktop/ambient monitor idea; not relevant to web v1.3 | Strong |

**Pixel Operating Map conclusion:** build an original low-fidelity operating floor in AgentOps MIS. Borrow the idea of state-to-zone mapping, status bubbles, live presence and click-to-inspect. Avoid copying pixel assets, branded characters, layout editors, paid tilesets and JSONL-transcript authority models.

---

## 2. Task Hall

| Candidate | Repository URL | License | Tech stack | Active? | Useful UI patterns | Useful code patterns | Asset reuse | Risk | Recommendation | AgentOps MIS mapping | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Plane | https://github.com/makeplane/plane | AGPL-3.0 | React Router, Django, Node.js | Active | Work item cards, cycles, modules, views, pages, analytics | Issue filtering, project structure, saved views | No | AGPL copy/fork risk | Reference only | Best Task Hall reference for backlog/running/waiting/completed/failed states | Strong |
| Taiga | https://github.com/taigaio/taiga | AGPL-3.0-or-later | Python/Django, Angular-era frontend | Maintained but older UI style | Agile board, swimlanes, issue detail | Classic project workflow model | No | AGPL and dated frontend | Reference only | Secondary reference for simple task board patterns | Weak/medium |
| Huly Platform | https://github.com/hcengineering/platform | EPL-2.0 | Large TypeScript/Rush platform; business apps including project management | Active; heavy platform | Integrated workspace, project management, CRM/chat adjacency | Typed API client, self-host patterns | No | Large architecture and dependency load | Reference only | Good long-term enterprise workspace reference; too broad for MVP | Medium |

**Task Hall conclusion:** Plane is the best UI reference. Reimplement issue cards, status lanes, risk tags, assignee chips and task detail affordances using AgentOps MIS task data.

---

## 3. Runtime Lab

| Candidate | Repository URL | License | Tech stack | Useful UI patterns | Recommendation | AgentOps MIS mapping |
|---|---|---|---|---|---|
| Windmill | https://github.com/windmill-labs/windmill | AGPL/source + commercial restrictions depending distribution | Rust backend/workers, Svelte frontend, Postgres, sandboxed runtimes | Job cards, execution logs, resource/secrets model, worker groups, schedules | Reference only | Runtime connector health, script/job execution status, retry and sandbox status |
| Grafana | https://github.com/grafana/grafana | AGPL-3.0-only with exceptions | Go, React/TypeScript frontend | Dense dashboards, dynamic filters, mixed data sources, alert panels | Reference only | Runtime health, latency, error, cost and connector status panels |
| Camunda | https://github.com/camunda/camunda | Mixed Camunda License + Apache exceptions | Java/Zeebe, Tasklist, Operate, Identity, Optimize | Operate-style process monitor, incident status, human task list | Reference only | Run/process status and runtime incident handling |
| Flowable | https://github.com/flowable/flowable-engine | Apache-2.0 | Java BPMN/CMMN/DMN engine | Human/system activity orchestration concepts | Reference only | Lightweight inspiration for run steps and human tasks |

**Runtime Lab conclusion:** use Windmill/Grafana/Camunda as visual references only. Runtime Lab should remain a connector control panel for OpenClaw, Hermes, Agnesfallback and OpenAI-compatible runtimes; it should not become a workflow runtime itself.

---

## 4. Tool Workshop

| Candidate | Repository URL | License | Tech stack | Useful UI patterns | Recommendation | AgentOps MIS mapping |
|---|---|---|---|---|---|
| Activepieces | https://github.com/activepieces/activepieces | MIT Community Edition; enterprise commercial license | TypeScript monorepo, pieces framework | Connector/action cards, piece catalog, no-code builder, human-in-loop pieces, versioned flows | Best reference; no copy | Tool catalog, connector/action capability cards, dry-run/live mode, permission indicators |
| n8n | https://github.com/n8n-io/n8n | Sustainable Use License + Enterprise License | Node/TypeScript workflow automation | Node canvas, 400+ integrations, templates, execution view, retries | Reference only | Tool execution graph, connector marketplace and run history patterns |
| Windmill | https://github.com/windmill-labs/windmill | AGPL/source + commercial restrictions | Rust/Svelte/Postgres | Logs, worker queues, script-generated UI, resources/secrets | Reference only | Tool call detail cards, logs and runtime grouping |

**Tool Workshop conclusion:** Activepieces is the best open-source UI reference for connector/action cards. Do not copy its pieces or marketplace assets; reimplement a compact AgentOps MIS tool-call workbench.

---

## 5. Approval Gate

| Candidate | Repository URL | License | Useful UI patterns | Recommendation | AgentOps MIS mapping |
|---|---|---|---|---|---|
| Camunda Tasklist | https://github.com/camunda/camunda | Mixed | Human task list, assignment, process context, incident state | Reference only | Approval queue, risk reason, approve/reject/return states |
| Flowable | https://github.com/flowable/flowable-engine | Apache-2.0 | Human/system activity orchestration | Reference only | Quality gate and approval state machine concepts |
| Activepieces | https://github.com/activepieces/activepieces | MIT CE + commercial EE | Human-in-the-loop steps, delay/approval actions | Reference only | Human approval action cards |
| GitHub branch protection/reviews | https://github.com/features/code-review | Product pattern, not open-source UI | Required reviews, status checks, blocking gates | Pattern only | Quality gate and approval evidence UX |

**Approval Gate conclusion:** borrow risk-based queue design and pass/fail/escalate semantics. AgentOps MIS approvals remain the only authority record.

---

## 6. Evaluation Room

| Candidate | Repository URL | License | Tech stack | Useful UI patterns | Recommendation | AgentOps MIS mapping |
|---|---|---|---|---|---|
| Langfuse | https://github.com/langfuse/langfuse | MIT | Next.js/TypeScript, ClickHouse, SDKs | Trace/session detail, score cards, evaluator results, datasets, prompt versions, filters | Best reference | Evaluation Room, Run Stream, quality gate result UI |
| Helicone | https://github.com/Helicone/helicone | Apache-2.0 | Next.js, Workers, Express/Tsoa, Supabase, ClickHouse, Minio | Cost/latency/error dashboards, provider routing, session traces, gateway logs | Reference only | Cost/latency/error views and LLM gateway-style summaries |
| Grafana | https://github.com/grafana/grafana | AGPL-3.0-only | Go + React/TS | Dashboards, time filters, alert rules, explore logs | Reference only | Control Tower panels and runtime health |

**Evaluation Room conclusion:** Langfuse is the strongest UI reference for trace/evaluation flows. Reimplement simple score cards, evaluator result panels and failure reason analysis in AgentOps MIS.

---

## 7. Memory Archive

| Candidate | Repository URL | License | Tech stack | Useful UI patterns | Recommendation | AgentOps MIS mapping |
|---|---|---|---|---|---|
| Docmost | https://github.com/docmost/docmost | AGPL core + EE directories | Node/TypeScript-style collaborative wiki | Spaces, permissions, comments, page history, search, attachments | Reference only | Memory spaces, SOP/decision/failure-case pages, review queue |
| Outline | https://github.com/outline/outline | BSL 1.1 | React, Node.js, TypeScript | Fast knowledge base, document tree, collaborative docs, search | Reference only | Knowledge tree and page detail UX |
| AppFlowy | https://github.com/AppFlowy-IO/AppFlowy | AGPL-3.0 | Flutter, Rust | Notion-style docs, database/grid, Kanban, templates | Visual reference only | Memory candidate review and template-like pages |
| AFFiNE | https://github.com/toeverything/AFFiNE | MIT CE; future EE planned | TypeScript, React, local-first blocksuite ecosystem | Docs + whiteboard + tables, backlinks/canvas, local-first | Reference only | Future relation/backlink UI and memory graph view |

**Memory Archive conclusion:** borrow tree, spaces, page cards and backlink/relation patterns. The memory authority remains the AgentOps MIS memory candidate and organizational memory model.

---

## 8. Audit Vault

| Reference | Source | Useful UI patterns | Recommendation | AgentOps MIS mapping |
|---|---|---|---|---|
| GitHub audit log | GitHub Enterprise product pattern | Actor/action/entity filters, timestamped events, export | Pattern only | Audit event table and filters |
| Stripe logs | Stripe dashboard pattern | Request/event detail, status, replay and metadata density | Pattern only | Tool call and connector event evidence |
| Cloudflare dashboard | Cloudflare dashboard pattern | Security/admin density, policy and status tags | Pattern only | Enterprise settings and connector risk indicators |
| Grafana admin | https://github.com/grafana/grafana | Dense admin navigation, alert/event panels | Reference only | Control Tower and Audit Vault operational density |

**Audit Vault conclusion:** do not invent a cute pixel audit UI. Use sober enterprise log patterns: actor, action, entity, risk, evidence, hash/proof, timestamp and filters.

---

## 9. External Base Dock

| Candidate | Repository URL | License | Useful UI patterns | Recommendation | AgentOps MIS mapping |
|---|---|---|---|---|---|
| Activepieces pieces | https://github.com/activepieces/activepieces | MIT CE + commercial EE | Connector marketplace, action cards, auth setup, capability descriptions | Best reference | External base connector cards and dry-run/live mode |
| n8n integrations | https://github.com/n8n-io/n8n | Sustainable Use License + EE | Integration catalog, node credentials, templates | Reference only | Connector marketplace and sync status |
| Plane integrations | https://github.com/makeplane/plane | AGPL-3.0 | App integrations inside project management | Reference only | Plane base binding placeholder |
| Docmost/Outline integrations | https://github.com/docmost/docmost and https://github.com/outline/outline | AGPL/BSL | Knowledge app embed/search/auth patterns | Reference only | Docmost/Outline base dock patterns |
| Langfuse/Helicone settings | https://github.com/langfuse/langfuse and https://github.com/Helicone/helicone | MIT/Apache-2.0 | API key, project, environment, endpoint setup | Reference only | W&B/Langfuse/Helicone evaluation base configuration |

**External Base Dock conclusion:** use marketplace cards with capability matrix, connection status, sync direction, last sync, error, permission and dry-run/live mode.

---

## 10. Control Tower

| Candidate | Repository URL | License | Useful UI patterns | Recommendation | AgentOps MIS mapping |
|---|---|---|---|---|---|
| Grafana | https://github.com/grafana/grafana | AGPL-3.0-only | KPI panels, time filters, alerts, explore logs | Reference only | Control Tower health, cost, latency, risk and incidents |
| Langfuse | https://github.com/langfuse/langfuse | MIT | LLM usage, cost, score and trace summaries | Reference only | AI-specific score/cost dashboards |
| Plane Analytics | https://github.com/makeplane/plane | AGPL-3.0 | Work item throughput and project analytics | Reference only | Task throughput and blocked/risk status |

**Control Tower conclusion:** use dense MIS dashboards, not game mechanics. The Pixel Operating Map should link into Control Tower, not replace it.

---

# What to borrow vs. avoid

## Borrow

- State-to-zone mapping from Star-Office-UI and OpenClaw virtual office projects.
- Live presence, status bubbles and movement metaphors from pixel office projects.
- Task board and issue detail patterns from Plane.
- Connector/action marketplace cards from Activepieces and n8n.
- Human task and process incident patterns from Camunda/Flowable.
- Trace table, score cards and evaluator detail from Langfuse.
- Cost/latency/provider views from Helicone.
- Spaces, document trees, page history and backlink patterns from Docmost/Outline/AFFiNE.
- Enterprise audit density from GitHub/Stripe/Cloudflare/Grafana patterns.

## Reimplement

- All React components inside `ui/start-building-app`.
- Pixel map geometry, CSS, sprites, labels and motion effects.
- Zone model and routing.
- Agent/task/run/approval/memory/evaluation/audit mapping.
- Connector marketplace cards and runtime status cards.
- Evidence, risk, approval and audit views.

## Avoid

- Copying art assets from Star-Office-UI, paid Donarg tilesets, MetroCity-derived sprites or any branded pop-culture content.
- Making Star-Office-UI or any pixel project the product base.
- Introducing PixiJS, Phaser or a full Canvas game engine in v1.3.
- Treating Claude Code JSONL transcript watchers as AgentOps MIS authority.
- Importing AGPL/BSL/fair-code UI code into the React/Vite app.
- Committing `.env`, local DBs, tokens, node_modules, generated caches or third-party asset dumps.

# Final atlas recommendation

For v1.3, implement a native, low-fidelity, original React/CSS Pixel Operating Map. Use references for product judgment only. The most important product line is:

> Pixel Office is a visual navigation and live operations layer. It is not the authority ledger, not a runtime, not an agent builder, and not a cloned virtual office product.

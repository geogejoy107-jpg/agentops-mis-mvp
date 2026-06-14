# Star-Office-UI Demo Integration

## Positioning

Star-Office-UI is an optional **Pixel Office Mode** and **Demo Recording Dashboard** for AgentOps MIS. It can visualize local AgentOps MIS state as a cozy office floor during classroom demos, but it does not replace the AgentOps MIS core ledger.

AgentOps MIS remains the authority for:

- agents
- tasks
- runs
- tool calls
- approvals
- memory review
- evaluations
- audit logs
- runtime connector events

Star-Office-UI is only a visual surface.

## License Boundary

The current plan allows Star-Office-UI art assets only for local, non-commercial classroom demo use.

Boundary:

- Demo/local course recording: Star-Office-UI visual assets may be used with attribution.
- Public commercial product, website, marketing, SaaS, paid deployment, App Store, hosted beta, or customer-facing release: replace all Star-Office-UI art assets with original AgentOps MIS assets.
- Code and visual assets must be treated separately. Even if code is MIT, the art assets are not automatically commercial-ready.

Attribution text for demo materials:

```text
Pixel Office demo visual mode is inspired by and temporarily uses assets from Star-Office-UI for non-commercial classroom demonstration only.

Star-Office-UI:
https://github.com/ringhyacinth/Star-Office-UI

Code/license follows the original repository. Art assets are used only for learning/demo purposes and will be replaced by original AgentOps MIS assets before any public commercial release.
```

Video narration:

```text
这个像素办公模式的 demo 暂时基于 Star-Office-UI 的非商业演示资产，后续产品化会替换为我们自己的原创 AgentOps MIS 像素资产。
```

## Local Deployment

Run AgentOps MIS:

```bash
python3 server.py
```

Run Star-Office-UI separately according to its own README. The default local endpoint assumed by the adapter is:

```text
http://127.0.0.1:19000
```

The adapter does not start Star-Office-UI and does not copy Star-Office-UI assets into this repository.

## AgentOps MIS To Star-Office State Mapping

| AgentOps MIS signal | Internal MIS state | Star-Office-compatible state | Message behavior |
|---|---|---|---|
| No active run | `idle` | `idle` | Show local ledger idle summary |
| Running run | `executing` | `executing` | Show run id, agent id, task title |
| Research task running | `researching` | `researching` | Show research task title |
| Writing/report task running | `writing` | `writing` | Show writing/report title |
| Approval required | `waiting_approval` | `executing` | Message includes `waiting approval` |
| Memory candidate activity | `syncing` | `syncing` | Show memory review count |
| Latest run failed/error | `error` | `error` | Show redacted error type |
| Audit event recorded | `auditing` | `syncing` | Message includes `audit event recorded` |

The adapter keeps both `mis_state` and `state` in the payload so richer Star-Office deployments can use the MIS-specific state while compatible deployments can use the safer `state` value.

## Adapter

Dry-run:

```bash
python3 scripts/push_star_office_state.py
```

Send to local Star-Office-UI:

```bash
python3 scripts/push_star_office_state.py --send
```

Custom endpoint:

```bash
python3 scripts/push_star_office_state.py --base-url http://127.0.0.1:19000 --endpoint agent-push --send
```

## Privacy Boundary

The adapter sends only:

- ids
- counts
- statuses
- redacted short summaries
- local timestamp
- source name

It does not send:

- credentials
- full prompts
- full transcripts
- raw tool arguments
- private message bodies
- local DB file contents

## Non-Goals

- Do not vendor Star-Office-UI assets into the AgentOps MIS core product.
- Do not make Star-Office-UI required for normal MIS operation.
- Do not expose AgentOps MIS publicly only to support this demo.
- Do not treat Star-Office-UI art as commercial product assets.

# Database routing reference

Use this reference only when deciding where to save a Notion archive entry.

## Routing priority

1. Explicit user destination.
2. Existing project-specific database with matching title/schema.
3. Existing general archive database.
4. Create or reuse `GPT Conversation Archive｜GPT 对话归档库`.

## Common routing rules

| Content type | Preferred destination | Notes |
|---|---|---|
| Course PPT/PDF summary, lecture notes, course concept extraction | `Course PPT｜课程课件库` | Use course unit, material type, keywords, study output, project application when fields exist. |
| Uploaded or linked files, Figma/SVG/PNG/PPT/PDF/video/dataset assets | `Media Assets｜多媒介资产库` | Save file/link metadata and usage context. Do not claim the binary was uploaded to Notion unless actually attached or linked. |
| Project reports, requirements, design docs, SOPs, reflections, case analysis | `Docs｜项目文档库` | Use doc type, module, output format, summary, related course when fields exist. |
| Decisions, tradeoff analyses, architecture choices | `Project Decisions` or archive fallback | If no decisions DB exists, use fallback archive category `Decision Log`. |
| Tasks, roadmap items, implementation steps | `Tasks`, `Roadmap`, or archive fallback | If no task DB exists, use fallback archive category `Task Record`; do not invent deadlines. |
| Research findings, competitive research, technical surveys | `Research Notes` or archive fallback | Use category `Research Brief` if no research DB exists. |
| General reusable answer | archive fallback | Use category `Knowledge Note`. |

## Database creation discipline

Create a new specialized database only when at least one of these is true:

- The user explicitly asks for a new database.
- The content will likely recur and needs structured properties not covered by existing databases.
- The current workspace has no general archive and no matching project database.

When unsure, reuse the default archive database rather than creating a new specialized database.

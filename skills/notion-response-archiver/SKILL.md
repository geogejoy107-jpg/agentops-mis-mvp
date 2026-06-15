---
name: notion-response-archiver
description: formalize chatgpt answers and save them to notion. use when the user explicitly says to save, archive, write, or sync a response to notion, or when a substantial project, research, course, decision, or planning answer should be offered for notion archival. choose the most suitable existing notion database, create a default archive database only when no suitable database exists, and save the original user question plus the polished answer.
---

# Notion Response Archiver

Use this skill to turn a ChatGPT exchange into a polished Notion knowledge entry. The user's preference is: do not force one default content style; infer the best style from the topic. For long formal answers, ask whether to save to Notion. For explicit save/archive requests, save without asking unless the destination or creation action is risky or ambiguous.

## Trigger behavior

1. **Explicit save trigger**: if the user says “保存到 Notion”, “归档”, “写入知识库”, “存起来”, “同步到 Notion”, “放进数据库”, or similar, formalize and save immediately.
2. **Implicit suggestion trigger**: after producing a substantial durable answer, ask one short question such as: “这条回复适合保存到 Notion。要我归档吗？” Do not save until the user agrees.
3. **Manual style trigger**: if the user explicitly asks for a specific style or destination, follow it. Otherwise infer style and database from the content.
4. **No archival trigger**: do not offer Notion archival for casual chat, transient brainstorming, private feelings, or very short answers unless the user asks.

## Required saved content

Save **5B** by default: the polished formal document plus the original user question. Do not save the full raw assistant answer unless the user asks.

Each saved page should contain:

- Title
- Short abstract
- Original user question
- Polished formal answer
- Key points or structured sections
- Action items, decisions, or risks if relevant
- Tags and routing reason
- Source/citation notes when present in the conversation

## Formalization style

Infer the document style from the user’s topic:

- Course or learning content: use “course note” style with concepts, examples, application to project, and review questions.
- Project planning or execution: use “project memo” style with background, decision, plan, risks, deliverables, next actions.
- Research: use “research brief” style with question, findings, evidence, implications, limitations, next research tasks.
- Product/system design: use “design spec” style with problem, scope, architecture, data model, workflow, tradeoffs.
- Decision: use “decision log” style with options, rationale, decision, owner, impact, review date.
- Task request: use “task record” style with objective, steps, owner, status, dependencies, deadline if known.
- General useful answer: use “knowledge note” style with summary, body, takeaways, tags.

Keep the Notion entry formal, scannable, and reusable. Preserve citations and file references already present in the answer; do not invent citations.

## Notion database selection workflow

1. Search Notion for an existing database whose title or schema matches the content.
2. Prefer project-specific databases over generic databases.
3. If working in the user’s MIS project and these databases exist, prefer them:
   - `Course PPT｜课程课件库` for course PPT/PDF learning notes and lesson summaries.
   - `Media Assets｜多媒介资产库` for files, PDFs, PPTs, Figma links, SVG/PNG, videos, datasets, and source assets.
   - `Docs｜项目文档库` for project documents, reports, designs, requirements, case analysis, SOPs, reflections.
4. If no suitable database exists, search for `GPT Conversation Archive｜GPT 对话归档库` or `Conversation Archive`.
5. If no archive database exists, create `GPT Conversation Archive｜GPT 对话归档库` as the default fallback database under the best available project/root page, or as a private workspace database if no root is known.
6. Avoid creating many narrowly named databases. Create a new specialized database only when the user explicitly wants a new category or the content clearly needs recurring structured storage.

See `references/database-routing.md` for detailed routing and fallback schema.

## Creating or updating Notion pages

Before creating a database row, fetch the chosen database/data source schema and use the exact property names. If schema fields differ from the ideal schema, set only reliable properties such as title/status/date/tags and put the rest in the page body.

When creating a page:

1. Choose a concise, searchable title.
2. Set status to a draft/indexed/summarized equivalent if the database has a status property.
3. Add tags based on topic, project, course unit, artifact type, and output type.
4. Add the formalized content as the page body.
5. Return the created page URL and a one-sentence routing explanation.

## Fallback archive database schema

If the default archive database must be created, use this schema when the Notion tool supports database creation:

```sql
CREATE TABLE (
  "Name" TITLE,
  "Category" SELECT('Course Note':blue, 'Project Memo':green, 'Research Brief':purple, 'Design Spec':purple, 'Decision Log':orange, 'Task Record':red, 'Knowledge Note':gray),
  "Status" SELECT('Draft':gray, 'Saved':blue, 'Reviewed':green, 'Archived':gray),
  "Original Question" RICH_TEXT,
  "Summary" RICH_TEXT,
  "Tags" MULTI_SELECT('MIS':blue, 'Course':blue, 'Research':purple, 'Project':green, 'Notion':gray, 'Figma':purple, 'PDF':red, 'PPT':orange, 'AI':purple),
  "Routing Reason" RICH_TEXT,
  "Source Context" RICH_TEXT,
  "Updated" DATE
)
```

If database creation is unavailable, create a normal page named `GPT Conversation Archive｜GPT 对话归档库` and append entries as dated sections.

## Confirmation wording

After saving, respond briefly:

- “已保存到 Notion：<page title>”
- “位置：<database/page>”
- “归档理由：<one sentence>”
- “链接：<Notion URL>”

If you ask before saving, ask only one question and include the inferred destination: “这条回复适合保存到 `Docs｜项目文档库`，要我归档吗？”

# Notion Response Archiver

This directory contains the source files for a ChatGPT Skill that formalizes useful ChatGPT answers and archives them to the most suitable Notion database.

## Contents

```text
notion-response-archiver/
├── SKILL.md
├── agents/
│   └── openai.yaml
└── references/
    └── database-routing.md
```

## Intended behavior

- Explicit user requests such as “保存到 Notion”, “归档”, or “写入知识库” trigger immediate archival.
- Substantial project, research, course, decision, or planning answers should prompt the user before saving.
- The Skill saves the polished formal document plus the original user question by default.
- It chooses an existing project database when appropriate and falls back to `GPT Conversation Archive｜GPT 对话归档库` only when needed.

## Packaging note

The distributable ZIP should be generated from this directory when uploading the Skill to ChatGPT. The repository stores the editable source files rather than only the generated ZIP so future changes can be reviewed and versioned.

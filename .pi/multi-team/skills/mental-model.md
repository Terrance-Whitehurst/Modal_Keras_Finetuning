---
name: mental-model
description: Manage structured YAML expertise files as personal mental models. Use when starting tasks (read for context), completing work (capture learnings), or when your understanding of the system needs updating.
---

# Mental Model

## Instructions

You have personal expertise files — structured YAML documents that represent your mental model of the system you work on. These are YOUR files. You own them.

### When to Read

- **At the start of every task** — read your expertise file(s) for context before doing anything
- **When you need to recall** prior observations, decisions, or patterns
- **When a teammate references something** you've tracked before

### When to Update

- **After completing meaningful work** — capture what you learned
- **When you discover something new** about the system (architecture, patterns, gotchas)
- **When your understanding changes** — update stale entries, don't just append
- **When you observe team dynamics** — note what works, what doesn't, who's strong at what

### How to Structure

Write structured YAML. Don't be rigid about categories — let the structure emerge from your work. But keep it organized enough that you can scan it quickly.

```yaml
# Good: structured, scannable, evolving
architecture:
  api_layer:
    pattern: "REST with WebSocket for real-time"
    key_files:
      - path: apps/server/routes.ts
        note: "All endpoints, ~400 lines"
    decisions:
      - "Chose Express over Fastify for ecosystem maturity"

observations:
  - date: "2026-03-24"
    note: "Engineering team handles scope-heavy requests better when given explicit constraints"

open_questions:
  - "Should we split the auth module? It's growing fast."
```

### What NOT to Store

- Don't copy-paste entire files — reference them by path
- Don't store conversation logs — that's what the session log is for
- Don't store transient data (build output, test results) — just conclusions
- Don't be prescriptive about your own categories — evolve them naturally

### Line Limit Enforcement

Each expertise file has a `max-lines` limit declared in your system prompt. After every write to an expertise file:

1. Check the line count: `wc -l <file>`
2. If over the limit, trim immediately:
   - Remove least critical entries (old observations, resolved questions)
   - Condense verbose sections
   - Merge redundant entries
3. Re-check until within limit

This is not optional. The line limit is hard-enforced by the runtime — if your file exceeds the limit after a write, you'll get a warning that you must resolve before continuing.

### YAML Validation

After every write, validate your YAML is parseable. Malformed YAML is useless:

```bash
python3 -c "import yaml; yaml.safe_load(open('<file>'))"
```

Fix any syntax errors immediately.

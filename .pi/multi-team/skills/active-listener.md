---
name: active-listener
description: Read the conversation log at the start of every task for full context. Ensures you know what's happened, what's been decided, and what's still open before responding.
---

# Active Listener

## Variables

MESSAGE_COUNT: 10

## Instructions

Before doing any work, read the last `MESSAGE_COUNT` entries from your conversation log.

### On Every Task Start

1. Read your conversation log file (path is in your Variables section)
2. Parse the last `MESSAGE_COUNT` lines — each line is a JSON object with `from`, `message`, `type`, and `team`
3. Understand what's happened: what was asked, what's been decided, what's unresolved

### Rules

- **Always read before responding.** No exceptions.
- **Don't repeat work.** If a teammate already covered it, build on it or agree — don't restate.
- **Flag conflicts.** If your analysis contradicts a prior response, say so with reasoning.

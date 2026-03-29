# Agent Coding Hints and Guides

## Anti-Churn: Stay in the Foreground

**Problem:** Claude defaults to spawning sub-agents (Explore, Plan, general-purpose) for tasks that can be done directly. Each sub-agent invocation adds 2–10 minutes of pure overhead before a single line of work is done. Chaining sub-agents (A → B → C) produces 30-minute sessions for what should be 5-minute tasks.

**Rule:** Do not spawn a sub-agent unless the task genuinely requires more context than fits in a single exchange (e.g., a full codebase-wide audit). For all normal coding work, operate in the foreground.

### Foreground tool priority:
| Task | Use this | NOT this |
|------|----------|----------|
| Read a file | `Read` | Agent(Explore) |
| Search for a function/pattern | `Grep` or `Glob` | Agent(Explore) |
| Run tests | `Bash` | Agent(general-purpose) |
| Edit a file | `Edit` | Agent(general-purpose) |
| Write a new file | `Write` | Agent(general-purpose) |

### Sub-agent only when:
- A codebase-wide audit genuinely requires more files than fit in one context pass.
- The task is fully independent and can run in the background without blocking the main line of work.

**Never chain sub-agents.** If Agent A's output is needed to determine what Agent B does, that chain should be inline `Read`/`Grep`/`Edit` calls, not two sequential sub-agent spawns.

---

## DNC Protocol

`DNC` = Do Not Code. When the user says DNC, discussion only — no file edits, no code output, no implementation. Wait for explicit go-ahead before touching any file.

---

## Physics-First Test Philosophy

Tests are legacy artifacts. Solve the correct physics first; then calibrate test assertions to match. Never distort the solver to make a broken test pass.

---

## Token Efficiency

- Read only the line ranges needed, not full files, when the target location is known.
- Implement fixes sequentially (not speculatively in parallel) when each fix informs the next.
- Calibrate tests last, in one focused pass, after all solver fixes are verified.

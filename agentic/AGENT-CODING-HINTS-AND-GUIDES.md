# Agent Coding Hints And Guides

## Foreground First

Do not spawn sub-agents for ordinary repo work.

Prefer:

- read files directly
- search with `rg`
- run snippets/tests directly
- patch files directly

The current work is geometry-heavy and conceptually tight. Context loss hurts more than parallelism helps.

## DNC Protocol

`DNC` means discussion only.

When the user says `DNC`:

- no file edits
- no code implementation
- no speculative patching

## REPL / Snippet Priority

When architecture is under discussion, prefer truth surfaces over source-only reasoning.

Use:

- runtime object APIs
- snippet outputs
- geometry dumps
- materialized renders
- collision reports

Do not rely on polished explanation when a snippet can answer the question.

## Physics First

Do not distort routing doctrine to satisfy stale expectations.

If geometry, algebra, and render output disagree:

- identify the owning layer
- fix the owning layer
- then update expectations

## Do Not Overclaim

If a fix is:

- local
- guarded
- partial
- realization-time only

then say so.

This branch already paid for overclaiming once. Do not repeat it.

## Documentation Discipline

When a meaningful design idea emerges, write it down promptly in the right place:

- `docs/worldscale_geometry.adoc` for world-scale routing doctrine
- `docs/ideas.adoc` for candidate but not accepted design ideas
- `papers/new_ways.adoc` for collaboration-method reflection, not engine doctrine

## Token Efficiency

- Read only the ranges you need when the location is known.
- Use snippets to narrow uncertainty before opening many files.
- Do not rewrite whole modules unless the architectural seam truly demands it.

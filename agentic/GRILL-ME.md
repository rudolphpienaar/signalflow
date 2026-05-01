# Grill-Me: Design Interview Protocol

## Trigger

User says "grill me", "interview me about this", or "stress-test this plan".

## Purpose

Force explicit design decisions before touching code. Prevents oscillation,
shallow pattern-matching, and "one step forward, one step sideways" failure
modes where the agent approximates answers without grounding them in actual
system behaviour.

Current design branch: the next SignalFlow sprint separates source modules from
load-bearing geometry scopes. If the user says "grill me" for this branch, the
interview must distinguish:

- source identity: `ChipId.moduleName`
- geometry scope: implicit call-depth layer
- drawable boundary: optional render policy

Do not ask whether modules should become depth layers. That is already rejected.
Ask only unresolved questions such as naming, YAML override surface, drawable
policy, and migration order.

## Protocol

1. **Explore the codebase first.** If a question can be answered by reading
   code or running a snippet, do that instead of asking. Never ask the user
   something the code can answer.

2. **Ask one question at a time.** Walk down the decision tree branch by
   branch. Resolve each node before proceeding to the next.

3. **Provide your recommended answer with each question.** State it as a
   recommendation with reasoning, not as a tentative guess. The user
   corrects, confirms, or redirects.

4. **Do not code until the interview is complete** (or the user explicitly
   asks to pause and implement what is agreed so far).

5. **Track agreed decisions explicitly.** Recap agreed answers when the user
   asks or when returning from a sidequest.

6. **Sidequests are fine — resume the interview after.** If a finding during
   the interview reveals a latent bug or a required prerequisite change,
   handle it and resume.

## Failure Modes to Avoid

- Pattern-matching to "closest fit" in existing code without verifying the
  geometric or semantic correctness of that fit.
- Agreeing with the user's framing without checking it against code.
- Abandoning a correct suggestion too quickly when pushed back on.
- Implementing before reaching shared understanding on all decision branches.

## Question Structure

For each question:
- State what is being decided and why it matters.
- Give your recommended answer with brief reasoning.
- Wait for user confirmation, correction, or redirect before proceeding.

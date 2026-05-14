# Graph Space Explosion: Visualizing the Agentic Orchestration Problem

This directory contains three YAML diagrams that visualize the **exponential growth of the action space** in agentic workflows. These diagrams directly support the mathematical argument in the **"Agentic Nondeterminism" paper** that demonstrates why LLM-based agentic orchestration is structurally unsafe for clinical computing.

## Overview

The paper proves that:
```
H_MCP(i; L) ≈ 1 - (1-ε)^L
|S(G)| ≈ d^L
```

Where:
- `H_MCP(i; L)` = probability of at least one orchestration error
- `d` = branching factor (choices per decision point)
- `L` = workflow depth (number of decision points)
- `ε` = per-step error rate

These diagrams **visually demonstrate** how `d^L` grows explosively even with modest parameters.

---

## The Three Diagrams

### 1. Binary Tree: `graph-space-01-binary.yaml`
**Configuration:** d=2, L=5
**Total paths:** 2^5 = **32 paths**
**Clinical scenario:** Two choices at each stage

```
Depth 1: images_collect()
         ├─ preprocess_A
         └─ preprocess_B
Depth 2:    ├─ segment_AA, segment_AB
            └─ segment_BA, segment_BB
Depth 3:       4 validate functions (AA, AB, BA, BB)
Depth 4:          8 analyze functions
Depth 5:             16 export functions
```

**Key insight:** Even with binary choices, 5 decision points yield 32 possible workflows. Only a tiny fraction would be clinically valid.

---

### 2. Ternary Tree: `graph-space-02-ternary.yaml`
**Configuration:** d=3, L=4
**Total paths:** 3^4 = **81 paths**
**Clinical scenario:** Three preprocessing methods, three segmentation algorithms, three validation strategies

```
Depth 1: images_collect()
         ├─ preprocess_A
         ├─ preprocess_B
         └─ preprocess_C
Depth 2:    9 segment functions (AA, AB, AC, BA, BB, BC, CA, CB, CC)
Depth 3:       27 validate functions
Depth 4:          81 analyze functions (terminal nodes)
```

**Key insight:** With just 3 choices per stage and 4 stages, we already have 81 possible workflows. The space grows **3x faster than binary** at each level.

---

### 3. Quaternary Tree: `graph-space-03-quaternary.yaml`
**Configuration:** d=4, L=3
**Total paths:** 4^3 = **64 paths**
**Clinical scenario:** Four preprocessing algorithms, four segmentation methods, four validation approaches

```
Depth 1: images_collect()
         ├─ preprocess_A
         ├─ preprocess_B
         ├─ preprocess_C
         └─ preprocess_D
Depth 2:    16 segment functions (AA, AB, AC, AD, BA, ..., DD)
Depth 3:       64 validate functions (AAA, AAB, ..., DDD)
```

**Key insight:** This is a **realistic branching factor** for modern tool registries (OpenAI MCP, Anthropic tool use). With just 3 decision points, we have 64 paths. At depth 4, this becomes 256. At depth 5, 1024.

---

## Exponential Growth Table

| Branching (d) | Depth 1 | Depth 2 | Depth 3 | Depth 4 | Depth 5 |
|---------------|---------|---------|---------|---------|---------|
| **d=2**       | 2       | 4       | 8       | 16      | **32**  |
| **d=3**       | 3       | 9       | 27      | **81**  | 243     |
| **d=4**       | 4       | 16      | **64**  | 256     | 1024    |
| **d=5**       | 5       | 25      | 125     | 625     | 3125    |
| **d=10**      | 10      | 100     | 1000    | 10000   | 100000  |

**Bold** = configurations visualized in our YAML diagrams.

---

## Connection to the IAS Paper

### Problem Statement (Section: Agents, Orchestration, and the Inevitable Risk of Depth)

From the paper:
> "A wrong tool, a wrong parameter, an omitted step, or a wrongly generated program are all instances of the same underlying phenomenon: probabilistic generation has been asked to serve as procedural control."

**These diagrams show the "wrong paths" visually.**

For a clinical intent like "Run MRI lesion segmentation pipeline," suppose only **ONE path** is clinically valid (e.g., `images_collect → preprocess_B → segment_BA → validate_BAA → analyze_BAAA`).

In the **d=4, L=3** case:
- Total paths: 64
- Valid paths: 1 (hypothetically)
- Invalid paths: **63**

The agent policy π_MCP(s | i) assigns probability mass over all 64 paths. Unless that mass is **exactly zero** on all 63 invalid paths, we have `H_MCP(i) > 0`.

---

### Mathematical Formulation (Section: Theoretical Formulation of the Action Space)

The paper defines:
```
S(G) = set of all reachable paths
S_valid ⊂ S(G) = clinically acceptable paths
S_invalid = S(G) \ S_valid
```

**Our diagrams literally render S(G)** as a directed acyclic graph where:
- Each function box = a node in the tool graph
- Each wire = a valid transition (edge)
- Each complete path from `images_collect()` to a terminal leaf = one workflow `s ∈ S(G)`

The **visual density** of the diagram shows why `|S_invalid| ≫ |S_valid|`.

---

### The Hallucination Probability Formula

From the paper:
```
H_MCP(i; L) ≈ 1 - (1-ε)^L
```

For `ε = 0.05` (5% per-step error), `L=5`:
```
H_MCP(i; 5) ≈ 1 - (0.95)^5
              ≈ 1 - 0.7738
              ≈ 0.226  (22.6% chance of error)
```

**The diagrams show the 32 paths where that 22.6% can manifest.**

For `ε = 0.10` (10% per-step error):
```
H_MCP(i; 5) ≈ 1 - (0.90)^5 ≈ 0.41  (41% error rate)
```

---

### IAS Collapse: From d^L to 1

The Intent-Action Service (IAS) solves this by **collapsing the action space**:

```
π_IAS(s | i) = { 1  if s = s_i (canonical workflow for intent i)
               { 0  otherwise
```

Instead of navigating a space of size `d^L`, the system:
1. **Interprets** user input `u` to intent `i` (probabilistic, but constrained)
2. **Compiles** intent `i` to workflow `s_i` (deterministic, F: I → S_valid)
3. **Executes** `s_i` (no agent in the loop)

**Visually:** IAS picks **exactly one highlighted path** through the diagram and executes only that path. No exploration, no branching, no runtime assembly.

---

## Presentation Strategy

### Slide 1: The Problem (Binary Tree)
**Title:** "Modest Branching, Explosive Growth"

- Show `graph-space-01-binary.yaml` rendered
- Annotate: "32 possible workflows, only 1 valid"
- Equation: `2^5 = 32`
- Message: "Even with binary choices, the space is large"

### Slide 2: Realistic Complexity (Quaternary Tree)
**Title:** "Real-World Tool Registries"

- Show `graph-space-03-quaternary.yaml` rendered
- Annotate: "64 workflows at depth 3"
- Equation: `4^3 = 64`, `4^5 = 1024`
- Message: "OpenAI MCP and Anthropic expose 10+ tools. This is conservative."

### Slide 3: The Mathematics
**Title:** "Hallucination is Structural, Not Fixable"

- Show growth table (d=2,3,4 vs L=1,2,3,4,5)
- Overlay formula: `H_MCP(i; L) = 1 - (1-ε)^L`
- Graph: Plot error probability vs depth for ε=0.05, 0.10, 0.15
- Message: "More tools + more steps = guaranteed failure"

### Slide 4: The Solution (IAS)
**Title:** "Collapse the Space: Intent → Single Canonical Workflow"

- Show same quaternary diagram
- **Highlight exactly ONE path in red**
- Label: "F(i) = s_i (deterministic)"
- Equation: `H_IAS(i) = 0` (by construction)
- Message: "Generative models choose the intent. Deterministic software executes the workflow."

---

## Rendering Commands

To generate ASCII visualizations for slides:

```bash
# Render all three diagrams
python -m signalflow.cli render examples/presentation/graph-space-01-binary.yaml > slides/binary-tree.txt
python -m signalflow.cli render examples/presentation/graph-space-02-ternary.yaml > slides/ternary-tree.txt
python -m signalflow.cli render examples/presentation/graph-space-03-quaternary.yaml > slides/quaternary-tree.txt
```

For presentation slides:
- Use **monospace font** (Courier New, Consolas, or Monaco at 10-12pt)
- **Increase vertical spacing** slightly for readability
- Consider **syntax highlighting** (gray boxes, different colors for depth levels)
- Export to **PNG** if embedding in PowerPoint/Keynote

---

## Advanced: Annotating Valid vs Invalid Paths

To make the "valid vs invalid" distinction even clearer, you could:

1. **Pick one canonical path** through each diagram
2. **Color-code** that path in green (if rendering supports color)
3. **Gray out** all other paths
4. **Add text annotation**: "Only this path is clinically validated"

Example for binary tree:
```
Canonical: images_collect → preprocess_B → segment_BA → validate_BAA → analyze_BAAA → export_BAAAA
Invalid: All other 31 paths
```

This visually reinforces:
```
|S_valid| = 1
|S_invalid| = 31
Ratio = 31:1  (96.8% of the space is invalid)
```

For d=4, L=3:
```
|S_valid| = 1
|S_invalid| = 63
Ratio = 63:1  (98.4% of the space is invalid)
```

---

## Key Talking Points

### For Technical Audiences

1. **"This is the tool graph G=(V,E)"**
   - Vertices = functions/tools
   - Edges = allowed transitions
   - Workflows = paths from root to leaf

2. **"The agent defines π_MCP(s|i), a probability distribution over this graph"**
   - Every wire the agent can traverse has some probability mass
   - Unless that mass is **exactly zero** on all invalid paths, `H_MCP(i) > 0`

3. **"IAS collapses this to a single path per intent"**
   - `F: Intent → Workflow` is a deterministic compiler
   - No runtime exploration, no branching, no agent-driven orchestration

### For Clinical Audiences

1. **"Each box is a medical imaging tool (preprocessing, segmentation, validation)"**
2. **"The diagram shows ALL possible ways an agent could combine these tools"**
3. **"Only ONE path is medically correct for a given patient and protocol"**
4. **"The agent will inevitably try wrong paths with non-zero probability"**
5. **"IAS ensures only the correct path is ever executed"**

### For Executive Audiences

1. **"This is why 'agentic AI' in healthcare is dangerous"**
2. **"The space of wrong answers is exponentially larger than the space of right answers"**
3. **"No amount of prompt engineering fixes this mathematical reality"**
4. **"IAS is the architectural solution: AI picks the goal, deterministic software executes the plan"**

---

## Related Work

These diagrams complement:
- **LLM-to-IAS.adoc** (the agentic nondeterminism paper)
- **Intent-server paper** (ChRIS external IAS architectural proposal)
- **Signal Flow Graph theory** (Mason, 1950s) - continuous-wire paradigm
- **POMDP agent formulation** (Lin et al., 2025 agent survey)

---

## Citation

If using these diagrams in academic presentations:

```
SignalFlow Rendering of Action Space Explosion
Supporting: Pienaar, R. (2025). "Reasoning, LLMs, and Agentic Programs:
Agents Will Always Lie, So Clinical Truth Must Live Outside the Model."
Boston Children's Hospital.
```

---

## Contact

For questions about these diagrams or the underlying IAS architecture:
- **Rudolph Pienaar** (rudolph.pienaar@childrens.harvard.edu)
- SignalFlow project: https://github.com/[signalflow-repo]
- Intent-server project: https://github.com/rudolphpienaar/intent-server

---

## Summary

| Diagram | Branching | Depth | Paths | Key Message |
|---------|-----------|-------|-------|-------------|
| **Binary** | d=2 | L=5 | 32 | "Even modest branching explodes" |
| **Ternary** | d=3 | L=4 | 81 | "Three choices is already huge" |
| **Quaternary** | d=4 | L=3 | 64 | "Realistic tool registries at shallow depth" |

**Exponential formula:** `|S(G)| = d^L`

**Theorem:** For any `ε > 0` and sufficiently large `L`, `H_MCP(i; L) → 1`

**Solution:** `H_IAS(i) = 0` by deterministic collapse `F: Intent → Workflow`

These diagrams make the abstract mathematics **visually concrete** and **clinically interpretable**.

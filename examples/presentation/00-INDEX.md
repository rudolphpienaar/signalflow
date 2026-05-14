# Presentation Materials Index

This directory contains all YAML diagrams and documentation for presentations on:
1. **SignalFlow** - ASCII rendering of execution circuits
2. **Intent-Action Service (IAS)** - Deterministic workflow compilation
3. **Agentic Nondeterminism** - Mathematical proof that LLM orchestration is unsafe

---

## Quick Start

```bash
# Render a diagram
python -m signalflow.cli render examples/presentation/presentation-01-simple-api.yaml

# Render all graph-space diagrams for IAS talk
python -m signalflow.cli render examples/presentation/graph-space-01-binary.yaml > binary.txt
python -m signalflow.cli render examples/presentation/graph-space-02-ternary.yaml > ternary.txt
python -m signalflow.cli render examples/presentation/graph-space-03-quaternary.yaml > quaternary.txt
```

---

## File Organization

### General SignalFlow Presentations
**Purpose:** Introduce SignalFlow's continuous-wire paradigm and use cases

| File | Description | Complexity | Best For |
|------|-------------|------------|----------|
| `presentation-01-simple-api.yaml` | API Request→Parse→Process→Format | Simple | Opening slide |
| `presentation-02-microservices.yaml` | Orchestrator→[Auth,Data,Cache]→Aggregator | Medium | Fanout pattern |
| `presentation-03-error-handling.yaml` | Validate→Execute→ErrorHandler | Medium | Transformation vs passthrough |
| `presentation-04-data-pipeline.yaml` | ETL: Extract→Clean→Enrich→Validate→Load | Medium | Data engineering |
| `presentation-05-web-request.yaml` | Full HTTP lifecycle (6 stages) | High | Complete architecture |
| `presentation-06-minimal-leaf.yaml` | Single terminal function | Minimal | Quick demo |
| `presentation-07-callback-pattern.yaml` | Dispatcher→[Handlers]→Logger | Medium | Event-driven systems |

**Documentation:** `PRESENTATION-README.md`

---

### IAS / Agentic Nondeterminism Materials
**Purpose:** Visualize exponential growth of action space to support IAS paper

| File | Branching (d) | Depth (L) | Paths | Best For |
|------|---------------|-----------|-------|----------|
| `graph-space-01-binary.yaml` | 2 | 5 | 32 | "Modest branching still explodes" |
| `graph-space-02-ternary.yaml` | 3 | 4 | 81 | "Three choices is huge" |
| `graph-space-03-quaternary.yaml` | 4 | 3 | 64 | "Realistic tool registries" |

**Documentation:** `GRAPH-SPACE-README.md`

**Key formula:** `|S(G)| = d^L` (action space grows exponentially)

---

## Presentation Flow Recommendations

### Scenario 1: SignalFlow Introduction (General Technical Audience)
**Goal:** Explain the continuous-wire paradigm and differentiate from UML/Flame Graphs

1. Start: `presentation-06-minimal-leaf.yaml` (1 min)
   - "Simplest case: U-turn in a terminal function"
2. Build: `presentation-01-simple-api.yaml` (2 min)
   - "Linear flow through 4 functions"
3. Complexity: `presentation-04-data-pipeline.yaml` (3 min)
   - "ETL pipeline showing sequential threading"
4. Real-world: `presentation-05-web-request.yaml` (5 min)
   - "Full HTTP request with module boundaries"
5. Patterns: `presentation-02-microservices.yaml` (3 min)
   - "Fanout and convergence topology"

**Total:** 14 minutes + Q&A

---

### Scenario 2: IAS Paper Presentation (Academic/Clinical Audience)
**Goal:** Prove that agentic orchestration is structurally unsafe, IAS is the remedy

1. **Problem Setup** (5 min)
   - Clinical workflow: MRI lesion segmentation
   - Tools: preprocessing, segmentation, validation, analysis, export
   - Question: "Should an LLM assemble this workflow at runtime?"

2. **Action Space Explosion** (10 min)
   - Show `graph-space-01-binary.yaml`: "d=2, L=5 → 32 paths"
   - Show `graph-space-03-quaternary.yaml`: "d=4, L=3 → 64 paths"
   - Table: Growth from d=2 to d=10, L=1 to L=5
   - Formula: `|S(G)| = d^L`

3. **Mathematical Formulation** (8 min)
   - Define `S(G)`, `S_valid`, `S_invalid`
   - Agent policy: `π_MCP(s | i)` over all paths
   - Hallucination probability: `H_MCP(i) = 1 - Σ π_MCP(s | i)` for s ∈ S_valid
   - **Theorem:** If ε > 0 anywhere, then H_MCP(i; L) → 1 as L grows

4. **The IAS Solution** (7 min)
   - Show same quaternary diagram with **ONE path highlighted**
   - "F(i) = s_i" (deterministic compilation)
   - `H_IAS(i) = 0` by construction
   - Staged IAS: state-grounded local collapse

5. **Experimental Design** (5 min)
   - ChRIS medical imaging testbed
   - MCP-agent condition vs IAS condition
   - Metrics: reproducibility, invalid sequences, human assessment

**Total:** 35 minutes + 10 min Q&A = 45 min talk

---

### Scenario 3: Executive Briefing (Non-Technical Leadership)
**Goal:** "Why agentic AI in healthcare is dangerous; what IAS does about it"

1. **The Promise** (2 min)
   - "AI that can run medical imaging workflows on its own"
   - Show `presentation-05-web-request.yaml` as "what they're proposing"

2. **The Problem** (5 min)
   - Show `graph-space-03-quaternary.yaml`
   - "64 possible workflows. Only 1 is correct for this patient."
   - "The AI will try wrong ones with non-zero probability."
   - Analogy: "Self-driving car that crashes 2% of the time"

3. **The Mathematics** (3 min)
   - Simple growth table (d vs L)
   - "More tools → worse, not better"
   - "This is not a bug. It's structural."

4. **The Solution** (5 min)
   - "IAS: Intent-Action Service"
   - "AI picks the goal. Software executes the plan."
   - Show same diagram with ONE highlighted path
   - "Zero runtime exploration. Zero hallucination risk."

5. **Next Steps** (2 min)
   - ChRIS proof-of-concept
   - Timeline: Q4 2025 - Q1 2026
   - Publication target: IEEE Software, Q2 2026

**Total:** 17 minutes + Q&A

---

## Key Equations & Formulas

### Action Space Size
```
|S(G)| ≈ d^L
```
- d = branching factor (choices per decision point)
- L = workflow depth (number of decision points)

### Hallucination Probability (per-step model)
```
H_MCP(i; L) ≈ 1 - (1 - ε)^L
```
- ε = per-step error rate
- As L → ∞, H_MCP → 1 (guaranteed failure)

### IAS Deterministic Collapse
```
F: Intent → Workflow
π_IAS(s | i) = { 1 if s = s_i, 0 otherwise }
H_IAS(i) = 0
```

---

## Rendering Tips

### For Slides
1. **Font:** Monospace (Courier New, Consolas, Monaco) at 11-14pt
2. **Background:** White or light gray (avoid pure black terminals)
3. **Syntax highlighting:** Optional, but helps differentiate layers
4. **Export:** PNG at 300 DPI for print, 150 DPI for screen

### For Papers
1. **Format:** Keep ASCII in code blocks with fixed-width font
2. **Caption:** "SignalFlow rendering of [scenario]. Each box is a function; wires show execution flow."
3. **Reference:** Cite both SignalFlow and the specific YAML file

### For Live Demo
1. **Terminal:** Use large font (18-20pt) for visibility
2. **Color scheme:** High contrast (light background recommended)
3. **Scrolling:** Pre-render to files to avoid scrolling during talk

---

## File Sizes & Rendering Times

Approximate rendering times on a modern laptop:

| File | Functions | Rendering Time | ASCII Size |
|------|-----------|----------------|------------|
| presentation-01-simple-api.yaml | 4 | <1s | ~50 lines |
| presentation-02-microservices.yaml | 5 | <1s | ~70 lines |
| presentation-05-web-request.yaml | 6 | ~1s | ~90 lines |
| graph-space-01-binary.yaml | 32 | ~2s | ~500 lines |
| graph-space-02-ternary.yaml | 81 | ~5s | ~1500 lines |
| graph-space-03-quaternary.yaml | 64 | ~3s | ~1000 lines |

**Note:** Ternary and quaternary diagrams are **very large**. Consider rendering to file and using image viewer for presentations rather than live terminal display.

---

## Related Documentation

- **SignalFlow Core Docs:** `/docs/overview.adoc`, `/docs/architecture.adoc`
- **IAS Architecture Paper:** `/termux-home/Projects/intent-server/paper-engineering/`
- **Agentic Nondeterminism Paper:** `/termux-home/Projects/intent-server/agentic-nondeterminism/LLM-to-IAS.adoc`
- **YAML Syntax:** `/docs/yaml_syntax.adoc`

---

## Questions to Prepare For

### Technical
1. **Q:** "Can't we just train the model to avoid invalid paths?"
   **A:** "No. Even with perfect training data, ε > 0 unless you remove all runtime freedom, at which point it's not agentic."

2. **Q:** "What about retrieval-augmented generation (RAG)?"
   **A:** "RAG constrains content selection, not procedural assembly. IAS addresses a different layer."

3. **Q:** "How do you define S_valid?"
   **A:** "Clinical governance, institutional protocols, regulatory requirements. Validated by domain experts offline."

### Clinical
1. **Q:** "Does IAS prevent all errors?"
   **A:** "No. It eliminates orchestration hallucinations (wrong workflow). Semantic errors (wrong intent interpretation) remain."

2. **Q:** "Can IAS adapt to new protocols?"
   **A:** "Yes. Add new intents and their canonical workflows. The compiler is updated, not the agent."

3. **Q:** "What about edge cases the designers didn't think of?"
   **A:** "That's a limitation of any prevalidated system. But it's the same limitation we accept for medical devices."

### Executive
1. **Q:** "Is this just fear-mongering about AI?"
   **A:** "No. We're using AI for interpretation (user input → intent). We're just not using it for execution."

2. **Q:** "What's the business case?"
   **A:** "Regulatory approval. FDA won't approve a probabilistic orchestrator. Deterministic IAS fits existing device frameworks."

3. **Q:** "When can we deploy this?"
   **A:** "Proof-of-concept in 6 months. Production in 12-18 months after validation studies."

---

## Citation

```bibtex
@misc{signalflow2025graphspace,
  title={SignalFlow Graph Space Visualizations for Agentic Orchestration Analysis},
  author={Pienaar, Rudolph},
  year={2025},
  howpublished={SignalFlow Examples},
  url={https://github.com/[repo]/examples/presentation/}
}
```

---

## Contact

**Rudolph Pienaar**
- Email: rudolph.pienaar@childrens.harvard.edu
- Institution: Boston Children's Hospital
- Projects: ChRIS, SignalFlow, Intent-Server

---

**Last Updated:** 2025-05-13
**SignalFlow Version:** v5.9.2

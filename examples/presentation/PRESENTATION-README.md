# SignalFlow Presentation Diagrams

This directory contains 7 YAML block diagrams specifically designed for presentation purposes. Each demonstrates a different aspect of SignalFlow's capabilities.

## Quick Start

To render any diagram:
```bash
# If you have the SignalFlow CLI installed:
signalflow render examples/presentation-01-simple-api.yaml

# Or use Python directly:
python -m signalflow.cli render examples/presentation-01-simple-api.yaml
```

## Diagram Overview

### 1. **presentation-01-simple-api.yaml** - Introduction Level
**Purpose:** Introduce the continuous-wire paradigm
**Complexity:** Simple linear flow (4 functions)
**Best for:** Opening slide, explaining basic concepts
**Key concepts:** Request→Parse→Process→Format pipeline

**Use this to explain:**
- The "single wire" that flows through all functions
- How signals transform as they move through chips
- The U-turn at terminal functions

---

### 2. **presentation-02-microservices.yaml** - Fanout Pattern
**Purpose:** Show parallel service calls with convergence
**Complexity:** Medium (1 orchestrator → 3 services → 1 aggregator)
**Best for:** Microservice architecture discussions
**Key concepts:** Fanout, canonical chip reuse, convergence

**Use this to explain:**
- How one parent can fan out to multiple children
- How multiple paths converge to a single shared hub
- The "declaration vs. reference" concept (Aggregator appears once)

---

### 3. **presentation-03-error-handling.yaml** - Transformation vs. Passthrough
**Purpose:** Demonstrate computation blocks and transformations
**Complexity:** Medium (4-stage pipeline)
**Best for:** Explaining visual grammar (pure vs. compute)
**Key concepts:** Validation layers, error wrapping, boundary transformations

**Use this to explain:**
- Difference between passthrough (internal_wiring present) and transformation (absent)
- How computation blocks (`▬` or `█`) indicate data transformation
- Error handling patterns

---

### 4. **presentation-04-data-pipeline.yaml** - Sequential Processing
**Purpose:** Classic ETL pattern
**Complexity:** Medium (5-stage sequential pipeline)
**Best for:** Data engineering audience
**Key concepts:** Extract→Transform→Load, sequential threading

**Use this to explain:**
- Long sequential chains of transformations
- How internal_wiring creates manifold routing between stages
- Module boundaries for organizational clarity

---

### 5. **presentation-05-web-request.yaml** - Full System Architecture
**Purpose:** Complete web request lifecycle
**Complexity:** High (6-stage with modular boundaries)
**Best for:** Web development audience, architecture discussions
**Key concepts:** Middleware, routing, database, rendering, logging

**Use this to explain:**
- Modular encapsulation with double-line module boxes
- Boundary piercing markers (`╫` horizontal, `╪` vertical)
- How architectural layers are visually separated
- End-to-end request flow

---

### 6. **presentation-06-minimal-leaf.yaml** - Simplest Case
**Purpose:** Absolute minimum example
**Complexity:** Minimal (single function)
**Best for:** Quick demo or backup slide
**Key concepts:** Leaf chip, U-turn, minimal geometry

**Use this to explain:**
- The simplest possible SignalFlow diagram
- How a function with no children creates a U-turn
- The computation block on the return path

---

### 7. **presentation-07-callback-pattern.yaml** - Event Handling
**Purpose:** Observer/callback pattern
**Complexity:** Medium (1 dispatcher → 3 handlers → 1 logger)
**Best for:** Event-driven architecture discussions
**Key concepts:** Event dispatching, multiple handlers, logging hub

**Use this to explain:**
- Event-driven architecture patterns
- Multiple independent handlers for the same event type
- How SignalFlow represents callbacks and observers

---

## Presentation Flow Recommendations

### For Technical Audiences (Engineers, Architects)
1. Start with **#6 (Minimal Leaf)** - show the absolute basics
2. Move to **#1 (Simple API)** - introduce linear flow
3. Show **#4 (Data Pipeline)** - demonstrate sequential processing
4. Present **#2 (Microservices)** - introduce fanout and convergence
5. Deep dive with **#5 (Web Request)** - show full system architecture
6. Discuss patterns with **#7 (Callback)** - event-driven design

### For Executive/Design Audiences
1. Start with **#1 (Simple API)** - clear and intuitive
2. Show **#2 (Microservices)** - business-relevant pattern
3. Present **#5 (Web Request)** - complete system view
4. Keep **#6 (Minimal)** as backup for questions

### For Academic/Research Audiences
1. Start with **#6 (Minimal Leaf)** - establish the grammar
2. Introduce **#3 (Error Handling)** - transformation semantics
3. Show **#1 (Simple API)** - basic composition
4. Discuss **#4 (Data Pipeline)** - sequential threading
5. Present **#2 (Microservices)** - graph topology (DAG)
6. Compare with **#5 (Web Request)** - modular boundaries

---

## Key Talking Points

### The SignalFlow Difference

**vs. UML Sequence Diagrams:**
- UML uses vertical timeline with independent arrows
- SignalFlow uses continuous wire that must be physically traceable
- UML shows temporal sequence; SignalFlow shows topological circuit

**vs. Flame Graphs:**
- Flame graphs show time-on-CPU statistics (performance profiling)
- SignalFlow shows logical structure and data flow (architecture understanding)
- Flame graphs are quantitative; SignalFlow is qualitative

### Core Principles

1. **One Wire, One Path** - The entire execution is a single unbroken wire
2. **Topological Space** - Functions are placed in 2D space, not temporal sequence
3. **Deterministic Rendering** - Same input always produces identical output
4. **ASCII Art** - Version control friendly, universally accessible
5. **Signal Flow Graph Heritage** - Based on 1950s systems theory by Samuel Mason

### Visual Grammar

- **Pure wire** (`─` or clean hline): passthrough, no transformation
- **Computation block** (`▬` or `█`): transformation occurs
- **Module boundary** (double lines): architectural encapsulation
- **Boundary piercing** (`╫` horizontal, `╪` vertical): crossing module boundaries

---

## Rendering Tips

### For Presentations
- Use monospace font for proper alignment
- Increase font size for readability (14-16pt minimum)
- Consider dark mode friendly colors
- Save rendered output to text files for slide inclusion

### Configuration Tweaks
- `channelWidth`: Adjust horizontal spacing (20-35 typical)
- `verticalChipPadding`: Adjust vertical spacing (3-5 typical)
- `module_box_padding`: Control module boundary spacing

### Common Adjustments
```yaml
config:
  channelWidth: 32              # Wider for more spacing
  verticalChipPadding: 5        # Taller for clarity
  internal_wiring:
    colorize: false             # Disable for B&W presentations
    shareRoutes: false          # Cleaner routing
```

---

## Further Examples

For more complex examples, see:
- `hub.yaml` - Complex fanout with 5→1→5 topology
- `passthrough.yaml` - Internal wiring manifold demonstrations
- `branch-converging.yaml` - Multiple convergence points
- `stress-hub.yaml` - Stress test with many simultaneous routes

---

## Questions to Address in Presentation

**Q: Why ASCII instead of SVG/graphical format?**
A: Version control compatibility, universal accessibility, simplicity, diff-ability

**Q: How does this help with debugging?**
A: Visualizes actual execution path, not just static code structure

**Q: Can this scale to large systems?**
A: Yes - uses routing zones and grid system for arbitrary complexity

**Q: What about recursive calls?**
A: Self-edges loop back to the same chip (no cloning)

**Q: How is this different from call graphs?**
A: Shows continuous wire path with data flow, not just call relationships

---

## Contact & Resources

- Project: SignalFlow ASCII Rendering Engine
- Documentation: See `docs/` directory
- Examples: See `examples/` directory
- Tests: 566+ passing tests demonstrating correctness

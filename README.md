# signalFlow 5.1.2

### Topological Call-Thread Schematic Renderer

SignalFlow is a domain-specific ASCII rendering engine that maps recursive software call trees into a 2D topological space. Inspired by **Signal Flow Graphs (SFG)** from systems and information engineering, it treats the execution of a program not as a series of discrete messages, but as a **Single-Thread Weave** that travels through a modular circuit.

Version 5.1.2 keeps the v5 `internal_wiring` model and renderer stability work,
and adds a repo-wide refactor/docstring cleanup pass: the remaining god-method
cluster was broken into smaller helpers, the style-guide Python baseline is now
enforced as 3.11+, and `ruff` plus the full test suite pass cleanly.

The repository also now carries an explicit re-architecture track beside the
legacy engine. The current architectural target is a `RoutingZoneGrid` /
`RoutingZone` / `RoutingZoneInterconnect` world model, with a typed
`CircuitDocumentSource` -> `CircuitDocument` ingress layer already in place.

---

## The Paradigm

Unlike traditional UML Sequence Diagrams that rely on a vertical time-axis and independent arrows, SignalFlow prioritizes **topological continuity**. 

- **The Wire:** A single, unbroken thread representing the execution path as it unrolls through the system.
- **The Chips:** Functions are represented as "chips" with symmetric entry/exit ports.
- **The Signals:** Input and output variables are the "signals" that flow along the wire and are transformed as they pierce through modular boundaries.
- **The Boundaries:** Double-lined module boxes (`╔═ ║ ═╝`) enforce architectural encapsulation, with explicit markers for horizontal (`╫`) and vertical (`╪`) wall crossings.

By enforcing the "one-wire" constraint, SignalFlow provides a high-density **System Schematic** that makes causality, transformation, and modular coupling immediate and visceral.

---

## Example

Given a recursive call tree in YAML:

```yaml
title: "non-root parent — pass-through single child"
tree:
  module: App.ts
  func: "main()"
  output_signal: "model"
  output_return: "model"
  calls:
    - module: Adapter.ts
      func: "transform()"
      input_signal: "input"
      input_return: "output"
      output_signal: "payload"
      output_return: "result"
      calls:
        - module: Codec.ts
          func: "encode()"
          input_signal: "input"
          input_return: "payload"
          calls: []
```

SignalFlow produces a clean, architectural schematic:

```
  == non-root parent — pass-through single child ==

    ╔═ App.ts ════════════╗                ╔═ Adapter.ts ════════╗                ╔═ Codec.ts ════════╗
    ║                     ║                ║                     ║                ║                   ║
    ║                     ║                ║                     ║                ║                   ║
    ║ ┌───────────────┐   ║                ║ ┌───────────────┐   ║                ║ ┌───────────────┐ ║
    ║ │     main()    │   ║                ║ │  transform()  │   ║                ║ │    encode()   │ ║
    ║ ├───────────────┤   ║                ║ ├───────────────┤   ║                ║ ├───────────────┤ ║
    ║ │               ├►model──────────input►┼───────────────┼►payload────────input►┼──┐            │ ║
    ║ │               ├◄model─────────output◄┼───────────────┼◄result───────payload◄┼──┘            │ ║
    ║ └───────────────┘   ║                ║ └───────────────┘   ║                ║ └───────────────┘ ║
    ║                     ║                ║                     ║                ║                   ║
    ╚═════════════════════╝                ╚═════════════════════╝                ╚═══════════════════╝
```

---

## Install

```bash
pip install -e .
```

Requires Python 3.11+.

---

## Usage

```bash
# Render a YAML file
signalflow examples/show-cohort.yaml

# Read YAML from stdin
cat my_tree.yaml | signalflow -

# Run the built-in example
signalflow --example

# Explicit engine selection
signalflow --engine legacy examples/hub.yaml
signalflow --engine new examples/root-multi-child.yaml
```

---

## Design Philosophy

SignalFlow is built on the principle of **"Lateral Thinking with Withered Technology"** (*Kareta Gijutsu no Horisontaru Shikō*). By applying 1950s systems theory (Mason's Signal Flow Graphs) to a stable, 1970s medium (ASCII character grids), it delivers a tool that is:

- **Durable:** Diagrams are part of the codebase, version-controllable, and text-searchable.
- **Universal:** Renders in any terminal, editor, or browser.
- **Rigorous:** Forces an accounting of every call and return in the execution circuit.

---

## Documentation

For a deeper dive into the theory and mechanics:

- **[Architecture Overview](docs/overview.adoc):** Philosophical background, SFG lineage, and differential diagnosis against UML.
- **[Re-Architecture Contract](docs/re-architecture.adoc):** Current design contract for the new engine.
- **[RoutingZone Note](docs/routingZone.txt):** Canonical note for `RoutingZoneGrid`, `RoutingZone`, and `RoutingZoneInterconnect`.
- **[Chip Reference](docs/chip.adoc):** First-class chip concept in the re-architecture.
- **[Circuit Reference](docs/circuit.adoc):** Typed YAML ingress and validated circuit graph.
- **[YAML to Circuits](docs/yamlToCircuits.adoc):** Current stage-by-stage workflow from YAML through placement planning.
- **[RoutingZone Reference](docs/routingZone.adoc):** Atomic local routing block.
- **[RoutingZoneInterconnect Reference](docs/routingZoneInterconnect.adoc):** Seam continuity between neighboring zones.
- **[RoutingZoneGrid Reference](docs/routingZoneGrid.adoc):** World topology and macro path selection.
- **[Architecture Reference](docs/architecture.adoc):** Legacy/current implementation model and renderer contracts.
- **[Internal Wiring Reference](docs/internalWiring.adoc):** Manifold bands/zones, endpoint identity, and W1-W5 routing.
- **[YAML Syntax Guide](docs/yaml_syntax.adoc):** Definitive input syntax, compatibility notes, and canonical examples.
- **[Wire Model Reference](docs/wire-model.md):** Technical specification for chip geometry, port symmetry, and boundary piercing rules.

---

## Cite

See `CITATION.cff` for citation details in research or professional documentation.

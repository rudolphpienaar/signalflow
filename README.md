# signalFlow

### Topological Call-Thread Schematic Renderer

SignalFlow is a domain-specific ASCII rendering engine that maps recursive software call trees into a 2D topological space. Inspired by **Signal Flow Graphs (SFG)** from systems and information engineering, it treats the execution of a program not as a series of discrete messages, but as a **Single-Thread Weave** that travels through a modular circuit.

---

## 🛰️ The Paradigm

Unlike traditional UML Sequence Diagrams that rely on a vertical time-axis and independent arrows, SignalFlow prioritizes **topological continuity**. 

- **The Wire:** A single, unbroken thread representing the execution path as it unrolls through the system.
- **The Chips:** Functions are represented as "chips" with symmetric entry/exit ports.
- **The Signals:** Input and output variables are the "signals" that flow along the wire and are transformed as they pierce through modular boundaries.
- **The Boundaries:** Double-lined module boxes (`╔═ ║ ═╝`) enforce architectural encapsulation, with explicit markers for horizontal (`╫`) and vertical (`╪`) wall crossings.

By enforcing the "one-wire" constraint, SignalFlow provides a high-density **System Schematic** that makes causality, transformation, and modular coupling immediate and visceral.

---

## 🎨 Example

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

## 🛠️ Install

```bash
pip install -e .
```

Requires Python 3.12+.

---

## 🚀 Usage

```bash
# Render a YAML file
signalflow examples/show-cohort.yaml

# Read YAML from stdin
cat my_tree.yaml | signalflow -

# Run the built-in example
signalflow --example
```

---

## 📐 Design Philosophy

SignalFlow is built on the principle of **"Lateral Thinking with Withered Technology"** (*Kareta Gijutsu no Horisontaru Shikō*). By applying 1950s systems theory (Mason's Signal Flow Graphs) to a stable, 1970s medium (ASCII character grids), it delivers a tool that is:

- **Durable:** Diagrams are part of the codebase, version-controllable, and text-searchable.
- **Universal:** Renders in any terminal, editor, or browser.
- **Rigorous:** Forces an accounting of every call and return in the execution circuit.

---

## 📚 Documentation

For a deeper dive into the theory and mechanics:

- **[Architecture Overview](docs/overview.adoc):** Philosophical background, SFG lineage, and differential diagnosis against UML.
- **[Wire Model Reference](docs/wire-model.md):** Technical specification for chip geometry, port symmetry, and boundary piercing rules.

---

## 🏷️ Cite

See `CITATION.cff` for citation details in research or professional documentation.

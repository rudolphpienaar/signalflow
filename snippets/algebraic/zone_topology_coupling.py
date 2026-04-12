"""Print the symbolic coupling graph for the WTE board topology.

Shows all declared drag and stretch edges grouped by anchor token.
No board YAML needed — purely symbolic.

Usage from CLI:
    uv run python snippets/algebraic/zone_topology_coupling.py

Run from the REPL with:
    load("snippets/algebraic/zone_topology_coupling.py")
"""

from __future__ import annotations

from signalflow.board.geometry.topology import (
    TopologyCouplingKind,
    wteZoneBoardTopologySchema_build,
)
from signalflow.notation.sfn import sfN

schema = wteZoneBoardTopologySchema_build()

# Group edges by anchor token in declaration order.
anchorOrder: list[sfN] = []
seen: set[sfN] = set()
for edge in schema.couplingEdges:
    if edge.anchor not in seen:
        anchorOrder.append(edge.anchor)
        seen.add(edge.anchor)

print(f"WTE topology coupling graph  ({len(schema.couplingEdges)} edges)")
print()

for anchor in anchorOrder:
    dragTargets = schema.dragTargets_get(anchor)
    stretchEdges = schema.stretchEdges_get(anchor)
    if not dragTargets and not stretchEdges:
        continue
    print(f"  {anchor.name:<4}")
    for target in dragTargets:
        print(f"    ~=>  {target.name}")
    for edge in stretchEdges:
        face = edge.dependentFace.value if edge.dependentFace else "?"
        print(f"    ~+>  {edge.dependent.name}[{face}]")

print()
print(f"total drag edges:    "
      f"{sum(1 for e in schema.couplingEdges
            if e.kind is TopologyCouplingKind.DRAG)}")
print(f"total stretch edges: "
      f"{sum(1 for e in schema.couplingEdges
            if e.kind is TopologyCouplingKind.STRETCH)}")

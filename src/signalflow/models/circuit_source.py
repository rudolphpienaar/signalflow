"""Serialized source models for circuit YAML ingress.

This module models the YAML document shape accepted by the new engine before
that source is normalized into first-class `Chip` objects and the validated
`CircuitDocument` graph. The goal is to keep raw dicts at the parser edge only.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CircuitPortDeclarationSource:
    """Serialized source form of one port declaration."""

    signalName: str | None = None
    returnName: str | None = None


@dataclass(frozen=True)
class CircuitPortDeclarationSourceSet:
    """Modeled collection of serialized port declarations."""

    portDeclarationSources: tuple[CircuitPortDeclarationSource, ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True)
class CircuitWiringDirectiveSource:
    """Serialized source form of one internal-wiring directive."""

    wiringDeclaration: str


@dataclass(frozen=True)
class CircuitWiringDirectiveSourceSet:
    """Modeled collection of serialized internal-wiring directives."""

    wiringDirectiveSources: tuple[CircuitWiringDirectiveSource, ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True)
class CircuitChipIoInputSource:
    """Serialized source form of the `chip_io.input` block."""

    explicit: bool | None = None


@dataclass(frozen=True)
class CircuitChipIoInternalWiringSource:
    """Serialized source form of the `chip_io.internal_wiring` block."""

    colorize: bool | None = None
    showInternalLabels: bool | None = None
    aliasInternalLabels: bool | None = None


@dataclass(frozen=True)
class CircuitChipIoSource:
    """Serialized source form of the `chip_io` block."""

    chipIoInputSource: CircuitChipIoInputSource | None = None
    chipIoInternalWiringSource: CircuitChipIoInternalWiringSource | None = None


@dataclass(frozen=True)
class CircuitChildCallSource:
    """Serialized source form of one child call occurrence."""

    childNodeSource: CircuitNodeSource
    bindOutputPortDeclarationSource: CircuitPortDeclarationSource | None = None


@dataclass(frozen=True)
class CircuitNodeSourceChildren:
    """Modeled collection of serialized child call occurrences."""

    childCallSources: tuple[CircuitChildCallSource, ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True)
class CircuitNodeSource:
    """Serialized source form of one nested circuit source node."""

    moduleName: str
    functionName: str
    hasExplicitInputPorts: bool = False
    hasExplicitOutputPorts: bool = False
    inputPortDeclarationSourceSet: CircuitPortDeclarationSourceSet = field(
        default_factory=CircuitPortDeclarationSourceSet
    )
    outputPortDeclarationSourceSet: CircuitPortDeclarationSourceSet = field(
        default_factory=CircuitPortDeclarationSourceSet
    )
    wiringDirectiveSourceSet: CircuitWiringDirectiveSourceSet = field(
        default_factory=CircuitWiringDirectiveSourceSet
    )
    chipIoSource: CircuitChipIoSource | None = None
    childNodeSources: CircuitNodeSourceChildren = field(
        default_factory=CircuitNodeSourceChildren
    )


@dataclass(frozen=True)
class CircuitDocumentSource:
    """Serialized source form of one top-level circuit document."""

    title: str = ""
    rootNodeSource: CircuitNodeSource | None = None

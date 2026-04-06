"""sfN: canonical symbolic notation for all SignalFlow geometry regions.

This is the single source of truth for region naming across the board,
routing, and geometry layers. String literals scattered across builders,
realizers, solvers, and channel runtimes should be derived from this
enum rather than hardcoded independently.

Naming convention
-----------------
Member name  = sfN token used in code and path notation
Member value = long-form human-readable description used in display,
               docs, and diagnostics

The token grammar is intentionally variable-width. The notation stays as
short as possible, and only grows when more semantic information is needed.
This is deliberate: ``Wi`` and ``Ei`` are complete names already, while
compound regions such as ``Wfi`` or ``NWi`` need one extra character.

Token grammar:
  - first capital letter:
      primary compass anchor
      ``W`` / ``E`` imply longitude; ``N`` / ``S`` imply latitude
  - optional second capital letter:
      secondary compass anchor for compound corner regions
      examples: ``NW`` / ``SE``
  - lowercase suffix letters:
      semantic modifiers
      ``i`` = intra
      ``e`` = extra
      ``f`` = fan
      ``t`` = terminal
      ``x`` = transfer

Examples:
  - ``Wi``  = west intra routing band
  - ``Wfi`` = west fan intra
  - ``Wt``  = west terminal
  - ``NWi`` = north-west intra corner
  - ``NWx`` = north-west transfer

So the notation is not fixed-width; it is minimal-width and unambiguous.
"""

from __future__ import annotations

from enum import Enum


class sfN(Enum):
    """Canonical symbolic name for every geometry region in a SignalFlow zone.

    Use ``sfN.Wi`` etc. in code; ``sfN.Wi.name`` gives the compact token
    ``"Wi"``; ``sfN.Wi.value`` gives the long-form description.
    Token width is intentionally variable by region kind.
    """

    # --------------------------------------------------------------
    # intra ring
    Wi = "West Intra Longitude"
    Ei = "East Intra Longitude"
    Ni = "North Intra Latitude"
    Si = "South Intra Latitude"
    Ci = "Intra Courtyard"

    # --------------------------------------------------------------
    # extra ring
    We = "West Extra Longitude"
    Ee = "East Extra Longitude"
    Ne = "North Extra Latitude"
    Se = "South Extra Latitude"

    # --------------------------------------------------------------
    # terminals
    Wt = "West Terminal"
    Et = "East Terminal"
    Nt = "North Terminal"
    St = "South Terminal"

    # ------------------------------------------------------------------ fans
    Wfi = "West Fan Intra"
    Wfe = "West Fan Extra"
    Efi = "East Fan Intra"
    Efe = "East Fan Extra"
    Nfi = "North Fan Intra"
    Nfe = "North Fan Extra"
    Sfi = "South Fan Intra"
    Sfe = "South Fan Extra"

    # --------------------------------------------
    # intra corners (implicit in paths)
    NWi = "North West Intra Corner"
    NEi = "North East Intra Corner"
    SWi = "South West Intra Corner"
    SEi = "South East Intra Corner"

    # --------------------------------------------------------------
    # extra corners
    NWe = "North West Extra Corner"
    NEe = "North East Extra Corner"
    SWe = "South West Extra Corner"
    SEe = "South East Extra Corner"

    # --------------------------------------------------------------
    # intra/extra transfers
    NWx = "North West Transfer"
    NEx = "North East Transfer"
    SWx = "South West Transfer"
    SEx = "South East Transfer"

    # --------------------------------------------------------------
    # public

    @property
    def region_key(self) -> str | None:
        """Internal geometry lookup key (``"side/family"`` format).

        Returns ``None`` for regions that do not yet have a standardised
        key in the geometry layer (corners, extra fans, transfers).
        """
        return _REGION_KEYS.get(self)

    @property
    def channel_name(self) -> str | None:
        """Legacy symbolic channel token used by the solver/runtime.

        Returns ``None`` for non-routing regions
        (terminals, fans, corners).
        """
        return _CHANNEL_NAMES.get(self)

    @property
    def symbol(self) -> str | None:
        """Canonical text glyph for displayable named regions."""

        return _REGION_SYMBOLS.get(self)

    @classmethod
    def from_region_key(cls, key: str) -> sfN | None:
        """Resolve an internal geometry key to its sfN member.

        Args:
            key: Geometry-layer key such as ``"west/intra_routing_longitude"``.

        Returns:
            Matching ``sfN`` member, or ``None`` if the key is not recognised.
        """
        return _REGION_KEY_INDEX.get(key)

    @classmethod
    def symbolFromRegionKey_get(cls, key: str) -> str | None:
        """Resolve the canonical display glyph for a geometry region key."""

        baseKey = key.split(":", 1)[0]
        region = cls.from_region_key(baseKey)
        if region is None:
            return None
        return region.symbol

    @classmethod
    def from_channel_name(cls, name: str) -> sfN | None:
        """Resolve a legacy channel token to its sfN member.

        Args:
            name: Channel token such as ``"wLong"`` or ``"nLat"``.

        Returns:
            Matching ``sfN`` member, or ``None`` if the name is not recognised.
        """
        return _CHANNEL_NAME_INDEX.get(name)

    @classmethod
    def intra_routing_channels(
        cls,
    ) -> tuple[sfN, ...]:
        """Intra routing channels in stable display order."""
        return (cls.Wi, cls.Ni, cls.Ei, cls.Si)

    @classmethod
    def extra_routing_channels(
        cls,
    ) -> tuple[sfN, ...]:
        """Extra routing channels in stable display order."""
        return (cls.We, cls.Ne, cls.Ee, cls.Se)


# ---------------------------------------------------------------------------
# Mapping tables — defined after the class so members are fully resolved.
# ---------------------------------------------------------------------------

#: Internal geometry region keys for regions that have them.
_REGION_KEYS: dict[sfN, str] = {
    # intra routing channels
    sfN.Wi: "west/intra_routing_longitude",
    sfN.Ei: "east/intra_routing_longitude",
    sfN.Ni: "north/intra_routing_latitude",
    sfN.Si: "south/intra_routing_latitude",
    # extra routing channels
    sfN.We: "west/extra_routing_longitude",
    sfN.Ee: "east/extra_routing_longitude",
    sfN.Ne: "north/extra_routing_latitude",
    sfN.Se: "south/extra_routing_latitude",
    # terminals
    sfN.Wt: "west/chip_terminal",
    sfN.Et: "east/chip_terminal",
    sfN.Nt: "north/chip_terminal",
    sfN.St: "south/chip_terminal",
    # intra fans
    sfN.Wfi: "west/intra_routing_fan_in_out",
    sfN.Efi: "east/intra_routing_fan_in_out",
    # extra fans (keys defined; geometry builder support pending)
    sfN.Wfe: "west/extra_routing_fan_in_out",
    sfN.Efe: "east/extra_routing_fan_in_out",
    sfN.Nfi: "north/intra_routing_fan_in_out",
    sfN.Sfi: "south/intra_routing_fan_in_out",
    sfN.Nfe: "north/extra_routing_fan_in_out",
    sfN.Sfe: "south/extra_routing_fan_in_out",
}

#: Reverse index: geometry key → sfN member.
_REGION_KEY_INDEX: dict[str, sfN] = {v: k for k, v in _REGION_KEYS.items()}

_REGION_SYMBOLS: dict[sfN, str] = {
    sfN.Wi: "🭲",
    sfN.Ei: "🭵",
    sfN.Ni: "🭷",
    sfN.Si: "🭺",
    sfN.We: "▕",
    sfN.Ee: "▏",
    sfN.Ne: "▔",
    sfN.Se: "▁",
    sfN.Wt: "░",
    sfN.Et: "▒",
    sfN.Nt: "▓",
    sfN.St: "█",
    sfN.Wfi: "🬤",
    sfN.Efi: "🮥",
    sfN.Nfi: "🮧",
    sfN.Sfi: "🮪",
    sfN.Wfe: "🬗",
    sfN.Efe: "🮤",
    sfN.Nfe: "🮦",
    sfN.Sfe: "🮭",
}

#: Symbolic path tokens used by the solver and path parsers.
#: Routing channels use their canonical channel name; fans use
#: their compact token.
_CHANNEL_NAMES: dict[sfN, str] = {
    sfN.Wi: "wLong",
    sfN.Ei: "eLong",
    sfN.Ni: "nLat",
    sfN.Si: "sLat",
    sfN.We: "xwLong",
    sfN.Ee: "xeLong",
    sfN.Ne: "xnLat",
    sfN.Se: "xsLat",
    sfN.Wfi: "wf",
    sfN.Efi: "ef",
    sfN.Nfi: "nf",
    sfN.Sfi: "sf",
}

#: Reverse index: channel token → sfN member.
_CHANNEL_NAME_INDEX: dict[str, sfN] = {v: k for k, v in _CHANNEL_NAMES.items()}

"""Layout Joiner: Exhaustive 16-Character Geometric Algebra (RPN Naming).

This module implements a rigorous bitmask-driven algebraic truth table for
topological character merging. It distinguishes between "terminating" intent
(stubs) and "pass-through" intent (full lines).

The engine treats every character as a set of 4 directional vectors:
N=1 (↑), S=2 (↓), E=4 (→), W=8 (←).

All characters are processed through an exhaustive 16x16 geometric algebra:

  ┌───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┐
  │   │   │ ╵ │ ╷ │ │ │ ╶ │ └ │ ┌ │ ├ │ ╴ │ ┘ │ ┐ │ ┤ │ ─ │ ┴ │ ┬ │ ┼ │
  ├───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┤
  │   │   │ ╵ │ ╷ │ │ │ ╶ │ └ │ ┌ │ ├ │ ╴ │ ┘ │ ┐ │ ┤ │ ─ │ ┴ │ ┬ │ ┼ │
  │ ╵ │ ╵ │ ╵ │ │ │ │ │ └ │ └ │ ├ │ ├ │ ┘ │ ┘ │ ┤ │ ┤ │ ┴ │ ┴ │ ┼ │ ┼ │
  │ ╷ │ ╷ │ │ │ ╷ │ │ │ ┌ │ ├ │ ┌ │ ├ │ ┐ │ ┤ │ ┐ │ ┤ │ ┬ │ ┼ │ ┬ │ ┼ │
  │ │ │ │ │ │ │ │ │ │ │ ├ │ ├ │ ├ │ ├ │ ┤ │ ┤ │ ┤ │ ┤ │ ┼ │ ┼ │ ┼ │ ┼ │
  │ ╶ │ ╶ │ └ │ ┌ │ ├ │ ╶ │ └ │ ┌ │ ├ │ ─ │ ┴ │ ┬ │ ┼ │ ─ │ ┴ │ ┬ │ ┼ │
  │ └ │ └ │ └ │ ├ │ ├ │ └ │ └ │ ├ │ ├ │ ┴ │ ┴ │ ┼ │ ┼ │ ┴ │ ┴ │ ┼ │ ┼ │
  │ ┌ │ ┌ │ ├ │ ┌ │ ├ │ ┌ │ ├ │ ┌ │ ├ │ ┬ │ ┼ │ ┬ │ ┼ │ ┬ │ ┼ │ ┬ │ ┼ │
  │ ├ │ ├ │ ├ │ ├ │ ├ │ ├ │ ├ │ ├ │ ├ │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │
  │ ╴ │ ╴ │ ┘ │ ┐ │ ┤ │ ─ │ ┴ │ ┬ │ ┼ │ ╴ │ ┘ │ ┐ │ ┤ │ ─ │ ┴ │ ┬ │ ┼ │
  │ ┘ │ ┘ │ ┘ │ ┤ │ ┤ │ ┴ │ ┴ │ ┼ │ ┼ │ ┘ │ ┘ │ ┤ │ ┤ │ ┴ │ ┴ │ ┼ │ ┼ │
  │ ┐ │ ┐ │ ┤ │ ┐ │ ┤ │ ┬ │ ┼ │ ┬ │ ┼ │ ┐ │ ┤ │ ┐ │ ┤ │ ┬ │ ┼ │ ┬ │ ┼ │
  │ ┤ │ ┤ │ ┤ │ ┤ │ ┤ │ ┼ │ ┼ │ ┼ │ ┼ │ ┤ │ ┤ │ ┤ │ ┤ │ ┼ │ ┼ │ ┼ │ ┼ │
  │ ─ │ ─ │ ┴ │ ┬ │ ┼ │ ─ │ ┴ │ ┬ │ ┼ │ ─ │ ┴ │ ┬ │ ┼ │ ─ │ ┴ │ ┬ │ ┼ │
  │ ┴ │ ┴ │ ┴ │ ┼ │ ┼ │ ┴ │ ┴ │ ┼ │ ┼ │ ┴ │ ┴ │ ┼ │ ┼ │ ┴ │ ┴ │ ┼ │ ┼ │
  │ ┬ │ ┬ │ ┼ │ ┬ │ ┼ │ ┬ │ ┼ │ ┬ │ ┼ │ ┬ │ ┼ │ ┬ │ ┼ │ ┬ │ ┼ │ ┬ │ ┼ │
  │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │ ┼ │
  └───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───┘

Dependencies:
    - signalflow.legacy.config for Wire tokens
    - All code should be run through 'ruff' for linting and formatting.
"""

from __future__ import annotations

# Standard library
from typing import Final

# Local
from signalflow.legacy.config import Wire


class LayoutJoiner:
    """Centralized brain for geometric vector-based character merging.

    Implements a bitmask-driven algebra where any two glyphs or intents can
    be summed to produce the mathematically correct resulting character.
    Intermediate results use atomic stubs, while final output is promoted
    to full lines for visual continuity.

    Attributes:
        N: Bitmask for North vector (1).
        S: Bitmask for South vector (2).
        E: Bitmask for East vector (4).
        W: Bitmask for West vector (8).
        DV: Bitmask for Double Vertical module wall (16).
        DH: Bitmask for Double Horizontal module wall (32).
    """

    # Directional Bitmask Intent (Atomic Vectors)
    N: Final[int] = 1  # North (Upward)
    S: Final[int] = 2  # South (Downward)
    E: Final[int] = 4  # East (Rightward)
    W: Final[int] = 8  # West (Leftward)
    DV: Final[int] = 16  # Double Vertical (Module)
    DH: Final[int] = 32  # Double Horizontal (Module)

    # Mask to Character Mapping (Topological Truth)
    # Maps every bitmask permutation (0-63) to its canonical character.
    # Intermediate stubs are preserved here for mathematical accuracy.
    MASK_TO_CHAR: Final[dict[int, str]] = {
        0: " ",
        N: "╵",
        S: "╷",
        E: "╶",
        W: "╴",
        N | S: "│",
        E | W: "─",
        N | E: "└",
        S | E: "┌",
        N | W: "┘",
        S | W: "┐",
        N | S | E: "├",
        N | S | W: "┤",
        N | E | W: "┴",
        S | E | W: "┬",
        N | S | E | W: "┼",
        # Double-line module crossings (Exhaustive Piercing Set)
        N | S | DV: "║",
        E | W | DH: "═",
        # Piercings: Any combination of H-wire and V-DoubleWall = ╫
        N | S | E | DV: "╫",
        N | S | W | DV: "╫",
        N | S | E | W | DV: "╫",
        # Piercings: Any combination of V-wire and H-DoubleWall = ╪
        E | W | N | DH: "╪",
        E | W | S | DH: "╪",
        E | W | N | S | DH: "╪",
    }

    # Display Promotion Table (Visual continuity for user)
    # Maps single-vector stubs to their full-line visual counterparts.
    PROMOTION: Final[dict[str, str]] = {"╵": "│", "╷": "│", "╶": "─", "╴": "─"}

    @classmethod
    def glyph_merge(
        cls,
        currentChar: str,
        incomingChar: str | None = None,
        incomingMask: int | None = None,
    ) -> str:
        """Merge two topological elements using bitmask summation.

        Applies the geometric algebra by OR-ing the directional vectors of the
        current character and the incoming intent (either a char or a specific
        mask).

        Args:
            currentChar: The glyph already present on the canvas.
            incomingChar: Optional new glyph to lay (provides full intent).
            incomingMask: Optional specific directional intent vector bitmask.

        Returns:
            The resulting canonical glyph in its intermediate (potentially stub)
            form.

        Example:
            >>> LayoutJoiner.glyph_merge('─', incomingMask=LayoutJoiner.S)
            '┬'
        """
        # Normalize and get existing mask
        c1: str = cls.token_normalize(currentChar)
        m1: int = cls.charToMask_get(c1)

        # Sovereignty Check: If current is alphanumeric/sovereign, it blocks.
        if m1 == 0 and c1 != " ":
            return currentChar

        # Determine Incoming Intent Vector
        m2: int = 0
        if incomingMask is not None:
            m2 = incomingMask
        elif incomingChar is not None:
            c2: str = cls.token_normalize(incomingChar)
            m2 = cls.charToMask_get(c2)
            # If incoming is alphanumeric/sovereign, it overwrites
            if m2 == 0 and incomingChar != " ":
                return incomingChar

        # Perform Geometric Sum (Topological Algebra)
        finalMask: int = m1 | m2

        # Lookup intermediate result (may be a stub)
        res: str = cls.MASK_TO_CHAR.get(finalMask, " ")
        if res == " " and (incomingChar or currentChar):
            return incomingChar if incomingChar else currentChar
        return res

    @classmethod
    def character_promote(cls, ch: str) -> str:
        """Promote intermediate stubs to full lines for visual continuity.

        Args:
            ch: The intermediate character (possibly a stub like '╵').

        Returns:
            The visually continuous character (e.g., '│').
        """
        return cls.PROMOTION.get(ch, ch)

    @classmethod
    def charToMask_get(cls, ch: str) -> int:
        """Map any character or token to its directional bitmask.

        Args:
            ch: The character glyph or semantic token to map.

        Returns:
            The integer bitmask representing the directional vectors.
        """
        for mask, char in cls.MASK_TO_CHAR.items():
            if char == ch:
                return mask
        return 0

    @staticmethod
    def token_normalize(ch: str) -> str:
        """Standardize semantic Wire tokens to their base glyphs.

        Args:
            ch: The character or token to normalize.

        Returns:
            The normalized literal character glyph.
        """
        if ch in (Wire.RT, Wire.LT):
            return "─"
        if ch in (Wire.DN, Wire.UP):
            return "│"
        if ch in (Wire.UR, Wire.LD):
            return "┌"
        if ch in (Wire.RD, Wire.UL):
            return "┐"
        if ch in (Wire.DR, Wire.LU):
            return "└"
        if ch in (Wire.DL, Wire.RU):
            return "┘"
        return ch

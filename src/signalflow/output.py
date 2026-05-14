"""Output format converters for SignalFlow ASCII diagrams.

This module provides functions to convert ASCII art diagrams to various
image formats (SVG, PNG, JPG) for use in presentations and publications.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

OutputFormat = Literal["txt", "svg", "png", "jpg", "jpeg"]


@dataclass
class ColorScheme:
    """Color scheme for output rendering.

    Attributes:
        background: Background color (hex, rgb, or CSS color name).
        foreground: Foreground/text color (hex, rgb, or CSS color name).
    """
    background: str = "white"
    foreground: str = "black"

    @classmethod
    def fromPreset(cls, preset: str) -> "ColorScheme":
        """Create a color scheme from a preset name.

        Args:
            preset: Preset name (light, dark, blue, solarized-light, solarized-dark).

        Returns:
            ColorScheme instance.

        Raises:
            ValueError: If preset name is unknown.
        """
        presets = {
            "light": cls(background="white", foreground="black"),
            "dark": cls(background="#1e1e1e", foreground="#d4d4d4"),
            "blue": cls(background="#0d1117", foreground="#c9d1d9"),
            "solarized-light": cls(background="#fdf6e3", foreground="#657b83"),
            "solarized-dark": cls(background="#002b36", foreground="#839496"),
            "gruvbox-light": cls(background="#fbf1c7", foreground="#3c3836"),
            "gruvbox-dark": cls(background="#282828", foreground="#ebdbb2"),
        }
        if preset not in presets:
            raise ValueError(
                f"Unknown color preset: {preset}. "
                f"Available: {', '.join(presets.keys())}"
            )
        return presets[preset]




def format_fromExtension(filename: str) -> OutputFormat:
    """Infer output format from file extension.

    Args:
        filename: Output filename with extension.

    Returns:
        Output format (txt, svg, png, jpg, jpeg).

    Raises:
        ValueError: If extension is not supported.
    """
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in ("txt", "svg", "png", "jpg", "jpeg"):
        raise ValueError(
            f"Unsupported output format: .{ext}. "
            f"Supported: .txt, .svg, .png, .jpg, .jpeg"
        )
    return ext  # type: ignore


def ascii_toSVG(
    lines: list[str],
    title: str = "",
    colorScheme: ColorScheme | None = None,
) -> str:
    """Convert ASCII art to SVG.

    Args:
        lines: ASCII art lines to convert.
        title: Optional title for the SVG document.
        colorScheme: Color scheme for rendering. Defaults to light theme.

    Returns:
        SVG document as a string.
    """
    if colorScheme is None:
        colorScheme = ColorScheme()
    # Calculate dimensions
    maxWidth = max(len(line) for line in lines) if lines else 80
    height = len(lines)

    # SVG configuration for monospace rendering
    charWidth = 8.4  # Width of each character in pixels
    charHeight = 16  # Height of each character in pixels
    padding = 20

    svgWidth = maxWidth * charWidth + padding * 2
    svgHeight = height * charHeight + padding * 2

    # Escape XML entities
    def escape(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    # Build SVG
    svg_parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        f'<svg width="{svgWidth}" height="{svgHeight}" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'version="1.1">',
    ]

    if title:
        svg_parts.append(f"  <title>{escape(title)}</title>")

    # Background
    svg_parts.extend([
        f'  <rect width="{svgWidth}" height="{svgHeight}" fill="{colorScheme.background}"/>',
        '  <style>',
        '    text {',
        '      font-family: "Courier New", "DejaVu Sans Mono", monospace;',
        f'      font-size: {charHeight - 2}px;',
        f'      fill: {colorScheme.foreground};',
        '      white-space: pre;',
        '    }',
        '  </style>',
        f'  <text x="{padding}" y="{padding + charHeight * 0.8}">',
    ])

    # Add each line as a tspan
    for idx, line in enumerate(lines):
        y_offset = idx * charHeight
        escaped_line = escape(line)
        svg_parts.append(
            f'    <tspan x="{padding}" dy="{charHeight if idx > 0 else 0}">'
            f'{escaped_line}</tspan>'
        )

    svg_parts.extend([
        '  </text>',
        '</svg>',
    ])

    return "\n".join(svg_parts)


def ascii_toPNG(
    lines: list[str],
    outputPath: str,
    title: str = "",
    colorScheme: ColorScheme | None = None,
    fontSize: int = 12,
) -> None:
    """Convert ASCII art to PNG image.

    Requires Pillow (PIL) to be installed.

    Args:
        lines: ASCII art lines to convert.
        outputPath: Path to write PNG file.
        title: Optional title (unused for PNG, kept for API consistency).
        colorScheme: Color scheme for rendering. Defaults to light theme.
        fontSize: Font size in points (default: 12). Larger = higher quality.

    Raises:
        ImportError: If Pillow is not installed.
    """
    if colorScheme is None:
        colorScheme = ColorScheme()
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as e:
        raise ImportError(
            "PNG output requires Pillow. Install with: pip install Pillow"
        ) from e

    # Configuration (fontSize now comes from parameter)
    charWidth = fontSize * 0.6  # Approximate monospace width
    charHeight = fontSize * 1.2
    padding = 20

    # Calculate dimensions
    maxWidth = max(len(line) for line in lines) if lines else 80
    height = len(lines)

    imgWidth = int(maxWidth * charWidth + padding * 2)
    imgHeight = int(height * charHeight + padding * 2)

    # Create image
    img = Image.new("RGB", (imgWidth, imgHeight), color=colorScheme.background)
    draw = ImageDraw.Draw(img)

    # Try to load a monospace font
    try:
        # Try common monospace fonts
        for fontName in [
            "DejaVuSansMono.ttf",
            "CousineMonoRegular.ttf",
            "LiberationMono-Regular.ttf",
            "FreeMono.ttf",
            "cour.ttf",  # Windows Courier New
        ]:
            try:
                font = ImageFont.truetype(fontName, fontSize)
                break
            except OSError:
                continue
        else:
            # Fallback to default font
            font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    # Draw text
    y = padding
    for line in lines:
        draw.text((padding, y), line, fill=colorScheme.foreground, font=font)
        y += charHeight

    # Save
    img.save(outputPath)


def output_write(
    lines: list[str],
    outputPath: str | None,
    title: str = "",
    colorScheme: ColorScheme | None = None,
    fontSize: int = 12,
) -> None:
    """Write SignalFlow output to file in the appropriate format.

    The output format is inferred from the file extension:
    - .txt: Plain text ASCII
    - .svg: Scalable Vector Graphics
    - .png: PNG image (requires Pillow)
    - .jpg/.jpeg: JPEG image (requires Pillow)

    If outputPath is None, writes ASCII to stdout.

    Args:
        lines: ASCII art lines to write.
        outputPath: Output file path, or None for stdout.
        title: Optional title for the document.
        colorScheme: Color scheme for rendering. Defaults to light theme.
        fontSize: Font size for PNG/JPEG output (default: 12).

    Raises:
        ValueError: If file extension is not supported.
        ImportError: If image format requires missing dependency.
    """
    if outputPath is None:
        # Write to stdout
        for line in lines:
            print(line)
        return

    outputFormat = format_fromExtension(outputPath)

    if outputFormat == "txt":
        # Write plain text
        with open(outputPath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            f.write("\n")
        print(f"Wrote ASCII to {outputPath}", file=sys.stderr)

    elif outputFormat == "svg":
        # Convert to SVG
        svg_content = ascii_toSVG(lines, title, colorScheme)
        with open(outputPath, "w", encoding="utf-8") as f:
            f.write(svg_content)
        print(f"Wrote SVG to {outputPath}", file=sys.stderr)

    elif outputFormat in ("png", "jpg", "jpeg"):
        # Convert to raster image
        ascii_toPNG(lines, outputPath, title, colorScheme, fontSize)
        print(f"Wrote {outputFormat.upper()} to {outputPath}", file=sys.stderr)

    else:
        raise ValueError(f"Unsupported format: {outputFormat}")

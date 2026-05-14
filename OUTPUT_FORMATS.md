# SignalFlow Output Formats

SignalFlow can now export diagrams in multiple formats for use in presentations, papers, and documentation.

## Usage

```bash
# ASCII to stdout (default)
signalflow examples/hub.yaml

# Save ASCII to text file
signalflow examples/hub.yaml -o diagram.txt

# Export to SVG (scalable, recommended for presentations)
signalflow examples/hub.yaml -o diagram.svg

# Export to PNG (requires Pillow)
signalflow examples/hub.yaml -o diagram.png

# Export to JPEG (requires Pillow)
signalflow examples/hub.yaml -o diagram.jpg

# Export with dark theme
signalflow examples/hub.yaml -o diagram.svg --color-preset dark

# Export with custom colors
signalflow examples/hub.yaml -o diagram.png --colors "#1e1e1e,#d4d4d4"

# Export with higher quality (larger font)
signalflow examples/hub.yaml -o diagram.png --font-size 20

# Combine options for presentation-ready output
signalflow examples/hub.yaml -o diagram.png --color-preset dark --font-size 18
```

## Format Details

### ASCII (.txt)
- **Use for:** Version control, command-line viewing, documentation
- **Pros:** Lightweight, diff-friendly, universal
- **Cons:** Not suitable for slides or publications
- **Dependencies:** None

### SVG (.svg)
- **Use for:** Presentations, web pages, printed materials
- **Pros:** Scalable, crisp at any resolution, small file size
- **Cons:** May need font adjustment in some viewers
- **Dependencies:** None (pure Python)
- **Recommended for:** Most use cases

### PNG (.png)
- **Use for:** Slide decks (PowerPoint, Keynote), raster graphics
- **Pros:** Universal compatibility, embedded fonts
- **Cons:** Fixed resolution, larger files
- **Dependencies:** Pillow (included in requirements)

### JPEG (.jpg, .jpeg)
- **Use for:** Photos, web optimization
- **Pros:** Compressed, smaller files
- **Cons:** Lossy compression, not ideal for text/diagrams
- **Dependencies:** Pillow (included in requirements)
- **Note:** PNG is generally better for diagrams

## Installing Dependencies

Pillow is included in the project dependencies and will be installed automatically when you install SignalFlow:

```bash
# Install from source
pip install -e .

# Or with uv
uv sync
```

If you need to install Pillow manually:
```bash
pip install Pillow>=12.2.0
```

## Color Schemes

SignalFlow supports customizable color schemes for SVG and PNG/JPEG output.

### Preset Color Schemes

Use `--color-preset` to select from built-in themes:

| Preset | Background | Foreground | Best For |
|--------|------------|------------|----------|
| `light` (default) | White | Black | Light backgrounds, printing |
| `dark` | #1e1e1e | #d4d4d4 | Dark mode presentations |
| `blue` | #0d1117 | #c9d1d9 | GitHub dark theme |
| `solarized-light` | #fdf6e3 | #657b83 | Solarized light |
| `solarized-dark` | #002b36 | #839496 | Solarized dark |
| `gruvbox-light` | #fbf1c7 | #3c3836 | Gruvbox light |
| `gruvbox-dark` | #282828 | #ebdbb2 | Gruvbox dark |

**Examples:**
```bash
# Dark theme for presentations
signalflow examples/hub.yaml -o diagram.svg --color-preset dark

# Solarized dark for terminal-like aesthetics
signalflow examples/hub.yaml -o diagram.png --color-preset solarized-dark

# Gruvbox for warm, retro look
signalflow examples/hub.yaml -o diagram.svg --color-preset gruvbox-dark
```

### Custom Colors

Use `--colors` to specify custom background and foreground colors:

```bash
# CSS color names
signalflow examples/hub.yaml -o diagram.svg --colors "lightblue,darkblue"

# Hex colors
signalflow examples/hub.yaml -o diagram.png --colors "#1e1e1e,#d4d4d4"

# Mixed formats
signalflow examples/hub.yaml -o diagram.svg --colors "white,#333333"
```

**Format:** `--colors "background,foreground"`

Colors can be:
- CSS color names (e.g., `white`, `black`, `lightblue`)
- Hex values (e.g., `#1e1e1e`, `#d4d4d4`)
- RGB values (e.g., `rgb(30, 30, 30)`)

### Color Scheme Tips

1. **For presentations:** Use high contrast (e.g., `dark` or `light`)
2. **For printed materials:** Use `light` preset
3. **For dark-themed slides:** Use `dark` or `blue` presets
4. **For accessibility:** Ensure sufficient contrast between background and foreground

## Image Quality and Anti-Aliasing

### Font Size Control

Control PNG/JPEG image quality using the `--font-size` option:

```bash
# Default quality (12pt font)
signalflow examples/hub.yaml -o diagram.png

# Higher quality for presentations (18-24pt)
signalflow examples/hub.yaml -o diagram.png --font-size 20

# Smaller for documentation (10-14pt)
signalflow examples/hub.yaml -o diagram.png --font-size 10
```

**Font Size Guidelines:**
- **10-14pt**: Documentation, embedded diagrams, web pages
- **12pt (default)**: General purpose, good balance of size/quality
- **16-20pt**: Presentations, slides, posters
- **24pt+**: Large format displays, projection

### Anti-Aliasing

**PNG/JPEG:** Anti-aliasing is **automatically enabled** when using TrueType fonts (DejaVu Sans Mono, Liberation Mono, etc.). Pillow renders smooth, high-quality text by default.

**SVG:** Anti-aliasing is handled by the SVG viewer/browser. Modern browsers (Chrome, Firefox, Safari) provide excellent anti-aliased rendering.

**Tips for best quality:**
1. Use larger `--font-size` values (16-24) for presentations
2. SVG format is recommended for maximum quality (scales infinitely)
3. PNG works best when you need embedded fonts and fixed resolution
4. For printing, use SVG or high `--font-size` PNG (20+)

## Examples

### Batch convert all presentation diagrams to SVG:
```bash
for yaml in examples/presentation/graph-space-*.yaml; do
    base=$(basename "$yaml" .yaml)
    signalflow "$yaml" -o "output/${base}.svg"
done
```

### Generate both light and dark versions:
```bash
for yaml in examples/presentation/graph-space-*.yaml; do
    base=$(basename "$yaml" .yaml)
    signalflow "$yaml" -o "output/${base}-light.svg" --color-preset light
    signalflow "$yaml" -o "output/${base}-dark.svg" --color-preset dark
done
```

### Quick preview workflow:
```bash
# Generate, view in browser
signalflow examples/hub.yaml -o /tmp/preview.svg
open /tmp/preview.svg  # macOS
xdg-open /tmp/preview.svg  # Linux
```

### For LaTeX papers:
```bash
# Generate SVG, include in LaTeX
signalflow examples/hub.yaml -o figures/hub-diagram.svg

# In your .tex file:
# \usepackage{svg}
# \includesvg{figures/hub-diagram}
```

## Technical Details

### SVG Generation
- Uses monospace font rendering with `<text>` elements
- Preserves box-drawing characters (─│┌┐└┘├┤┬┴┼)
- Embedded fonts for maximum compatibility
- Configurable character spacing (8.4px width, 16px height)

### PNG/JPEG Generation
- Renders text using PIL/Pillow
- Attempts to find system monospace fonts
- Falls back to default font if none found
- Font size: 12pt (configurable in code)
- Resolution: Based on character dimensions

## Font Recommendations

For best results with SVG output, ensure your system has these fonts:
- **Primary:** Courier New, DejaVu Sans Mono
- **Fallbacks:** Liberation Mono, FreeMono, Consolas

For PNG output, Pillow will automatically use the best available monospace font.

## Troubleshooting

### "ImportError: PNG output requires Pillow"
Install Pillow: `pip install Pillow`

### "Unsupported output format"
Check your file extension. Supported: `.txt`, `.svg`, `.png`, `.jpg`, `.jpeg`

### SVG looks wrong in browser
Some browsers may not render box-drawing characters correctly. Try:
1. Exporting to PNG instead
2. Using a different browser (Chrome/Firefox recommended)
3. Embedding the SVG in an HTML file with explicit font declarations

### PNG text is blurry
The default font size is 12pt. You can modify `src/signalflow/output.py` and increase `fontSize` for higher resolution.

## API Usage

You can also use the output functions programmatically:

```python
from signalflow.output import ascii_toSVG, ascii_toPNG, output_write

# Convert ASCII lines to SVG string
svg_content = ascii_toSVG(ascii_lines, title="My Diagram")

# Write to file with automatic format detection
output_write(ascii_lines, "diagram.svg", title="My Diagram")

# Direct PNG generation
ascii_toPNG(ascii_lines, "diagram.png", title="My Diagram")
```

## Comparison with Other Tools

| Tool | Format | Scalable | Dependencies | Best For |
|------|--------|----------|--------------|----------|
| **SignalFlow SVG** | Vector | Yes | None | Presentations, web |
| **SignalFlow PNG** | Raster | No | Pillow | Slide decks |
| Carbon | Raster | No | Browser | Code snippets |
| asciitosvg | Vector | Yes | Go | General ASCII art |
| ditaa | Raster | No | Java | Box diagrams |

## Future Enhancements

Potential additions for future versions:
- `--font-size` option for PNG rendering
- `--scale` option for higher-resolution output
- PDF export via reportlab
- Custom color schemes for SVG
- Transparent backgrounds

## Contributing

To add support for new output formats, edit `src/signalflow/output.py` and:
1. Add the format to the `OutputFormat` type
2. Implement a converter function
3. Add a case in `output_write()`
4. Update this documentation
5. Add tests

## See Also

- `examples/presentation/` - Example diagrams for presentations
- `docs/yaml_syntax.adoc` - SignalFlow YAML format reference
- `README.md` - Main SignalFlow documentation

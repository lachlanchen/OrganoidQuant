# Illustrator SVG Tile Export

This tool extracts embedded microscopy tiles from Adobe Illustrator SVG figure layouts and exports them into a clear folder structure.

## What it does
- reads embedded `<image>` tiles from an SVG
- recovers panel/grid structure from tile coordinates
- assigns row/column labels from a small JSON config
- writes raw standalone tile PNGs
- writes `manifest.json` and `manifest.csv`
- builds stitched contact sheets for panel `A` and panel `B`

## Figure 5 export
```bash
analysis-tools/illustrator_svg_tile_export/export_illustrator_svg_tiles.py \
  analysis-tools/illustrator_svg_tile_export/figure5_y27632_config.json
```

## Output layout
Example output root:
`analysis-output/figure_subfigure_export/figure5_y27632`

Contains:
- `panel_A/`
- `panel_B/`
- `panel_A_contact_sheet.png`
- `panel_B_contact_sheet.png`
- `manifest.json`
- `manifest.csv`

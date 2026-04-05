# DEO Segmentation Method TeX Note

This folder contains a self-contained LaTeX source note that documents:

- the DEO segmentation algorithm
- the hybrid signal / support-map construction
- multiscale Cellpose with signal-based large-mass recovery
- candidate scoring and merge logic
- all current downstream metrics in mathematical form

Main file:

- `main.tex`

Suggested build command on a machine with TeX installed:

```bash
cd references/deo_segmentation_metric_method_tex
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```

Or with `latexmk`:

```bash
cd references/deo_segmentation_metric_method_tex
latexmk -pdf main.tex
```

This WSL environment currently does not have a TeX engine installed, so the PDF was not compiled here.

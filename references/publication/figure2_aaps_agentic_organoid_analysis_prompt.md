# Figure 2 Concept: Agentic Analysis of Organoid Images with AAPS

Date: 2026-04-29

## User Requirements Captured

The intended Figure 2 should support the paper story:

**Agentic Analysis of organoids with AAPS.**

The core message is that pure agent behavior is difficult to control directly. For biomedical image analysis, the agent needs a structured harness because image quality, imaging conditions, magnification, field content, object scale, and experiment design vary across datasets. The same segmentation or quantification method may not apply to every dataset.

The figure should communicate that AAPS provides an agentic but controlled analysis pipeline with dataset management, image quality control, segmentation method selection, quantification design, database maintenance, plotting, and conclusion generation.

Key required concepts:

1. **Dataset and metadata management**

AAPS should automatically manage datasets from imaging capture, maintain a database, store metadata, and preserve the experiment design.

2. **Quality control and image priors before segmentation**

AAPS should perform quality control and infer image priors for later segmentation. It should choose the proper segmentation strategy based on magnification, image quality, organoid size prior, brightfield/darkfield modality, object distribution, and expected count prior. The pipeline can use a vision model to read and reason about images inside the AAPS workflow.

3. **Flexible segmentation methods**

AAPS should support flexible segmentation methods, including Cellpose, thresholding, multiscale segmentation, and other task-specific methods. For difficult segmentation or specific features that are hard to quantify directly, the pipeline may also use an image generation model to generate segmentation annotations or identify hard-to-quantify visual features.

4. **Agent-designed quantification metrics**

AAPS should use an agent to design quantification metrics based on the experiment design, then run the quantification. Example metric families include growth, differentiation, fusion, morphology, darkness, area, perimeter, centrality, and edge-based structure.

5. **Database, plots, and conclusions**

AAPS should maintain a database of metrics and outputs, generate plots, and produce experiment-level conclusions.

## Figure 2 Design Goal

Create a modern, clear, Nature-style workflow figure that explains why a controlled agent harness is needed for biomedical organoid image analysis and how AAPS converts heterogeneous microscopy data into quality-controlled segmentation, metrics, plots, and conclusions.

The figure should feel like a serious biomedical methods figure, not a marketing diagram.

## Recommended Figure Structure

Suggested panel layout:

- **Panel A: Why uncontrolled agents are risky**
  - Show variable organoid microscopy images entering an unconstrained AI agent cloud.
  - Indicate possible failure modes: inconsistent segmentation, wrong metric choice, poor QC, and weak reproducibility.
  - Keep this compact, as the purpose is to motivate AAPS.

- **Panel B: AAPS as the harness**
  - Show AAPS as a structured control layer around the agent.
  - Include guardrails/checkpoints: metadata, experiment design, QC, method routing, audit trail, database.

- **Panel C: Image-aware routing and segmentation**
  - Show a vision model reading images and extracting priors: magnification, modality, image quality, organoid size, density, and object counts.
  - Show routing to Cellpose, thresholding, multiscale segmentation, or image-generation-assisted annotation.

- **Panel D: Experiment-aware metric design**
  - Show the agent choosing metrics based on biological questions and experiment design.
  - Include growth, differentiation, fusion, darkness, area, perimeter, and centrality/edge metrics as examples.

- **Panel E: Database, plots, and conclusions**
  - Show structured database tables, metric plots, representative overlays, and concise conclusions.
  - Emphasize reproducible outputs and auditability.

## High-Quality Image Generation Prompt

Use this prompt for ChatGPT image generation or another image model:

```text
Create a publication-quality Figure 2 for a Nature-style biomedical methods paper.

Theme: "Agentic analysis of organoid images with AAPS". The figure should explain that pure AI-agent behavior is hard to control, so biomedical image analysis needs a structured harness that manages data, performs image quality control, routes segmentation methods, designs quantification metrics, maintains a database, generates plots, and produces conclusions.

Style: clean modern scientific workflow figure, editorial Nature Methods / Nature Biomedical Engineering aesthetic, white or very light warm-gray background, thin vector lines, rounded modular panels, subtle shadows, restrained color palette of deep slate, teal, muted blue, warm amber, and soft coral. Use crisp microscopy-inspired thumbnails and clean icons. Avoid cartoon characters, 3D glossy style, clutter, decorative gradients, and marketing-poster aesthetics.

Overall layout: horizontal left-to-right pipeline with five labeled panels A-E. Use a clear central backbone labelled "AAPS harness" that wraps around or controls an AI agent. The harness should look structured and auditable, with checkpoints and guardrails. Use minimal readable text only.

Panel A, Problem: show heterogeneous organoid microscopy inputs with different brightness, magnification, organoid size, density, and image quality. Show an unconstrained AI-agent cloud producing inconsistent outputs. Add small warning cues for "variable images", "method mismatch", and "uncontrolled agent behavior".

Panel B, Dataset and metadata management: show imaging capture feeding into a structured dataset registry. Include small symbols for metadata, experiment design, date, condition, replicate, magnification, and database table. Emphasize that AAPS automatically organizes data and preserves experiment context.

Panel C, Vision QC and segmentation routing: show a vision model inspecting microscopy images and extracting image priors: modality, quality, magnification, size prior, count prior, density, and distribution. Then show a routing switch selecting among Cellpose, thresholding, multiscale segmentation, and image-generation-assisted annotation for difficult cases. Show segmentation masks as colored organoid instances, with QC checkmarks.

Panel D, Agent-designed quantification: show the agent using experiment design to choose metrics. Include compact metric cards: growth, differentiation, fusion, darkness P90, area/perimeter, centrality, edge structure. Show formulas or small plot icons only if they remain clean and readable.

Panel E, Reproducible outputs and conclusions: show a database of per-organoid and per-image metrics, representative segmentation overlays, polished plots, and a short conclusion card. Emphasize audit trail, reproducibility, and biological interpretation.

Important visual details: organoids should look like brightfield microscopy structures with round/cystic or lobular morphology, dark cellular texture, and colored instance masks. Do not make pale hydrogel droplets look like organoids. Segmentation masks should be solid colored instances with different colors for adjacent organoids.

Text labels to include, if readable: "AAPS harness", "metadata", "QC", "image priors", "method routing", "segmentation", "metric design", "database", "plots", "conclusions". Keep text sparse and clean. Use panel labels A, B, C, D, E.

Composition: 16:9 landscape, high resolution, balanced whitespace, clear hierarchy, all panels aligned, figure suitable for a manuscript main figure. No title inside the figure except small panel labels and short workflow labels.
```

## Shorter Prompt Version

```text
Design a Nature-style biomedical methods Figure 2 titled conceptually "Agentic analysis of organoid images with AAPS". Show a five-panel left-to-right workflow: A heterogeneous organoid microscopy data and uncontrolled-agent failure risk; B AAPS harness for dataset registry, metadata, experiment design, and audit trail; C vision-model QC and image priors routing segmentation to Cellpose, thresholding, multiscale segmentation, or image-generation-assisted annotation; D agent-designed metrics for growth, differentiation, fusion, darkness, area, perimeter, centrality, and edge structure; E database, plots, segmentation overlays, and conclusions. Use clean vector scientific design, white background, teal/slate/amber accents, rounded panels, minimal readable text, solid colored organoid instance masks, no cartoon/marketing style, no clutter, 16:9 landscape, high resolution.
```

## Negative Prompt / Avoid

```text
Avoid cartoon people, robot mascots, cyberpunk style, glossy 3D, heavy gradients, fake unreadable paragraphs, crowded icons, decorative DNA helices unrelated to the workflow, exaggerated neon colors, unstructured flowcharts, and segmentation masks that are hollow, fragmented, merged, or assigned the same color to adjacent organoids.
```

## Notes for Manual Refinement

- If the image model renders text poorly, generate the figure with blank label boxes and add final text manually in Illustrator, Figma, Inkscape, or PowerPoint.
- Keep the figure as a workflow figure, not a graphical abstract.
- The main visual contrast should be: uncontrolled agent behavior versus controlled AAPS harness with QC, method routing, database, and reproducible outputs.

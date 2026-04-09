# PIBM 2026 Imaging-AI Background Note

Date: 2026-04-08
Repo: `/home/lachlan/ProjectsLFS/Zhengyu`

## Purpose

This note records the local background used to reframe the DEO abstract for PIBM 2026 toward:

- imaging / sensing
- computational image analysis
- AI-ready phenotyping
- diagnostic-oriented optical screening

The goal is not to invent new completed experiments. The goal is to reorganize the existing DEO story using the strongest imaging and computational signals already present in this repository and in the recent Codex drafting session.

## Session Context From SQLite

Two local Codex threads are directly relevant.

### 1. DEO structure / analysis thread

Source:

- `~/.codex/state_5.sqlite`
- thread id: `019cb73d-1886-7230-a003-ab61b2342a2f`

Key metadata recovered from SQLite:

- cwd: `/home/lachlan/ProjectsLFS/Zhengyu`
- model: `gpt-5.4`
- reasoning: `xhigh`
- first user message focused on:
  - the three major DEO experiments
  - summary TIFFs
  - structured markdown description of the experiment layout

Interpretation:

- this thread establishes that the current project is already organized as a multi-experiment imaging dataset rather than only a biology manuscript
- the data are naturally grouped into density, alginate, and Y-27632 conditions with longitudinal image panels and detailed special-day imaging panels

### 2. PIBM abstract drafting thread

Source:

- `~/.codex/state_5.sqlite`
- thread id: `019d65de-01d6-7010-96f5-632aa6171b40`

Key metadata recovered from SQLite:

- cwd: `/home/lachlan/ProjectsLFS/PIBM`
- model: `gpt-5.4`
- reasoning: `xhigh`
- first user message contains the PIBM 2026 call text
- the conference scope explicitly includes:
  - optical and imaging solutions for biology and medicine
  - AI for biophotonics

Interpretation:

- the abstract must read like an imaging / photonics paper first
- biology remains the specimen context, not the rhetorical center

## Repository Signals That Support An Imaging-First Reframe

The repository already contains a strong computational imaging backbone.

### 1. Quantitative brightfield analysis is already central

Relevant notes:

- `references-plots/derivatives/markdown/zhengyu_feedback_plot_optimization_2026-04-06.md`
- `references/deo_metric_catalog_growth_fusion_differentiation.md`
- `references/deo_segmentation_metric_method_tex/README.md`

What these notes show:

- the accepted production baseline is segmentation-first quantitative analysis
- the preferred readouts are image-derived metrics, not only manual visual description
- the project already uses:
  - segmentation-derived growth metrics
  - darkness metrics for differentiation-like morphology
  - roundness / curvature / irregularity metrics
  - edge-based fusion proxies

This supports language such as:

- quantitative brightfield imaging
- time-resolved image analysis
- image-derived phenotypes
- computational phenotyping

### 2. The project already has explicit optical feature engineering

Relevant note:

- `references/deo_metric_catalog_growth_fusion_differentiation.md`

Important repository concept:

- the saved `signal.png` is a hybrid brightfield-derived signal representation built from contrast enhancement, residual structure, and inverted grayscale support

Why this matters rhetorically:

- the work is not only "we looked at brightfield images"
- it already includes engineered optical representations for quantitative readout

This supports language such as:

- morphology sensing
- signal-based image representation
- image-derived biomarkers

### 3. Differentiation and fusion are already framed as imaging phenotypes

Relevant notes:

- `references/app65_differentiation_darkness_metrics.md`
- `references/app80_internal_edge_centrality_metric.md`

Key usable concepts:

- differentiation-like progression is quantified through darkness and wall/core structure
- fusion is quantified through edge redistribution from periphery toward the interior

This supports language such as:

- wall thickening and darkening phenotypes
- internal edge redistribution
- fusion-associated structural signatures
- image-resolved state transitions

### 4. The repository already contains AI-oriented organoid language

Relevant materials:

- `OrganoidAgent/publication/main.tex`
- `OrganoidAgent/references/AI Agents for Multimodal Organoid Analysis and Experimentation.md`
- `api-tests/`
- `analysis-tools/`

What these show:

- high-content microscopy
- multimodal organoid analysis
- segmentation, tracking, and phenotyping
- AI-assisted or agent-assisted image analysis
- computational triage of organoid datasets

This supports abstract language such as:

- AI-ready phenotyping
- computational screening
- machine-learning-based biomarker extraction
- multimodal optical phenotyping

## What To Borrow From The Optica Paper

Local paper used for inspiration:

- `/home/lachlan/Downloads/optica-13-4-587.pdf`

Useful structural lessons from that paper:

1. Start from a sensing bottleneck, not from specimen biology.
2. Present a low-complexity but computationally enhanced optical framework.
3. Make the algorithmic or analytic contribution explicit.
4. End with why the system is broadly useful for future imaging applications.

For the DEO abstract, the transferable writing pattern is:

- problem:
  - heterogeneous culture limits reproducible optical readout and automated analysis
- method:
  - confined microdroplet geometry plus longitudinal brightfield imaging
- computational contribution:
  - segmentation-derived and signal-derived phenotypes quantify growth, wall thickening, darkening, and fusion
- future value:
  - AI-assisted phenotyping, multimodal sensing, hyperspectral integration

What should not be borrowed:

- do not imply event cameras or hyperspectral acquisition were already used in this DEO study
- do not claim real-time autonomous diagnosis if it was not performed

## Recommended Framing Shift

The old framing was too close to:

- a biology paper about density, alginate, and ROCK inhibition

The stronger PIBM framing is:

- a quantitative brightfield imaging platform for organoid morphodynamics
- with computational phenotyping under controlled perturbations
- and a clear path to AI-assisted and multimodal optical analysis

That means the abstract should:

- foreground:
  - imaging compatibility
  - time-resolved image analysis
  - quantitative morphology sensing
  - computational phenotyping
  - image-derived biomarkers
  - AI-ready analysis
- compress:
  - exact wet-lab manipulation details
  - reagent-specific storytelling
  - overly biological explanation of each condition

## Writing Rules For The Next Abstract Version

### Do

- present DEOs as an optically accessible microdroplet platform
- describe the results as image phenotypes and computationally resolved state changes
- mention segmentation-derived and signal-derived metrics
- position AI as:
  - AI-ready
  - AI-assisted
  - future machine-learning biomarker extraction
- mention hyperspectral imaging only as future integration

### Do Not

- claim completed AI diagnosis
- claim completed hyperspectral experiments
- let alginate or Y-27632 dominate the rhetorical center
- make the abstract read like a pure wet-lab optimization study

## Recommended One-Sentence Positioning

If the abstract needs a single anchor sentence, the best local framing is:

`We present droplet-engineered organoids as a standardized brightfield imaging platform in which controlled perturbations generate computationally separable morphological states for AI-ready optical phenotyping.`

## Main Source Files Used For This Reframe

- `references-plots/derivatives/markdown/zhengyu_feedback_plot_optimization_2026-04-06.md`
- `references/app65_differentiation_darkness_metrics.md`
- `references/app80_internal_edge_centrality_metric.md`
- `references/deo_metric_catalog_growth_fusion_differentiation.md`
- `references/deo_segmentation_metric_method_tex/README.md`
- `OrganoidAgent/publication/main.tex`
- `OrganoidAgent/references/AI Agents for Multimodal Organoid Analysis and Experimentation.md`
- `~/.codex/state_5.sqlite`
- `/home/lachlan/Downloads/optica-13-4-587.pdf`

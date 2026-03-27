# Thesis Notes: DEO Chapter Logic

## Scope Used
These notes are based on keyword extraction from `DEO+part+thesis.pdf`, especially sections labeled `3.5 Droplet-Engineered Organoids (DEO)`, `3.5.2`, and `3.5.4`, plus thesis figure captions `Figure 3.10` to `Figure 3.15`.

## Core DEO Setup
- DEOs are droplet-engineered organoids produced by microdroplet templating and automated bioprinting.
- A DEO is described as a single microdroplet with a diameter around `500 μm`.
- The droplet geometry keeps cells within a relatively short radius from the droplet center, which is expected to increase cell-cell interaction.
- The experimental theme across this chapter is not only growth, but how confinement, density, alginate, and Y-27632 alter:
  - growth kinetics
  - cystic morphology
  - fusion behavior
  - differentiation timing

## 1. Initial Cell Density Experiment
Relevant thesis text and figure:
- `Figure 3.10 Effects of initial cell density on the growth of Droplet-Engineered Organoids (DEOs)`

Thesis claims:
- low-density DEOs show delayed growth and only small cystic structures in early/mid culture
- middle-density DEOs reach larger cystic structures with better growth
- high-density DEOs grow faster and show earlier fusion
- high density may also trigger earlier differentiation and earlier need for passaging
- fusion is more visible in middle and high density conditions than low density
- middle-to-high density was selected for later experiments

Interpretation for dataset design:
- This experiment is a density screening experiment.
- The practical output is not simply “which looks larger”, but which density gives the best balance between:
  - growth speed
  - fusion potential
  - manageable differentiation timing

## 2. Alginate Experiment
Relevant thesis text and figures:
- `Figure 3.11 Alginate incorporation of droplet-engineered organoids`
- `Figure 3.12 Effects of alginate incorporation in droplet-engineered organoids`

Thesis claims:
- alginate was added to modulate mechanical compression
- alginate conditions are effectively:
  - no alginate control
  - low alginate `0.02%`
  - high alginate `0.05%`
- alginate groups show slower early growth
- alginate groups preserve cystic morphology longer and delay differentiation-associated thickening
- at day 7, fusion exists in alginate groups but fused structures are smaller than control
- control organoids more often appear to extend beyond droplet boundaries
- by day 13, alginate groups show more obvious progressive fusion compared with earlier time points
- overall interpretation: alginate slows growth and delays differentiation, while modifying fusion dynamics and confinement behavior

Interpretation for dataset design:
- This is not just a “larger is better” experiment.
- The thesis logic suggests two coupled readouts:
  - growth/morphology trajectory over time
  - delayed differentiation / altered fusion under mechanical modulation

## 3. Y-27632 Experiment
Relevant thesis text and figures:
- `Figure 3.14 Y-27632 promotes cystic morphology and delays differentiation in DEOs`
- `Figure 3.15 Effects of Y-27632 in DEOs`

Thesis claims:
- high-density DEOs were treated with `0, 10, 20, 50, 100 μM` Y-27632
- control shows cell-cell contact and aggregation, with fusion around days 3 to 5, but earlier differentiation than treated groups
- Y-27632 promotes cystic morphology and delays differentiation
- fusion increases with increasing Y-27632 concentration
- day 6 brightfield images were specifically selected to compare fusion across concentrations
- the frequency and number of fused organoids are higher in higher-concentration groups

Interpretation for dataset design:
- The main thesis claim is concentration-dependent improvement of fusion under Y-27632.
- Day 6 is a dedicated comparison point because it sits before day 7 differentiation-related morphology becomes visually confounding.

## Implication for Quantification
Across all three experiment branches, the thesis supports a mixed quantification framework:
- growth metrics:
  - diameter / cyst size
  - area
  - perimeter
- morphology metrics:
  - cystic vs thickened / differentiated appearance
  - degree of confinement within droplet
- interaction metrics:
  - organoid count per droplet
  - fusion frequency
  - fused area / fused mass extent
  - onset day of visible fusion

## Figure Logic from Thesis Captions
- Density figure: one main time-series panel plus an independent confirmation panel.
- Alginate figure: one longitudinal panel plus a detailed comparison panel at day 7 and day 13.
- Y-27632 figure: one longitudinal panel plus a dedicated comparison panel at day 6 with 10× imaging.

This thesis structure is consistent with the exported figure files and the transcription notes.

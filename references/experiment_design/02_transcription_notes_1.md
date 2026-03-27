# Transcription Notes 1: Morphology and Interpretation Clues

Source: `Shenzhen+University+Town+Sports+Center.md`

## Main Observations from the Discussion
The first transcript mainly explains how to interpret morphology over time rather than giving file structure.

### General temporal pattern
- Day 1 often starts as compact cell clusters rather than clear cysts.
- Day 2 begins to show cyst formation.
- Days 3 to 5 show cyst enlargement.
- By late time points, especially around day 7 or later, some organoids no longer maintain a clean spherical cyst shape.
- Late-stage organoids may thicken, shrink, wrinkle, or show intestinal-like differentiated morphology.

### Important interpretation rule
- Late-stage loss of perfect roundness should not automatically be treated as experimental failure.
- In some cases, irregular, wrinkled, or thickened morphology is interpreted as differentiation.
- Therefore, pure circularity is not a sufficient endpoint metric.

### Density experiment clue
- Low density starts from smaller, more dispersed cell clusters.
- High density starts with larger clusters and more rapid growth.
- Middle and high density were considered more suitable for later experiments.
- Fusion and close cell-cell interaction become more visible in larger / denser conditions.

### Y-27632 clue
- Higher Y-27632 concentration was described as showing stronger fusion by eye.
- `100 μM` was explicitly described as having the most obvious fusion and less obvious differentiation.
- A key visual sign of stronger fusion is that multiple small units appear to grow together into a large connected mass.

## Practical implications for analysis
This transcript suggests the quantification pipeline must separate at least three concepts:
- growth: larger cystic or tissue mass over time
- fusion: multiple units contacting and becoming a connected mass
- differentiation: loss of clean thin-walled cyst morphology, thickening, darkening, wrinkling, intestinal-like outer structure

## What should not be oversimplified
- A large irregular mass can still represent successful growth or fusion.
- A smooth cyst is not always the final desired state if the culture has entered differentiation.
- Later days should be scored with morphology-aware rules rather than purely geometric ones.

## What this means for figure interpretation
- Early time-series panels mainly communicate growth trajectory.
- Later panels communicate morphology transition, fusion, and differentiation.
- Dedicated “B” panels exist because a single time-series image per day is not enough to support robust interpretation.

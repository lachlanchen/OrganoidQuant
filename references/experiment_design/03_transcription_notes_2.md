# Transcription Notes 2: Experiment-to-Figure Mapping

Source: `Shenzhen+University+Town+Sports+Center+2.md`

## Confirmed mapping of the three main experiment branches
The transcript explicitly confirms the three core branches:

1. `App65 DEO + Alginate`
- different alginate concentrations under each date
- main readout: growth, fusion, and differentiation
- conditions: control, `0.02`, `0.05`

2. `App80 DEO`
- different Y-27632 concentrations
- main readout: fusion and growth
- conditions: control, `10`, `20`, `50`, `100 μM`

3. `DEO App81 P8`
- different initial cell densities
- main readout: growth and differentiation
- conditions: low, middle, high density

## Why there are A and B panels
The transcript gives a concrete reason:
- the main longitudinal panel is a time series with only one image per time point
- that is visually useful, but too sparse for strong comparison
- therefore a second panel is used to zoom into a selected day or selected subset of conditions with more images

## Dedicated detailed panels confirmed in the transcript
### Alginate B panel
- selected days: day 7 and day 13
- purpose: more detailed inspection of growth, fusion, and especially differentiation-related morphology
- rationale: the full time series is too sparse to show these differences clearly

### Y-27632 B panel
- selected day: day 6
- purpose: concentration-wise comparison of fusion before day 7 differentiation morphology becomes confounding
- rationale: day 7 already starts to show morphology that is less clean for fusion comparison

## Additional interpretation from the transcript
### Density experiment
- the intended message is that middle and high density grow better than low density
- faster growth and larger structures are expected in middle/high groups

### Alginate experiment
- alginate slows growth
- because growth is slower, differentiation also appears delayed or reduced
- control tends to show more darkened / thickened / differentiated morphology at later days
- alginate groups preserve cystic morphology longer

### Y-27632 experiment
- focus is fusion plus growth
- size-related readouts discussed in the transcript include:
  - perimeter
  - diameter
  - area
  - organoid or cyst size
- the transcript repeatedly points toward using the day 6 detailed panel as the clearest fusion comparison

## Implication for data products
This transcript supports a two-layer output strategy:
- layer 1: longitudinal summary over days
- layer 2: dedicated deep-dive analysis for chosen days

That means the final analysis should not only generate a single time-series plot. It should also generate condition-comparison figures for the dedicated B panels.

# Figure Design Note: Figure 2 Different Density DEO

Source files:
- `Figure 2 不同密度DEO.pdf`
- `Figure 2 不同密度DEO.svg`

## Extracted figure structure
Visible labels indicate:
- panel `A`
- panel `B`
- three density groups:
  - `Low density`
  - `Middle density`
  - `High density`
- time points:
  - `Day 0`
  - `Day 3`
  - `Day 5`
  - `Day 8`
  - `Day 11`
  - `Day 15`

## Interpreted panel logic
### Panel A
- primary longitudinal time series across the three density conditions
- used to show how morphology evolves across time
- likely one representative image per condition per time point

### Panel B
- independent confirmation panel, consistent with thesis text
- used to reinforce that the density-dependent pattern is reproducible
- not just decorative; it supports the claim that the effect is not an isolated example

## Biological message of the figure
The figure is designed to communicate:
- low density: slower growth, smaller structures, less interaction
- middle density: improved growth and visible fusion at later stages
- high density: fastest growth and earlier fusion, but also earlier differentiation risk

## What should be quantified for this figure
### Required quantitative outputs
- size trajectory over time:
  - equivalent diameter
  - area
  - perimeter
- morphology progression:
  - cystic fraction
  - differentiation-like morphology score
- interaction/fusion:
  - count of distinct organoid units inside one droplet
  - first day with visible contact/fusion
  - fused mass fraction

### Recommended figure outputs
- line plots of growth metrics vs day for low/middle/high density
- endpoint or late-day comparison of fusion / differentiation scores
- representative microscopy panel matching the A/B structure

## Coding implication
This figure requires the pipeline to preserve density as an experimental factor and not flatten it into a generic growth dataset. The main comparison is density-dependent kinetics and morphology transition.

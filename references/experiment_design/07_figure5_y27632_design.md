# Figure Design Note: Figure 5 Different Y-27632 Concentration

Source files:
- `Figure 5 不同浓度Y-27632调亮.pdf`
- `Figure 5 不同浓度Y-27632调亮.svg`

## Extracted figure structure
Visible labels indicate:
- panel `A`
- panel `B`
- five conditions:
  - `Control`
  - `10 μM`
  - `20 μM`
  - `50 μM`
  - `100 μM`
- panel A time points:
  - `Day 0`
  - `Day 2`
  - `Day 3`
  - `Day 5`
  - `Day 6`
  - `Day 7`
- panel B is associated with the same condition list and, from thesis/transcript, corresponds to a detailed day 6 comparison

## Interpreted panel logic
### Panel A
- longitudinal time-course panel showing morphology progression under increasing Y-27632 concentration
- used to show growth, cystic morphology maintenance, and delayed differentiation

### Panel B
- dedicated day 6 comparison across concentrations
- this is the key fusion-comparison panel
- chosen because day 6 is late enough for fusion to be visible but early enough to avoid strong day 7 differentiation confounding

## Biological message of the figure
This figure is built to support the main claim that:
- Y-27632 increases fusion efficiency in a concentration-dependent manner
- higher Y-27632 keeps organoids more cystic and delays differentiation
- control can show aggregation and some fusion, but higher concentrations produce more frequent and larger fused structures

## What should be quantified for this figure
### Panel A time-series metrics
- size over time:
  - diameter
  - area
  - perimeter
- organoid count per droplet over time
- cystic morphology score over time
- differentiation score over time

### Panel B day 6 metrics
- fusion score per droplet
- number of connected organoid units
- fused mass area fraction
- count of obvious merged structures
- size distribution of organoid masses

## Most important coding implication
This experiment should not be reduced to simple threshold-based object counting. By day 5 to day 7, the biologically relevant signal is often a large connected fused mass plus residual smaller units. The segmentation and scoring system must preserve:
- large merged organoid masses
- partial overlap / fusion states
- concentration-dependent progression toward larger connected structures

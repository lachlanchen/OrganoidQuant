# Comprehensive DEO Experiment Design and Quantification Plan

## 1. Integrated Understanding of the Project
Based on the thesis, figure exports, transcription notes, and handwritten summary, this dataset contains three major DEO experiment branches:

| Experiment | Data branch | Main variable | Main biological question | Main outputs |
| --- | --- | --- | --- | --- |
| Density | `DEO/DEO App81 P8` | initial cell density | how density affects growth, fusion opportunity, and differentiation timing | growth kinetics, morphology, fusion onset |
| Alginate | `DEO/App65 DEO+Alginate` | alginate concentration | how mechanical modulation changes growth, fusion, and differentiation | growth + differentiation delay + day 7 / 13 detailed analysis |
| Y-27632 | `DEO/App80 DEO` | Y-27632 concentration | how ROCK inhibition changes fusion efficiency and cystic morphology | fusion + growth + day 6 detailed analysis |

## 2. High-Level Experimental Logic
### Density experiment
Goal:
- choose a useful starting density for later DEO culture

Expected conclusion from sources:
- low density grows too slowly and interacts less
- middle / high density grow better and fuse more
- very high density may differentiate earlier

### Alginate experiment
Goal:
- test whether alginate-mediated mechanical modulation slows growth and delays differentiation while altering fusion behavior

Expected conclusion from sources:
- alginate slows early growth
- alginate delays differentiation-associated morphology changes
- control differentiates earlier
- detailed comparison should focus on day 7 and day 13

### Y-27632 experiment
Goal:
- test whether increasing Y-27632 concentration increases DEO fusion efficiency

Expected conclusion from sources:
- fusion increases with Y-27632 concentration
- higher concentrations preserve cystic morphology longer
- day 6 is the best dedicated comparison day for fusion

## 3. What Each Figure Is Trying to Show
### Figure 2: density
- panel A: time-series growth/morphology under low, middle, high density
- panel B: independent confirmation of the density effect

### Figure 3: alginate
- panel A: longitudinal morphology from day 0 to day 12 or 13
- panel B: day 7 and day 13 detailed comparison with more images / higher information density

### Figure 5: Y-27632
- panel A: longitudinal morphology from day 0 to day 7
- panel B: day 6 dedicated comparison across control to 100 μM

## 4. Step-by-Step Quantification Workflow
### Step 1: build metadata table
For every raw image, extract and store:
- experiment branch
- condition label
- date label / day label
- magnification (`4x`, `10x`, etc.)
- replicate index
- source path
- whether image belongs to a main time-series panel or a dedicated detailed panel

### Step 2: standardize image groups
Group images according to the real experimental question.

#### Density
- group by `low`, `middle`, `high`
- sort by day
- mark whether image belongs to main panel A or independent confirmation B

#### Alginate
- group by `control`, `0.02%`, `0.05%`
- build full time series
- separately collect day 7 and day 13 detailed images

#### Y-27632
- group by `0`, `10`, `20`, `50`, `100 μM`
- build full time series
- separately collect day 6 detailed 10× images

### Step 3: segment or identify organoid structures within each droplet
This should be morphology-aware.

Recommended logic:
- do not assume only small round objects are valid organoids
- preserve both:
  - small separate organoids
  - large fused / overlapping organoid masses
- avoid counting a late-stage fused mass as background or ignoring it because it is irregular

Recommended implementation chain:
1. image normalization and contrast balancing
2. coarse organoid candidate detection
3. hybrid segmentation:
   - small-object detector for peripheral small organoids
   - large-mass detector or polygon refinement for fused central masses
4. save instance or polygon outputs for each image
5. derive quantitative metrics from final segmentation, not from raw thresholding

### Step 4: derive image-level metrics
For each image, compute at minimum:
- organoid count
- combined organoid area
- perimeter
- equivalent diameter or cyst size
- fraction of area occupied by the largest connected mass
- fusion score
- differentiation / morphology score

### Step 5: define experiment-specific scores
#### Growth score
Can be represented by:
- area
- perimeter
- equivalent diameter
- cyst size

#### Fusion score
Should combine:
- number of connected masses
- largest connected mass fraction
- visible contact / coalescence between neighboring organoids
- reduction in separation between units over time

#### Differentiation score
Should capture:
- thickened epithelial wall
- darkening
- wrinkling / intestinal-like morphology
- loss of clean thin-walled cystic appearance

## 5. Recommended Quantification by Experiment
### Density
Primary metrics:
- size trajectory vs day
- fusion onset day
- differentiation onset day

Secondary metrics:
- organoid count within droplet
- largest mass fraction

Expected figure outputs:
- line plots for size vs day
- late-day fusion comparison
- qualitative panel for morphology progression

### Alginate
Primary metrics:
- size trajectory vs day
- cystic morphology score vs day
- differentiation score vs day
- day 7 and day 13 fusion / differentiation comparison

Secondary metrics:
- confinement within droplet
- largest mass fraction

Expected figure outputs:
- line plots for growth and differentiation delay
- day 7 and day 13 dedicated comparison plots

### Y-27632
Primary metrics:
- fusion score vs day
- size trajectory vs day
- day 6 fusion comparison across concentrations

Secondary metrics:
- organoid count
- largest fused mass area
- cystic morphology maintenance

Expected figure outputs:
- concentration-wise line plots across days
- day 6 boxplot / violin / bar comparison with significance markers

## 6. Statistical Plan
### Replicate handling
- use replicate-level image records as the atomic unit
- aggregate by condition and day
- keep raw replicate values for replotting and QC

### Suggested statistics
- for time-series comparisons within one condition set:
  - nonparametric comparisons where sample size is small
  - mixed-effects or repeated structure later if dataset quality supports it
- for dedicated-day cross-condition comparisons:
  - pairwise comparisons vs control
  - multiple-comparison correction if doing many pairwise tests

### Output tables to save
- raw image-level metrics table
- day-level summary table
- dedicated-panel comparison table
- statistics table with p-values and method used

## 7. Practical Deliverables the Analysis Should Produce
### Source-based documents
- source summaries for thesis, transcripts, figures, and note

### Data products
- standardized metadata table
- image-level quantitative table
- organoid-level table if segmentation supports it
- figure-ready summary tables

### Figures
- publication-style microscopy panels
- time-series quantification lines
- dedicated-day comparison plots
- significance annotations

## 8. What We Need To Do Next, Concretely
1. finalize metadata mapping for all three experiment branches
2. define one stable naming system for condition, day, magnification, and replicate
3. separate time-series images from dedicated deep-dive images
4. run a segmentation/measurement pipeline that preserves both small organoids and fused large masses
5. compute growth, fusion, and differentiation metrics per image
6. aggregate by day and condition
7. produce manuscript-style plots matching the panel logic from Figures 2, 3, and 5
8. keep all intermediate quantitative tables so figures can be regenerated without re-segmentation

## 9. Minimal Coding Blueprint
A practical codebase should eventually contain these modules:
- `metadata_indexer`: parse folder/file names into a clean table
- `image_qc`: detect unreadable or inconsistent images
- `segmentation`: hybrid organoid segmentation per image
- `measurement`: size, area, perimeter, largest-mass fraction, count
- `fusion_scoring`: morphology-aware fusion metrics
- `differentiation_scoring`: morphology-aware differentiation metrics
- `aggregation`: replicate-to-day summaries
- `plotting`: publication-style figure generation

## 10. Bottom-Line Scientific Story
The combined source set tells one coherent story:
- density sets the baseline physical opportunity for organoid interaction
- alginate changes the mechanical environment and delays differentiation while altering growth and fusion behavior
- Y-27632 improves fusion efficiency in a concentration-dependent way

The analysis should therefore be built not as a generic image-processing task, but as a structured biological quantification workflow that separately measures:
- growth
- fusion
- differentiation
- and the specific detailed comparison days chosen for manuscript-quality figures

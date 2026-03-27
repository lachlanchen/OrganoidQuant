# App80 Fusion Analysis: Main Problem Definition

Dataset scope:
- `DEO/App80 DEO`
- experiment variable: Y-27632 concentration
- main biological question: how Y-27632 changes organoid fusion and growth over time, especially under the dedicated day 6 comparison logic

## Core problem
The main problem in `App80 DEO` is no longer file organization or figure layout.

The real problem is that fusion is hard to define consistently across all stages because organoid morphology changes substantially over time.

In practical terms, this means fusion analysis is not just an image-processing problem. It is a morphology-definition problem.

## What this means in practice

### 1. Late-stage fused organoids stop looking like separate round objects
- Early days often contain many smaller cystic organoids that are easier to count.
- Later days often contain large irregular or dark connected masses.
- A method tuned for small round objects tends to miss the biologically important large fused masses.
- A method tuned for large masses tends to over-merge structures and lose individual organoid identity.

This is the first major source of instability in the current pipeline.

### 2. Fusion is confounded with growth and differentiation
A larger structure is not automatically a more fused structure.

Irregular, dark, thickened, or non-spherical morphology may reflect different biological states, for example:
- true fusion between neighboring organoids
- simple overall growth of one structure
- late differentiation
- partial collapse or loss of clean cystic morphology

Because of this, a single metric such as area, perimeter, or apparent size cannot be treated as a valid fusion readout by itself.

### 3. The previous fusion score is not biologically grounded enough
The previous pipeline produced plots that were visually acceptable, but the underlying numbers were not sufficiently reliable.

The problem is that the fusion score depended too much on heuristic visual or geometric proxies rather than a stable object-level biological definition.

This means the figures can look plausible while the actual measurement logic remains weak.

### 4. Segmentation is the main technical bottleneck, but not the whole problem
Segmentation is a critical obstacle, but solving segmentation alone is still not enough.

Observed limitations:
- Cellpose detects many small organoids but tends to miss or fragment the large fused masses.
- Vision-model polygon outputs can capture large masses better, but boundaries are often not precise enough.
- The hardest cases are exactly the most biologically relevant ones: partially merged, overlapping, non-spherical organoids.

So the problem is not merely “find all objects.”
The harder requirement is to preserve biologically meaningful structure in intermediate and late fusion states.

### 5. A robust fusion analysis needs a stricter object-level definition
For each image, the pipeline should ideally distinguish at least these categories:
- clearly separate organoid units
- partially contacting units
- clearly fused masses
- differentiated / thickened / collapsed structures

Without this distinction, the fusion score becomes unstable across days and concentrations.

## Bottom-line diagnosis
The real problem in `App80 DEO` fusion analysis is this:

Fusion quantification is currently a morphology-definition problem, not just a segmentation problem.

That is why methods that look technically reasonable can still fail biologically.

## Implication for future tasks
Future pipeline work should not only ask:
- how do we segment the image?

It must also ask:
- what biological state counts as fusion?
- how do we distinguish fusion from growth?
- how do we distinguish fusion from differentiation-related morphology change?
- how do we keep large fused masses and small residual organoids in the same measurement system?

## Recommended direction for later pipeline redesign
A stronger App80 pipeline should be built around:
- hybrid segmentation that preserves both small organoids and large fused masses
- explicit morphology-state labeling
- fusion metrics derived from object relationships, not only bulk area
- separate handling of early, mid, and late morphology regimes if needed

## One-sentence summary
The current App80 fusion-analysis bottleneck is not that the computer cannot see the image. It is that the pipeline does not yet have a sufficiently stable biological definition of fusion across changing morphology.

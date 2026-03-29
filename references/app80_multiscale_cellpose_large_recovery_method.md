# App80 Multiscale Cellpose With Large-Mass Recovery

## Short Answer

Yes, this method is partly general.

No, it is not a universal segmentation method that can be dropped onto any microscopy dataset without retuning.

What is general:
- multiscale Cellpose on the same image
- a second image-derived recovery branch for very large irregular objects
- overlap-aware merging between branches
- using a contrast-enhanced support map to reject weak masks and keep biologically supported ones

What is not general:
- the exact date-to-stage mapping
- the exact diameter triplets
- the exact large-mass recovery thresholds
- the exact rejection rules for droplet-like masks versus organoid-like masks

So the correct interpretation is:
- this is a reusable framework
- but it still needs dataset-specific tuning

## Why This Method Was Needed

Plain Cellpose was missing the biologically important cases in App80 10x images:
- early cluster-like organoids on the first date
- very large fused irregular organoid masses on later dates
- differentiated irregular tissue-like masses on the last date

The failure mode was consistent:
- small and medium objects were often found
- large irregular fused structures were under-segmented or dropped
- increasing diameter alone was not sufficient

That is why the current method uses two branches:
1. multiscale Cellpose
2. deterministic signal-based large-object recovery

## Current Script

Main script:
- [run_multiscale_dateaware_cellpose.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app80_first_replicate_multiscale_cellpose/run_multiscale_dateaware_cellpose.py)

Latest output example:
- [10x_cellpose_multiscale_dateaware_large_recovery_flat](/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/first_replication_selected_dates/10x_cellpose_multiscale_dateaware_large_recovery_flat)

## Method Structure

### 1. Load TIFF and convert to grayscale
The script reads the TIFF and produces:
- `rgb`
- `gray`

### 2. Build a hybrid signal image
The method creates a black-background signal image that was empirically useful in this project.

It combines:
- CLAHE-enhanced grayscale
- lightly blurred foreground image
- heavily blurred background estimate
- inverted grayscale component
- background-subtracted residual component

Current formula:
- `signal = 0.45 * inv_norm + 0.55 * residual_norm`

This is the same signal family that was previously useful as the "second column" image.

### 3. Build a support mask
A support mask is created from the signal image using:
- Otsu threshold
- percentile threshold
- morphological open/close cleanup

This support mask is not the final segmentation.
It is only a biologically informed support region that helps:
- refine Cellpose masks
- reject weak masks
- recover large irregular masses later

### 4. Run Cellpose at three diameters
For each image, the script runs Cellpose three times with different diameters.

Current App80 date-aware settings:
- `05-十二月-2025`: `[90, 180, 320]`
- `07-十二月-2025`: `[180, 320, 480]`
- `08-十二月-2025`: `[220, 380, 560]`
- `09-十二月-2025`: `[200, 340, 520]`
- `10-十二月-2025`: `[380, 700, 980]`
- `11-十二月-2025`: `[420, 780, 1100]`
- `12-十二月-2025`: `[320, 600, 900]`

These are not globally correct values.
They are tuned to the App80 first-replicate 10x series.

### 5. Score Cellpose candidates
Each candidate mask is scored using:
- support overlap
- mean hybrid-signal intensity inside the mask
- edge strength along the mask boundary
- fill ratio
- stage bonus

This makes the method less dependent on Cellpose alone.

### 6. Recover large irregular masses from the signal image
This is the key addition.

For difficult stages, the script also segments directly from the signal image using:
- percentile thresholding
- morphological closing
- border clearing
- hole filling
- connected components
- optional watershed on the binary region

This branch is enabled only for stages where it helps:
- `early_cluster`
- `fused_large`
- `differentiated_irregular`

It is intentionally disabled for the mid cystic stages because there it tends to over-merge many organoids into one large region.

### 7. Merge all candidates
The script merges:
- Cellpose candidates
- signal-component candidates
- signal-watershed candidates

The merge logic uses:
- overlap of the smaller mask
- IoU
- score comparison
- area comparison
- source preference when a large signal-derived mask clearly explains more tissue than a smaller Cellpose fragment

## Is It General?

## Generalizable Parts
These parts can be reused on other brightfield organoid datasets:
- multiscale Cellpose instead of one fixed diameter
- using a precomputed signal image rather than raw grayscale alone
- adding a deterministic large-object recovery branch
- merging masks from multiple branches rather than trusting one model pass
- using dataset stage information when known

## Non-General Parts
These parts are App80-specific and should be retuned for new data:
- exact stage names
- exact diameter triplets
- exact threshold quantiles for large-mass recovery
- exact max-area and border-touch rejection rules
- exact support-mask morphology sizes

So if this is applied to another dataset, the framework should stay the same, but these parameters should be recalibrated.

## When It Should Transfer Well
This method should transfer reasonably well if the new dataset has:
- brightfield or similar transmitted-light contrast
- circular to irregular organoid structures
- a progression from small clusters to large fused masses
- moderate consistency in image magnification and scale

## When It Will Not Transfer Cleanly
This method is likely to perform poorly without retuning if the new dataset has:
- fluorescence instead of brightfield
- very different magnification or pixel scale
- no large fused masses
- strong debris/background artifacts unlike App80
- entirely different morphology, for example single cells rather than organoid bodies

## Practical Reuse Strategy

If you want to use this on another dataset, the correct workflow is:

1. Start with the same script architecture.
2. Inspect 5 to 10 representative images across the time course.
3. Estimate diameter triplets per stage, not per image.
4. Check whether the hybrid signal still highlights biologically meaningful tissue.
5. Turn the large-mass recovery branch on only where Cellpose misses large irregular objects.
6. Compare galleries before trusting the masks.
7. Only then batch the rest of the dataset.

## Current Strengths

Compared with plain Cellpose, the current method is better at:
- keeping very large irregular fused masses in later App80 dates
- keeping late differentiated irregular tissue as organoid instances
- preserving cleaner mid-stage cystic Cellpose results by not forcing signal-based recovery where it hurts

## Current Weaknesses

This method is still not a perfect instance-segmentation solver.

Known weaknesses:
- early dense cluster images can still be over-fragmented or partially merged
- very large fused masses may be kept as one large instance when biologically they may contain several fused lobes
- if the support map is too permissive, the recovery branch can still produce a large region that is visually plausible but biologically too coarse

## Recommended Interpretation

This method should be treated as:
- a stronger semi-general segmentation framework for brightfield organoid images
- not a final foundation model for all organoid datasets
- especially useful when the main failure is missing large irregular fused objects

## Recommended Next Step For Other Data

For a new dataset, do not copy the App80 parameter table blindly.

Instead:
- keep the framework
- replace the stage mapping
- retune the diameter triplets
- retune the recovery thresholds on a small validation subset

That is the technically correct way to reuse this method.

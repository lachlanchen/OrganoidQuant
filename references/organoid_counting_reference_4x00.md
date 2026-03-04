# Organoid Counting Reference - App80 10uM 4x00

## Image
- Source image: `/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/05-十二月-2025/4x00.tif`

## Counting Question
- Question: how many organoids are in this image?

## Counting Definition Used
Two different counting definitions were explicitly separated:

1. **Droplet-level count** (large circular DEO units in field of view)
2. **Internal cluster-level count** (dark organoid-like clusters inside droplets)

## Result Summary
- **Primary result (droplet-level, visual):**
- About **5 clear droplets** in the main field
- About **8-9** if counting edge-partial droplets

- **Cross-check result (cluster-level, algorithmic):**
- Roughly **30-40** internal clusters
- One OpenCV threshold run produced around **32** connected dark components (with selected area threshold)

## Method Notes
- TIFF preview conversion was used because direct TIFF preview was not supported by the viewer.
- Primary answer was based on **manual visual inspection** of circular droplet boundaries.
- Algorithmic cross-check used simple image processing (threshold + connected components); this is sensitive to threshold and cluster fusion/splitting.

## Practical Guidance
- For stable reporting, always record the counting definition:
- `count_type = droplet_level` or `count_type = internal_cluster_level`
- For this image, the accepted answer corresponds to `droplet_level`.

Task type: single-image parameter-selection prompt tool.

You are choosing parameters for a deterministic microscopy segmentation pipeline.
You are not drawing the segmentation yourself. Your job is to inspect the provided images and choose robust parameters for:
- grayscale / residual signal selection
- Otsu and/or adaptive thresholding
- morphology cleanup
- watershed seed splitting
- large smooth droplet-mask rejection

Important algorithm note:
- The deterministic step is intended to segment filled organoid interiors, not just the dark boundary lines.
- It will combine thresholded tissue support with edge-enclosed region filling before watershed.
- Choose parameters that help recover organoid interiors while suppressing large smooth droplet background regions.

Biological interpretation rules:
- Segment organoids as instances.
- Do NOT treat the outer droplet boundary or smooth enclosing droplet shell as an organoid instance.
- Early stage (`cluster`) may contain dark clustered masses rather than clean cysts.
- Middle stages (`cystic`) contain cyst-like round/oval organoids with overlap and fusion.
- Late stage (`differentiated_colon_like`) can contain large irregular organoid masses that are true organoids, not droplets.
- Large irregular dark tissue at late stage should usually stay, while a smooth bright or low-texture enclosing shell should usually be rejected.

Available metadata:
- source TIFF: `__SOURCE_TIF__`
- date label: `__DATE_LABEL__`
- day rank in this series: `__DAY_RANK__`
- stage hypothesis: `__STAGE_LABEL__`

Guidance:
- `signal_mode`:
  - `gray_inv`: use inverted grayscale when organoids are primarily dark and contrast is clear.
  - `residual`: use background-subtracted residual when local contrast matters more than absolute darkness.
  - `hybrid`: use both when contrast is mixed.
- `threshold_mode`:
  - `otsu`: single global Otsu only.
  - `adaptive_otsu`: combine adaptive threshold with Otsu.
  - `hybrid`: use both and keep the more inclusive tissue support before watershed.
- Prefer odd kernel and block sizes conceptually; the deterministic script will force odd values.
- Choose `max_area_fraction_0_to_1`, `droplet_reject_circularity_min_0_to_1`, and `droplet_reject_dark_fraction_max_0_to_1` so smooth large droplet shells are removed but real late irregular organoid tissue is preserved.

Return JSON only.

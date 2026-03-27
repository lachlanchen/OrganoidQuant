# Fusion Analysis Test Prep

This tool builds a blinded test set by copying the first `10x` replicate from each date folder into a neutral folder with random UID filenames.

## Purpose
- remove obvious date names from filenames
- avoid exposing condition/date metadata to prompt-based analysis tools
- keep a private mapping file for later reverse lookup

## Usage
```bash
analysis-tools/fusion_analysis_test_prep/prepare_blinded_first_replicates.py \
  --output-root /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001 \
  '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/05-十二月-2025' \
  '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/07-十二月-2025'
```

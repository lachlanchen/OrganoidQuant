# App80 Edge Proxy Metrics

This tool computes exploratory edge- and gradient-based morphology proxies for all `10x` TIFF images in selected App80 day folders.

## Inputs
- one or more day folders such as:
  - `DEO/App80 DEO/10uM/05-十二月-2025`
  - `DEO/App80 DEO/10uM/07-十二月-2025`

## Outputs
- per-image CSV
- per-day summary CSV with mean/std/n
- reciprocal trend plots by day
- raw trend plots by day

## Usage
```bash
/home/lachlan/miniconda3/envs/organoid/bin/python analysis-tools/app80_edge_proxy_metrics/plot_app80_day_edge_proxy_metrics.py \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_10uM_edge_proxy_all_10x \
  '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/05-十二月-2025' \
  '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/07-十二月-2025' \
  '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/08-十二月-2025' \
  '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/09-十二月-2025' \
  '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/10-十二月-2025' \
  '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/11-十二月-2025' \
  '/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO/10uM/12-十二月-2025'
```

## Metric note
These are exploratory morphology proxies, not validated biological fusion scores.

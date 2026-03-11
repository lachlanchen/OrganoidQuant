# App80 10x Concentration Trends

This folder contains deterministic plotting code for the App80 10x Y-27632 dataset.

Files:
- `plot_app80_10x_concentration_trends.py`: builds the publication subset, daily means, and final figures.
- `run_app80_10x_concentration_trends.sh`: launcher that prefers the `organoid` env and falls back to base Python if `matplotlib` is incomplete there.

Selection rule used for the publication subset:
- For each concentration/date folder, take the first 3 sorted `10x*.tif` images.
- Skip the known stuck image `No/10-十二月-2025/10x02.tif`.
- Average the selected 3 replicate results per day.

Outputs are written to:
- `analysis-output/app80_10x_concentration_trends/`

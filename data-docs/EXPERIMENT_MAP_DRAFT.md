# DEO Experiments - Rough Mapping Draft

This is a **first-pass mapping** based on folder/file names only.
Use this table to confirm details with your labmate.

## 1) Major experiment mapping (rough)

| Major experiment (summary `.tif`) | Likely raw data folder | Why this is likely | Confidence |
|---|---|---|---|
| `不同浓度Alginate.tif` | `App65 DEO+Alginate/` | File names repeatedly include `0.02% Alginate`, `0.05% Alginate`, and `no` control across many days. | High |
| `不同浓度Y-27632.tif` | `App80 DEO/` | Folder is organized by concentration groups: `No`, `10uM`, `20uM`, `50uM`, `100uM`. | High |
| `不同密度DEO.tif` | `DEO App81 P8/` | File names repeatedly include `low`, `middle`, `high` (density-like labels) with 4x/10x imaging. | Medium-High |

## 2) Per-folder structure snapshot

| Folder | Main organization style | Approx. structure |
|---|---|---|
| `App65 DEO+Alginate/` | Date-based time course | 13 date folders (Nov-Dec 2025), many 4x/10x images per condition |
| `App80 DEO/` | Concentration-based groups | 5 condition folders (`No`, `10uM`, `20uM`, `50uM`, `100uM`), then date folders and images |
| `DEO App81 P8/` | Date-based + density labels | 17 date folders (Oct 2025 + `low transfer`), files include `low/middle/high` |

## 3) Detailed day-specific summary figures

| Detailed summary file | Likely parent major experiment | Likely meaning |
|---|---|---|
| `Alginate D7和D13.tif` | `不同浓度Alginate.tif` (App65) | Selected comparison for Day 7 and Day 13 in Alginate concentration experiment |
| `不同浓度Y-27632 Day 6 10x.tif` | `不同浓度Y-27632.tif` (App80) | Day 6 subset at 10x magnification for Y-27632 concentration experiment |

## 4) Suggested questions to confirm with labmate

1. Is `DEO App81 P8` exactly the source of `不同密度DEO.tif`?
2. For `App65`, are the only intended concentration groups `no`, `0.02%`, `0.05%` Alginate?
3. For `App80`, confirm dose series order: `No`, `10`, `20`, `50`, `100 uM` Y-27632.
4. For `Alginate D7和D13.tif`, what is the exact reference day numbering (start date / Day 0 definition)?
5. For `不同浓度Y-27632 Day 6 10x.tif`, confirm if all images come only from 10x field selection on Day 6.

## 5) Quick naming standard (optional, for future cleanup)

If you want, you can normalize this to:
- `ExpA_AlginateConc`
- `ExpB_Y27632Conc`
- `ExpC_DEODensity`
- `ExpA_D7_D13`
- `ExpB_D6_10x`


# App80 All-Concentration GPU Resume Runbook

Date: 2026-03-31
Project root: `/home/lachlan/ProjectsLFS/Zhengyu`

## Purpose

This note records the current App80 all-concentration segmentation run setup, why the Python environment became unstable before, how the run was resumed, and the rules to keep future long GPU jobs stable.

## Current Task

The active batch is the all-concentration App80 `10x` segmentation and profiling run under:

- `/home/lachlan/ProjectsLFS/Zhengyu/DEO/App80 DEO`

The output root is:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery`

The run keeps per-image intermediates under:

- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/runs`

For each image it saves:

- `*_mask_16bit.png`
- `*_instance_rgb.png`
- `*_overlay.png`
- `*_signal.png`
- `*_metrics.json`
- `*_segmentation_stats.json`

The final outputs are expected under:

- `profiling/quantification/`
- `figures/`

## Environment Policy

Only these repository environments should be used:

- `organoid`
- `organoid-gpu`

For this App80 segmentation batch, the correct environment is:

- `organoid-gpu`

The environment path is:

- `/home/lachlan/miniconda3/envs/organoid-gpu`

## What Actually Went Wrong Before

The repeated instability was not mainly caused by a simple `.bashrc` CUDA path override.

The real problems were:

1. `organoid` had a mixed CPU/GPU Python stack.
   - Conda `pytorch` was CPU-only.
   - Pip `torch` was a different CUDA build.
   - That environment was not trustworthy for GPU Cellpose work.

2. `organoid-gpu` was contaminated by user-site imports.
   - `~/.local/lib/python3.10/site-packages` was appearing on `sys.path`.
   - `OpenVoice` also leaked onto `sys.path` through `easy-install.pth`.
   - This produced inconsistent import-time behavior and impossible runtime errors.

3. Detached/background runs made that instability more obvious.
   - The problem was not tmux itself.
   - The problem was a polluted Python import path combined with a broken torch/runtime state.

Examples of the failure signature seen before cleanup:

- `bad marshal data`
- `EnumMeta.__call__() missing 1 required positional argument: 'value'`
- `UnboundLocalError` from normal stdlib paths
- inconsistent `inspect` / `typing` / `scipy` import failures

Those are not normal App80 script bugs. They indicate a broken Python environment state.

## What Was Fixed

The stable repair was:

1. Keep using `organoid-gpu`.
2. Remove user-site contamination by forcing:
   - `PYTHONNOUSERSITE=1`
3. Pin the run to GPU 0 by forcing:
   - `CUDA_DEVICE_ORDER=PCI_BUS_ID`
   - `CUDA_VISIBLE_DEVICES=0`
4. Disable Torch compile/JIT paths that were causing instability in this env:
   - `TORCHDYNAMO_DISABLE=1`
   - `TORCH_DISABLE_DYNAMO=1`
   - `PYTORCH_JIT=0`

These are now configured in the environment activation hooks:

- `/home/lachlan/miniconda3/envs/organoid-gpu/etc/conda/activate.d/env_vars.sh`
- `/home/lachlan/miniconda3/envs/organoid-gpu/etc/conda/deactivate.d/env_vars.sh`

The intended activation behavior is:

```bash
source /home/lachlan/miniconda3/etc/profile.d/conda.sh
conda activate organoid-gpu
python - <<'PY'
import os, site
print('PYTHONNOUSERSITE', os.environ.get('PYTHONNOUSERSITE'))
print('CUDA_VISIBLE_DEVICES', os.environ.get('CUDA_VISIBLE_DEVICES'))
print('user_site_on_path', site.getusersitepackages() in __import__('sys').path)
PY
```

The expected practical state is:

- `PYTHONNOUSERSITE=1`
- `CUDA_VISIBLE_DEVICES=0`
- user site not on `sys.path`

## GPU State

The run should always use GPU 0.

Current GPU mapping on this machine:

- GPU 0: `00000000:01:00.0`
- GPU 1: `00000000:08:00.0`

Operational rule for Zhengyu heavy runs:

- use GPU 0 only
- do not let long segmentation batches choose a GPU implicitly

This matters because earlier system investigation suggested the display-related crash path was more likely when heavy workloads were not explicitly pinned away from the fragile path.

## Verified Runtime State

After cleanup, the intended `organoid-gpu` state is:

- `torch 2.6.0+cu124`
- `torch.cuda.is_available() == True`
- `CellposeModel(gpu=True)` initializes successfully on `cuda:0`

The batch was resumed only after confirming that:

- CUDA is visible
- GPU model is visible
- Cellpose can create a GPU model in `organoid-gpu`

## Resume Method

The App80 all-concentration run was resumed in tmux, not as a plain foreground shell job.

The tmux sessions used are:

- `app80_allconc_full`
- `app80_allconc_guard`
- `app80_allconc_monitor`

Their roles are:

1. `app80_allconc_full`
   - main segmentation/profiling batch

2. `app80_allconc_guard`
   - restarts the main batch if it dies before final outputs exist

3. `app80_allconc_monitor`
   - records periodic status snapshots during the run

Important cleanup that was needed during resume:

- one stale non-tmux Python process was found still writing to the same output tree
- that stale process was killed
- only the tmux-owned GPU process was kept

That prevents duplicate workers from racing on the same output path.

## Current Progress Snapshot

Snapshot at the time this note was written:

- total complete: `601 / 646`
- `No`: `92 / 92`
- `10uM`: `146 / 146`
- `20uM`: `128 / 128`
- `50uM`: `134 / 134`
- `100uM`: `101 / 146`

At this snapshot, the final combined outputs did not exist yet:

- `profiling/quantification/per_image_metrics.csv`
- `profiling/quantification/daily_summary.csv`
- `figures/app80_all_concentrations_segmentation_metrics.png`
- `figures/app80_all_concentrations_normalized_edge_over_count_curvature.png`

So this note documents a live in-progress batch, not a finished run.

## How To Check It

### Check tmux sessions

```bash
tmux ls | grep app80_allconc
```

### Attach to the main run

```bash
tmux attach -t app80_allconc_full
```

### Check current GPU usage

```bash
nvidia-smi --query-compute-apps=gpu_bus_id,pid,process_name,used_gpu_memory --format=csv,noheader
```

### Check current completed counts

```bash
python - <<'PY'
from pathlib import Path
root = Path('/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/app80_all_concentrations_multiscale_large_recovery/runs')
counts = {}
for conc in sorted([p for p in root.iterdir() if p.is_dir()]):
    counts[conc.name] = len(list(conc.rglob('*_metrics.json')))
print(counts)
print('total', sum(counts.values()))
PY
```

## Practical Rules Going Forward

1. Use `organoid-gpu` for segmentation.
2. Use GPU 0 only.
3. Run long App80 segmentation jobs in tmux.
4. Keep `PYTHONNOUSERSITE=1` active in that env.
5. Preserve all per-image intermediates under `runs/`.
6. Do not restart from zero unless resume is genuinely impossible.
7. Before resuming, check for stale duplicate Python workers and kill the redundant one.

## Short Conclusion

The repeated environment trouble was not mainly a CUDA toolkit path problem.

The real cause was a polluted Python environment state:

- mixed CPU/GPU torch stacks in `organoid`
- user-site contamination in `organoid-gpu`
- detached-run instability exposing that broken state

The stable operating model for this project is now:

- `organoid-gpu`
- `PYTHONNOUSERSITE=1`
- `CUDA_VISIBLE_DEVICES=0`
- tmux-run batch
- preserve all segmentation intermediates and downstream profiling outputs

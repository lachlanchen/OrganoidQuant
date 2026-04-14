# Nano Banana 2.0 Handoff: Docs, Code, References, and Usage Notes

Date: 2026-04-15

This note is a local handoff for another model or agent that needs to use GRS AI Nano Banana from this repository.

It covers:
- the saved API documentation in this repo
- the exact code paths used in this project
- the prompt/reference materials we actually used
- the run artifacts that show real usage
- how to adapt the same API for a non-segmentation task such as a book cover

## 1. Core API Documentation In This Repo

Primary local docs:
- [grsai_nano_banana_api_documentation_2026-04-10.md](/home/lachlan/ProjectsLFS/Zhengyu/references/grsai_nano_banana_api_documentation_2026-04-10.md)
- [grsai_nano_banana_api_doc.md](/home/lachlan/ProjectsLFS/Zhengyu/references/grsai_nano_banana_api_doc.md)

These two are the main Nano Banana API references saved locally.

### Key API facts

Preferred host:
- `https://grsaiapi.com`

China host:
- `https://grsai.dakka.com.cn`

Primary generation endpoint:
- `POST /v1/draw/nano-banana`
- full URL: `https://grsaiapi.com/v1/draw/nano-banana`

Polling endpoint:
- `POST /v1/draw/result`
- full URL: `https://grsaiapi.com/v1/draw/result`

Headers:
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer <API_KEY>"
}
```

Typical request body:
```json
{
  "model": "nano-banana-2",
  "prompt": "your prompt here",
  "urls": ["https://example.com/reference.png"],
  "aspectRatio": "auto",
  "imageSize": "1K",
  "webHook": "-1",
  "shutProgress": false
}
```

Typical submit response:
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "id": "task-id"
  }
}
```

Typical poll request:
```json
{
  "id": "task-id"
}
```

Typical poll response:
```json
{
  "code": 0,
  "data": {
    "id": "task-id",
    "results": [
      {
        "url": "https://...",
        "content": "..."
      }
    ],
    "progress": 100,
    "status": "succeeded",
    "failure_reason": "",
    "error": ""
  },
  "msg": "success"
}
```

## 2. Nano Banana 2.0 Specific Notes

In this repo, `nano-banana-2` was used as a direct model-name swap on the same `/v1/draw/nano-banana` endpoint.

Important points from the saved docs:
- `nano-banana-2` is selected by setting:
  - `"model": "nano-banana-2"`
- supported `imageSize` examples include:
  - `1K`
  - `2K`
  - `4K`
- supported `aspectRatio` includes standard ratios and, in the saved docs, some additional wide/tall ratios such as:
  - `1:4`
  - `4:1`
  - `1:8`
  - `8:1`
- if you want task-id polling instead of webhook callback, use:
  - `"webHook": "-1"`

Practical usage pattern used here:
1. submit once
2. save prompt, payload, and task id
3. poll by task id
4. never resubmit the same job unless the remote job clearly failed or timed out

## 3. Gemini-Compatible Note

The saved docs also note a Gemini-compatible mode.

Saved compatibility note:
- replace the base host with the GRS AI host
- replace `gemini-2.5-flash-image` with `nano-banana-fast`

Example saved in local docs:
- `https://grsaiapi.com/v1beta/models/nano-banana-fast:generateContent`

In this repository, the main production path was the draw API, not the Gemini-style API.

## 4. Main Code Paths Used In This Repo

### Core single-image runner
- [run_app81_grsai_mask_generation.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_grsai_mask_generation/run_app81_grsai_mask_generation.py)

This is the main reusable runner.

What it does:
- reads `GRSAI` API key from env var or `.env`
- prepares image upload as data URL
- resizes upload image if needed
- submits to `/v1/draw/nano-banana`
- polls `/v1/draw/result`
- downloads final generated image
- performs local cleanup on the generated mask
- writes:
  - prompt
  - raw submit response
  - poll response
  - task manifest
  - generated mask
  - flat mask
  - overlays

### Simple single-image Nano Banana segmentation runner
- [run_single_grsai_cystic_organoid_mask.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_grsai_mask_generation/run_single_grsai_cystic_organoid_mask.py)

Used for simple one-image organoid segmentation experiments.

### Batch stitched-view runner
- [run_batch_grsai_examples_stitched_views.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_grsai_mask_generation/run_batch_grsai_examples_stitched_views.py)

Used when one field is represented as:
- left raw brightfield panel
- upper-right enhanced panel
- lower-right boundary panel

The prompt tells Nano Banana to use all views for reasoning but only draw mask in the raw panel.

### 3x3 stitched-collage batch runner with `nano-banana-2`
- [run_app81_stitched_replicate1_nanobanana2_batch.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_grsai_mask_generation/run_app81_stitched_replicate1_nanobanana2_batch.py)

Used for the 8-panel-plus-blank 3x3 collage workflow.

This is the best reference if another model needs to understand how we used `nano-banana-2` on stitched collages.

### Stitched-image creation helpers
- [create_app81_density_stitch_inputs.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_grsai_mask_generation/create_app81_density_stitch_inputs.py)
- [create_app81_density_stitch_inputs_replicates.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_grsai_mask_generation/create_app81_density_stitch_inputs_replicates.py)
- [run_grsai_stitched_collage_examples.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_grsai_mask_generation/run_grsai_stitched_collage_examples.py)

### Panel merge / targeted correction helpers
- [merge_stitched_panel_mask.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_grsai_mask_generation/merge_stitched_panel_mask.py)
- [export_final_app81_stitched_to_single_images.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_grsai_mask_generation/export_final_app81_stitched_to_single_images.py)

These were used to merge Cellpose and Nano Banana panel-level results and then export final single-image masks.

### Hybrid OpenAI + Nano Banana experiment
- [run_openai_grsai_hybrid_mask_generation.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/openai_image_mask_generation/run_openai_grsai_hybrid_mask_generation.py)

This is not the main final workflow, but it is relevant if another model wants an example of chaining models.

## 5. Prompt And Reference Materials Used Here

### General organoid masking guidance
- [nanobanana_organoid_mask_prompt_guidance_2026-04-11.md](/home/lachlan/ProjectsLFS/Zhengyu/references/nanobanana_organoid_mask_prompt_guidance_2026-04-11.md)

This is the best prompt-design reference for organoid segmentation in this repo.

It explains:
- how to describe organoids positively
- how to reject pale droplets and faint rings
- why texture and density matter more than just round shape

### Overlap-aware instance prompt
- [grsai_overlap_instance_segmentation_prompt_2026-04-10.md](/home/lachlan/ProjectsLFS/Zhengyu/references/grsai_overlap_instance_segmentation_prompt_2026-04-10.md)

Useful if another model needs overlapping-instance logic rather than simple solid-instance masks.

### Prompt overrides used in stitched runs
- [app81_replicate1_stitched_prompt_overrides_v2.json](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_grsai_mask_generation/app81_replicate1_stitched_prompt_overrides_v2.json)
- [app81_grsai_prompt_overrides_five_examples_v1.json](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_grsai_mask_generation/app81_grsai_prompt_overrides_five_examples_v1.json)
- [app81_grsai_prompt_overrides_low_v1.json](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_grsai_mask_generation/app81_grsai_prompt_overrides_low_v1.json)

These show how prompt adjustments were applied per image or per collage.

## 6. Real Run Artifacts That Show How We Actually Used Nano Banana

### Early single-image / five-example batch experiments
Saved under archived test outputs, for example:
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/archived/test_app81/`

Notable folders include:
- `test_app81_grsai_only_cystic_v3_low_examples_nanobanana2`
- `test_app81_grsai_only_cystic_v7_five_examples_nanobanana2_batch_round_cystic`
- `test_app81_grsai_only_cystic_v8_five_examples_nanobanana2_batch_guidance_prompt`

These folders typically contain:
- `prompt.txt`
- `task_manifest.json`
- generated masks
- overlays
- batch registry / summary files

### Main stitched App81 Nano Banana run
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/archived/app81_density_stitched/app81_density_stitched_masks_v1_replicate1_nanobanana2`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/archived/app81_density_stitched/app81_density_stitched_masks_v2_replicate1_nanobanana2_custom_prompts`

These are important because they show:
- the stitched-collage approach
- the full batch task registry
- prompt text actually used on the 3x3 collages

### Targeted Nano Banana refinements on top of Cellpose
Saved under:
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/archived/app81_density_stitched/app81_density_stitched_cellpose_v5_all_batches_all_replicates_4x_diameter/results/...`

Important examples:
- `high_batch_1_replicate_02_10x_stitched/nanobanana_refine_r3c2_large_organoid_v2_preserve_mask`
- `high_batch_2_replicate_01_10x_stitched/nanobanana_refine_targeted_panels_v1`
- `high_batch_2_replicate_02_10x_stitched/nanobanana_refine_targeted_panels_v1`
- `middle_batch_2_replicate_01_10x_stitched/nanobanana_refine_targeted_panels_v1`
- `middle_batch_2_replicate_02_10x_stitched/nanobanana_refine_targeted_panels_v1`

These are the best examples if another model needs to learn the pattern:
- send original image
- send current segmentation mask / overlay as references
- ask Nano Banana to preserve most of the current segmentation
- apply only targeted corrections in named panels

## 7. Environment And Operational Requirements

Default Python env in this repo:
- `organoid`
- expected interpreter:
  - `/home/lachlan/miniconda3/envs/organoid/bin/python`

API key loading in code:
- env var `GRSAI`
- fallback `.env` entry with `GRSAI=...`

The main code expects:
- internet access
- valid GRS AI API key
- writable output directory

## 8. Minimal Operational Recipe For Another Model

If another model needs to run Nano Banana from this repo, the shortest reliable recipe is:

1. Use the API docs above.
2. Use this runner first:
   - [run_app81_grsai_mask_generation.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_grsai_mask_generation/run_app81_grsai_mask_generation.py)
3. Set:
   - host: `https://grsaiapi.com`
   - model: `nano-banana-2` or `nano-banana-fast`
4. Send:
   - one or more images in `urls`
   - a strong explicit prompt
5. Save:
   - prompt
   - task id
   - submit response
   - final poll response
   - generated output paths
6. If doing edit/refinement rather than fresh generation:
   - send original image
   - send current mask or overlay as references
   - instruct the model to preserve the good parts and fix only named regions

## 9. How To Adapt This For A Book Cover

The same Nano Banana API can be used for book-cover generation.

The API does not change.
Only the prompt and references change.

### Book cover request pattern

Use the same endpoint:
- `POST https://grsaiapi.com/v1/draw/nano-banana`

Example body:
```json
{
  "model": "nano-banana-2",
  "prompt": "Design a clean, modern nonfiction book cover about organoid engineering. Minimal layout, strong focal illustration, editorial typography space, white and deep blue palette, premium scientific publishing feel, front cover only, no watermark.",
  "aspectRatio": "2:3",
  "imageSize": "2K",
  "webHook": "-1",
  "shutProgress": false,
  "urls": []
}
```

### If using references for book cover

You can attach:
- existing cover references
- palette references
- scientific illustration references
- author photo or logo assets

### Important distinction

Most code in this repository is segmentation-oriented.
That means:
- it is good for API mechanics
- it is good for task-id polling and result handling
- it is not a ready-made book-cover pipeline

For a book cover, another model should reuse:
- the API mechanics
- task submission and polling
- result saving structure

But it should replace:
- segmentation prompts
- mask cleanup logic
- overlay generation logic

## 10. Recommended Files To Give Another Model First

If another model only needs the minimum useful set, start with these:

Docs:
- [grsai_nano_banana_api_documentation_2026-04-10.md](/home/lachlan/ProjectsLFS/Zhengyu/references/grsai_nano_banana_api_documentation_2026-04-10.md)
- [nanobanana_organoid_mask_prompt_guidance_2026-04-11.md](/home/lachlan/ProjectsLFS/Zhengyu/references/nanobanana_organoid_mask_prompt_guidance_2026-04-11.md)

Core code:
- [run_app81_grsai_mask_generation.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_grsai_mask_generation/run_app81_grsai_mask_generation.py)
- [run_app81_stitched_replicate1_nanobanana2_batch.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_grsai_mask_generation/run_app81_stitched_replicate1_nanobanana2_batch.py)
- [merge_stitched_panel_mask.py](/home/lachlan/ProjectsLFS/Zhengyu/analysis-tools/app81_grsai_mask_generation/merge_stitched_panel_mask.py)

Real usage examples:
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/archived/app81_density_stitched/app81_density_stitched_masks_v2_replicate1_nanobanana2_custom_prompts/`
- `/home/lachlan/ProjectsLFS/Zhengyu/analysis-output/archived/app81_density_stitched/app81_density_stitched_cellpose_v5_all_batches_all_replicates_4x_diameter/results/`

## 11. Bottom Line

For another model:
- use the saved API docs in `references/`
- use `run_app81_grsai_mask_generation.py` as the main API implementation reference
- use the archived stitched Nano Banana runs as prompt-and-output examples
- use prompt guidance docs for segmentation tasks
- for a book cover, keep the same API mechanics but replace the segmentation prompt with a creative editorial-cover prompt

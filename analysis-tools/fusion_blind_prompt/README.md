# Fusion Blind Prompt Tool

This prompt tool analyzes a blinded microscopy image set without exposing date or condition metadata.

## Design
- converts blinded TIFFs to PNG in an isolated temp workspace
- builds a contact sheet labeled only by UID
- attaches the contact sheet plus all individual images to `codex exec`
- uses a strict JSON schema
- explicitly warns the model about the known fusion-analysis pitfalls:
  - large irregular fused masses are valid organoid structures
  - fusion is confounded with growth and differentiation
  - the cohort must be compared jointly, not one image at a time only

## Usage
```bash
analysis-tools/fusion_blind_prompt/run_blind_fusion_set_prompt.sh \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001 \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001/blind_fusion_analysis.json \
  /home/lachlan/ProjectsLFS/Zhengyu/analysis-output/fusion-analysis-test/set_001/blind_fusion_prompt.txt
```

## Input visibility
The model should only see:
- the blinded UID images
- the contact sheet built from those UID images
- the prompt text

It should not see:
- date folders
- concentration folders
- internal mapping files

## Main outputs
- `blind_fusion_analysis.json`
- optional saved prompt text for audit/debugging

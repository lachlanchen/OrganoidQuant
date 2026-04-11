# Nano Banana Organoid Mask Prompt Guidance

This note documents a prompt strategy for using Nano Banana to generate organoid masks from brightfield or phase-contrast microscopy images while avoiding false masking of pale hydrogel or Matrigel droplets.

## Core Masking Prompt

```text
Generate a precise black-and-white segmentation mask for the biological organoids in this brightfield microscopy image. White should represent the organoids, and black should represent the background.

TARGET TO MASK:
Mask all dense, textured, multicellular structures. These range from small compact cellular clusters to large complex lobular masses. Look for areas with granular internal texture, highly irregular and thick phase-contrast boundaries, and internal cavities or lumens. Include both small developing cysts and large fully formed organoids.

STRICT EXCLUSIONS:
Strictly ignore the large pale transparent droplets such as hydrogel or Matrigel domes that encapsulate the cells. Do not mask the thin, faint, low-contrast outer boundary lines of these large pale ovals. Ignore smooth, uniform, textureless transparent regions, and ignore minor out-of-focus background debris or dust artifacts. Only mask the actual dense cellular material.
```

## Why This Prompt Works

### Texture Over Shape

The prompt emphasizes granular internal texture and dense multicellular structure instead of simply looking for circles or enclosed boundaries. This helps the model focus on real cellular material rather than smooth background structures.

### Boundary Contrast

The prompt distinguishes between:

- thick, dark, high-contrast organoid boundaries
- thin, faint, low-contrast pale droplet boundaries

This is important because the hydrogel or Matrigel dome can surround real organoids without being biological tissue itself.

### Wide Size Range

The prompt explicitly allows a large size range:

- small compact cell clusters
- moderate cystic organoids
- large complex mature organoids

This reduces the chance that the model only keeps the largest object in the frame and misses smaller real organoids nearby.

### Background Artifact Rejection

The prompt also excludes:

- out-of-focus debris
- dust-like artifacts
- smooth transparent background structures

This helps produce a cleaner mask.

## Appearance of Organoids in These Images

Based on these microscopy images, the organoids usually show the following visual properties.

### Shape And Morphology

Early-stage organoids often appear as simple round or oval cysts.

More mature organoids become:

- irregular
- lobulated
- asymmetric
- folded

### Texture And Density

Unlike the smooth pale background or hydrogel dome, organoids usually have:

- granular texture
- rough internal appearance
- dense cellular structure

Thicker mature regions can become dark and opaque because they block transmitted light.

### Edges And Boundaries

Under brightfield or phase-contrast microscopy, true organoids often have:

- thick dark boundaries
- strong local contrast
- well-defined cellular walls

This differs from pale droplet boundaries, which are often thin, faint, and low contrast.

### Internal Structures

Many organoids contain lumens or cavity-like regions. These may appear as:

- lighter hollow centers
- enclosed internal spaces
- mixed light and dark internal regions

Their interiors are often heterogeneous rather than uniform.

### Size Variance

Real organoids in one field can vary greatly in size, from:

- small compact clusters
- moderate cystic organoids
- large complex tissue masses

## Practical Recognition Rule

In these images, the structures most likely to be true organoids are:

- dense
- high-contrast
- granular
- thick-walled
- biologically irregular or cystic multicellular bodies

The structures most likely to be false positives are:

- large pale transparent domes
- thin faint enclosing rings
- smooth hollow droplet boundaries
- minor floating debris

## Short Summary

When prompting Nano Banana for organoid masking, the safest strategy is:

- positively describe organoids as dense textured cellular structures
- explicitly allow both small cysts and large mature organoids
- explicitly reject pale transparent droplet domes and their faint outer boundaries
- reject smooth uniform background and minor debris


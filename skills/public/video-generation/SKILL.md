---
name: video-generation
description: Use this skill when the user requests to generate, create, or imagine videos. Supports structured prompts and reference image for guided generation.
---

# Video Generation Skill

## Overview

This skill generates high-quality videos using structured prompts and a local ComfyUI instance (Wan workflow).

The default workflow has been upgraded to support **long-form video generation** (10 seconds by default, extendable) via Kijai's `ComfyUI-WanVideoWrapper` with temporal sliding windows. It is optimized for stability on consumer GPUs (e.g., RTX 3060 12GB) — low VRAM usage, no OOM risk, at the cost of slower generation speed.

The legacy 2-second workflow (`text_to_video_wan.json`) is preserved and can be restored by deleting or renaming the long workflow file.

## Core Capabilities

- Create structured JSON prompts for AIGC video generation
- Support reference image as guidance or the first/last frame of the video
- Generate videos through automated Python script execution

## Workflow

### Step 1: Understand Requirements

When a user requests video generation, identify:

- Subject/content: What should be in the image
- Style preferences: Art style, mood, color palette
- Technical specs: Aspect ratio, composition, lighting
- Reference image: Any image to guide generation
- You don't need to check the folder under `/mnt/user-data`

### Step 2: Create Structured Prompt

Generate a structured JSON file in `/mnt/user-data/workspace/` with naming pattern: `{descriptive-name}.json`

### Step 3: Execute Generation

Call the Python script:
```bash
python /mnt/skills/public/video-generation/scripts/generate.py \
  --prompt-file /mnt/user-data/workspace/prompt-file.json \
  --output-file /mnt/user-data/outputs/generated-video.mp4 \
  --aspect-ratio 16:9 \
  --duration 10.0
```

Environment variables:

- `COMFYUI_BASE_URL`: URL of the local ComfyUI API (default: `http://host.docker.internal:8188`)

[!NOTE]
Reference images are not supported by the current Wan workflow and will be ignored if provided.

Parameters:

- `--prompt-file`: Absolute path to JSON prompt file (required)
- `--reference-images`: Absolute paths to reference image (optional)
- `--output-file`: Absolute path to output video file (required)
- `--aspect-ratio`: Aspect ratio of the generated video (optional, default: 16:9)
- `--duration`: Target video duration in seconds (optional, default: 10.0)

[!NOTE]
Do NOT read the python file, instead just call it with the parameters.

## Video Generation Example

User request: "Generate a short video clip depicting the opening scene from "The Chronicles of Narnia: The Lion, the Witch and the Wardrobe"

Step 1: Search for the opening scene of "The Chronicles of Narnia: The Lion, the Witch and the Wardrobe" online

Step 2: Create a JSON prompt file with the following content:

```json
{
  "title": "The Chronicles of Narnia - Train Station Farewell",
  "background": {
    "description": "World War II evacuation scene at a crowded London train station. Steam and smoke fill the air as children are being sent to the countryside to escape the Blitz.",
    "era": "1940s wartime Britain",
    "location": "London railway station platform"
  },
  "characters": ["Mrs. Pevensie", "Lucy Pevensie"],
  "camera": {
    "type": "Close-up two-shot",
    "movement": "Static with subtle handheld movement",
    "angle": "Profile view, intimate framing",
    "focus": "Both faces in focus, background soft bokeh"
  },
  "dialogue": [
    {
      "character": "Mrs. Pevensie",
      "text": "You must be brave for me, darling. I'll come for you... I promise."
    },
    {
      "character": "Lucy Pevensie",
      "text": "I will be, mother. I promise."
    }
  ],
  "audio": [
    {
      "type": "Train whistle blows (signaling departure)",
      "volume": 1
    },
    {
      "type": "Strings swell emotionally, then fade",
      "volume": 0.5
    },
    {
      "type": "Ambient sound of the train station",
      "volume": 0.5
    }
  ]
}
```

Step 3: Use the image-generation skill to generate the reference image

Load the image-generation skill and generate a single reference image `narnia-farewell-scene-01.jpg` according to the skill.

Step 4: Use the generate.py script to generate the video
```bash
python /mnt/skills/public/video-generation/scripts/generate.py \
  --prompt-file /mnt/user-data/workspace/narnia-farewell-scene.json \
  --reference-images /mnt/user-data/outputs/narnia-farewell-scene-01.jpg \
  --output-file /mnt/user-data/outputs/narnia-farewell-scene-01.mp4 \
  --aspect-ratio 16:9 \
  --duration 10.0
```
> Do NOT read the python file, just call it with the parameters.

## Setup Requirements (One-time)

### 1. Install ComfyUI Custom Nodes

Open ComfyUI Manager and install:
- **`ComfyUI-WanVideoWrapper`** (by kijai) — core nodes for long video generation
- **`ComfyUI-VideoHelperSuite`** — recommended video utility nodes

Restart ComfyUI after installation.

### 2. Model File Location

The long-video workflow expects the diffusion model in a different folder than the legacy workflow:

| Model | Required location |
|-------|------------------|
| `wan2.1_t2v_1.3B_fp16.safetensors` | `ComfyUI/models/diffusion_models/` |
| `wan_2.1_vae.safetensors` | `ComfyUI/models/vae/` (no change) |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `ComfyUI/models/clip/` (no change) |

If your 1.3B model is currently in `models/unet/` or `models/checkpoints/`, copy or symlink it to `models/diffusion_models/`.

### 3. Switching Back to Legacy Workflow

To restore the original 2-second video behavior, simply delete or rename:
```
skills/public/video-generation/text_to_video_wan_long.json
```
`generate.py` will automatically fall back to `text_to_video_wan.json`.

## Output Handling

After generation:

- Videos are typically saved in `/mnt/user-data/outputs/`
- Share generated videos (come first) with user as well as generated image if applicable, using `present_files` tool
- Provide brief description of the generation result
- Offer to iterate if adjustments needed

## Notes

- Always use English for prompts regardless of user's language
- JSON format ensures structured, parsable prompts
- Reference image enhance generation quality significantly
- Iterative refinement is normal for optimal results

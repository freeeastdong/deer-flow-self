import json
import os
import random
import time
import uuid

import requests
from PIL import Image


# ---------------------------------------------------------------------------
# Default ComfyUI workflow (txt2img with KSampler).
# Used when COMFYUI_WORKFLOW_PATH is not set and no custom workflow is found.
# ---------------------------------------------------------------------------
DEFAULT_WORKFLOW = {
    "1": {
        "inputs": {"ckpt_name": "PLEASE_SET_VIA_COMFYUI_CHECKPOINT_ENV"},
        "class_type": "CheckpointLoaderSimple",
        "_meta": {"title": "Load Checkpoint"},
    },
    "2": {
        "inputs": {"text": "", "clip": ["1", 1]},
        "class_type": "CLIPTextEncode",
        "_meta": {"title": "CLIP Text Encode (Positive)"},
    },
    "3": {
        "inputs": {"text": "", "clip": ["1", 1]},
        "class_type": "CLIPTextEncode",
        "_meta": {"title": "CLIP Text Encode (Negative)"},
    },
    "4": {
        "inputs": {"width": 1344, "height": 768, "batch_size": 1},
        "class_type": "EmptyLatentImage",
        "_meta": {"title": "Empty Latent Image"},
    },
    "5": {
        "inputs": {
            "seed": 0,
            "steps": 25,
            "cfg": 7.0,
            "sampler_name": "euler_ancestral",
            "scheduler": "normal",
            "denoise": 1.0,
            "model": ["1", 0],
            "positive": ["2", 0],
            "negative": ["3", 0],
            "latent_image": ["4", 0],
        },
        "class_type": "KSampler",
        "_meta": {"title": "KSampler"},
    },
    "6": {
        "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
        "class_type": "VAEDecode",
        "_meta": {"title": "VAE Decode"},
    },
    "7": {
        "inputs": {"filename_prefix": "deerflow", "images": ["6", 0]},
        "class_type": "SaveImage",
        "_meta": {"title": "Save Image"},
    },
}


# ---------------------------------------------------------------------------
# Aspect-ratio → pixel dimensions (multiples of 8 for SD compatibility)
# ---------------------------------------------------------------------------
ASPECT_RATIO_MAP = {
    "16:9": (1344, 768),
    "4:3": (1024, 768),
    "3:2": (1152, 768),
    "2:3": (768, 1152),
    "1:1": (1024, 1024),
    "9:16": (768, 1344),
}


def validate_image(image_path: str) -> bool:
    """Validate that an image file can be opened and is not corrupted."""
    try:
        with Image.open(image_path) as img:
            img.verify()
        with Image.open(image_path) as img:
            img.load()
        return True
    except Exception as e:
        print(f"Warning: Image '{image_path}' is invalid or corrupted: {e}")
        return False


def get_dimensions(aspect_ratio: str) -> tuple[int, int]:
    """Return (width, height) for the given aspect ratio."""
    return ASPECT_RATIO_MAP.get(aspect_ratio, (1344, 768))


def build_prompt_text(prompt_data: dict) -> tuple[str, str]:
    """Extract positive / negative prompt strings from the JSON prompt file."""
    if not isinstance(prompt_data, dict):
        return str(prompt_data), ""

    negative = prompt_data.pop("negative_prompt", "") if isinstance(prompt_data, dict) else ""

    if "prompt" in prompt_data:
        positive = str(prompt_data["prompt"])
    else:
        parts = [f"{k}: {v}" for k, v in prompt_data.items()]
        positive = "\n".join(parts)

    return positive, negative


def upload_image_to_comfyui(base_url: str, image_path: str) -> dict:
    """Upload a local image to ComfyUI's input folder."""
    with open(image_path, "rb") as f:
        resp = requests.post(
            f"{base_url}/upload/image",
            files={"image": (os.path.basename(image_path), f, "image/jpeg")},
            data={"type": "input"},
        )
    resp.raise_for_status()
    return resp.json()


def prepare_workflow(
    workflow: dict,
    positive_prompt: str,
    negative_prompt: str,
    aspect_ratio: str,
    checkpoint: str | None = None,
    reference_images_info: list[dict] | None = None,
) -> dict:
    """Mutate a copy of the workflow with prompt, size, checkpoint and references."""
    wf = json.loads(json.dumps(workflow))  # deep copy

    # ------------------------------------------------------------------
    # 1. Prompt injection
    # ------------------------------------------------------------------
    string_nodes = []
    clip_positive = None
    clip_negative = None

    for node_id, node in wf.items():
        class_type = node.get("class_type", "")
        title = node.get("_meta", {}).get("title", "")

        if class_type == "PrimitiveStringMultiline":
            string_nodes.append(node_id)
        elif class_type == "CLIPTextEncode":
            text_input = node["inputs"].get("text")
            if isinstance(text_input, str):  # direct text, not a reference/link
                title_lower = title.lower()
                if "negative" in title_lower:
                    clip_negative = node_id
                elif "positive" in title_lower:
                    clip_positive = node_id

    # Inject positive prompt
    if string_nodes:
        for node_id in string_nodes:
            wf[node_id]["inputs"]["value"] = positive_prompt
    elif clip_positive:
        wf[clip_positive]["inputs"]["text"] = positive_prompt

    # Inject negative prompt
    if clip_negative:
        wf[clip_negative]["inputs"]["text"] = negative_prompt

    # ------------------------------------------------------------------
    # 2. Dimensions
    # ------------------------------------------------------------------
    width, height = get_dimensions(aspect_ratio)

    # Try PrimitiveInt nodes (Flux2 / advanced workflow style)
    width_node = None
    height_node = None

    for node_id, node in wf.items():
        class_type = node.get("class_type", "")
        title = node.get("_meta", {}).get("title", "")
        if class_type == "PrimitiveInt":
            title_lower = title.lower()
            if title_lower in ("width", "宽", "宽度"):
                width_node = node_id
            elif title_lower in ("height", "高", "高度"):
                height_node = node_id

    if width_node:
        wf[width_node]["inputs"]["value"] = width
    if height_node:
        wf[height_node]["inputs"]["value"] = height

    # Also try direct latent image nodes (standard SD style)
    for node_id, node in wf.items():
        class_type = node.get("class_type", "")
        if class_type in ("EmptyLatentImage", "EmptyFlux2LatentImage"):
            w = node["inputs"].get("width")
            h = node["inputs"].get("height")
            if isinstance(w, (int, float)):
                node["inputs"]["width"] = width
            if isinstance(h, (int, float)):
                node["inputs"]["height"] = height

    # ------------------------------------------------------------------
    # 3. Randomise seed
    # ------------------------------------------------------------------
    for node in wf.values():
        class_type = node.get("class_type", "")
        if class_type == "RandomNoise" and "noise_seed" in node["inputs"]:
            node["inputs"]["noise_seed"] = random.randint(0, 2**32 - 1)
        elif class_type == "KSampler" and "seed" in node["inputs"]:
            node["inputs"]["seed"] = random.randint(0, 2**32 - 1)

    # ------------------------------------------------------------------
    # 4. Reference images
    # ------------------------------------------------------------------
    load_image_nodes = [
        nid for nid, n in wf.items() if n.get("class_type") == "LoadImage"
    ]
    if reference_images_info and load_image_nodes:
        for i, node_id in enumerate(load_image_nodes):
            if i < len(reference_images_info):
                wf[node_id]["inputs"]["image"] = reference_images_info[i]["name"]
            else:
                break

    # ------------------------------------------------------------------
    # 5. Checkpoint / model override
    # ------------------------------------------------------------------
    if checkpoint:
        for node in wf.values():
            if node.get("class_type") == "CheckpointLoaderSimple":
                node["inputs"]["ckpt_name"] = checkpoint

    return wf


def queue_prompt(base_url: str, workflow: dict, client_id: str) -> str:
    """Submit a workflow to ComfyUI and return the prompt_id."""
    resp = requests.post(
        f"{base_url}/prompt",
        json={"prompt": workflow, "client_id": client_id},
    )
    resp.raise_for_status()
    return resp.json()["prompt_id"]


def get_history(base_url: str, prompt_id: str) -> dict:
    """Fetch the execution history for a given prompt_id."""
    resp = requests.get(f"{base_url}/history/{prompt_id}")
    resp.raise_for_status()
    return resp.json()


def download_image(base_url: str, image_info: dict, output_path: str):
    """Download a generated image from ComfyUI's output folder."""
    params = {
        "filename": image_info["filename"],
        "subfolder": image_info.get("subfolder", ""),
        "type": image_info.get("type", "output"),
    }
    resp = requests.get(f"{base_url}/view", params=params, stream=True)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def generate_image(
    prompt_file: str,
    reference_images: list[str],
    output_file: str,
    aspect_ratio: str = "16:9",
) -> str:
    # ------------------------------------------------------------------
    # 1. Read the structured JSON prompt
    # ------------------------------------------------------------------
    with open(prompt_file, "r", encoding="utf-8") as f:
        prompt_data = json.load(f)

    positive_prompt, negative_prompt = build_prompt_text(prompt_data)

    # ------------------------------------------------------------------
    # 2. Validate reference images
    # ------------------------------------------------------------------
    valid_refs = []
    for ref_img in reference_images:
        if validate_image(ref_img):
            valid_refs.append(ref_img)
        else:
            print(f"Skipping invalid reference image: {ref_img}")

    if len(valid_refs) < len(reference_images):
        print(
            f"Note: {len(reference_images) - len(valid_refs)} reference image(s) skipped."
        )

    # ------------------------------------------------------------------
    # 3. ComfyUI configuration
    # ------------------------------------------------------------------
    base_url = os.getenv("COMFYUI_BASE_URL", "http://host.docker.internal:8188").rstrip("/")
    workflow_path = os.getenv("COMFYUI_WORKFLOW_PATH")
    checkpoint = os.getenv("COMFYUI_CHECKPOINT")

    # If COMFYUI_WORKFLOW_PATH is not set, look for the custom workflow next to this script
    if not workflow_path:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        custom_workflow = os.path.join(script_dir, "..", "image_flux2_klein_text_to_image.json")
        if os.path.exists(custom_workflow):
            workflow_path = custom_workflow

    # Load workflow JSON
    if workflow_path and os.path.exists(workflow_path):
        with open(workflow_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)
    else:
        if workflow_path:
            print(f"Warning: Workflow not found at {workflow_path}, using default.")
        workflow = DEFAULT_WORKFLOW
        if not checkpoint:
            return (
                "COMFYUI_CHECKPOINT environment variable is required when using the default workflow. "
                "Example: export COMFYUI_CHECKPOINT=sd_xl_base_1.0.safetensors"
            )

    # ------------------------------------------------------------------
    # 4. Upload reference images to ComfyUI
    # ------------------------------------------------------------------
    ref_images_info: list[dict] = []
    for ref_path in valid_refs:
        try:
            info = upload_image_to_comfyui(base_url, ref_path)
            ref_images_info.append(info)
            print(f"Uploaded reference image: {info['name']}")
        except Exception as e:
            print(f"Warning: failed to upload {ref_path}: {e}")

    # ------------------------------------------------------------------
    # 5. Build and submit workflow
    # ------------------------------------------------------------------
    wf = prepare_workflow(
        workflow,
        positive_prompt,
        negative_prompt,
        aspect_ratio,
        checkpoint=checkpoint,
        reference_images_info=ref_images_info,
    )

    client_id = str(uuid.uuid4())
    prompt_id = queue_prompt(base_url, wf, client_id)
    print(f"Queued ComfyUI job: {prompt_id}")

    # ------------------------------------------------------------------
    # 6. Poll until completion (max ~10 min)
    # ------------------------------------------------------------------
    max_polls = 1200
    for _ in range(max_polls):
        try:
            history = get_history(base_url, prompt_id)
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_output in outputs.values():
                    images = node_output.get("images", [])
                    if images:
                        download_image(base_url, images[0], output_file)
                        return f"Successfully generated image to {output_file}"
                return "ComfyUI finished but produced no images."
        except Exception as e:
            print(f"Polling error: {e}")
        time.sleep(0.5)

    return "ComfyUI generation timed out."


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate images using a local ComfyUI instance"
    )
    parser.add_argument(
        "--prompt-file",
        required=True,
        help="Absolute path to JSON prompt file",
    )
    parser.add_argument(
        "--reference-images",
        nargs="*",
        default=[],
        help="Absolute paths to reference images (space-separated)",
    )
    parser.add_argument(
        "--output-file",
        required=True,
        help="Output path for generated image",
    )
    parser.add_argument(
        "--aspect-ratio",
        required=False,
        default="16:9",
        help="Aspect ratio of the generated image (default: 16:9)",
    )

    args = parser.parse_args()

    try:
        print(
            generate_image(
                args.prompt_file,
                args.reference_images,
                args.output_file,
                args.aspect_ratio,
            )
        )
    except Exception as e:
        print(f"Error while generating image: {e}")

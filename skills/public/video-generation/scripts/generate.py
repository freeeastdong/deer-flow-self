import json
import os
import random
import time
import uuid

import requests


# ---------------------------------------------------------------------------
# Aspect-ratio → pixel dimensions for Wan video generation
# ---------------------------------------------------------------------------
ASPECT_RATIO_MAP = {
    "16:9": (832, 480),
    "4:3": (640, 480),
    "3:2": (720, 480),
    "2:3": (480, 720),
    "1:1": (480, 480),
    "9:16": (480, 832),
}

FPS = 16


def get_dimensions(aspect_ratio: str) -> tuple[int, int]:
    return ASPECT_RATIO_MAP.get(aspect_ratio, (832, 480))


def queue_prompt(base_url: str, workflow: dict, client_id: str) -> str:
    resp = requests.post(
        f"{base_url}/prompt",
        json={"prompt": workflow, "client_id": client_id},
    )
    resp.raise_for_status()
    return resp.json()["prompt_id"]


def get_history(base_url: str, prompt_id: str) -> dict:
    resp = requests.get(f"{base_url}/history/{prompt_id}")
    resp.raise_for_status()
    return resp.json()


def download_file(base_url: str, file_info: dict, output_path: str):
    params = {
        "filename": file_info["filename"],
        "subfolder": file_info.get("subfolder", ""),
        "type": file_info.get("type", "output"),
    }
    resp = requests.get(f"{base_url}/view", params=params, stream=True)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def prepare_workflow(
    workflow: dict,
    positive_prompt: str,
    negative_prompt: str,
    aspect_ratio: str,
    duration: float = 10.0,
) -> dict:
    """Inject prompts, dimensions and duration into the Wan video workflow."""
    wf = json.loads(json.dumps(workflow))
    width, height = get_dimensions(aspect_ratio)
    num_frames = int(FPS * duration)

    for node in wf.values():
        class_type = node.get("class_type", "")
        title = node.get("_meta", {}).get("title", "")

        if class_type == "CLIPTextEncode":
            text_input = node["inputs"].get("text", "")
            if isinstance(text_input, str):
                title_lower = title.lower()
                if "negative" in title_lower:
                    node["inputs"]["text"] = negative_prompt
                elif "positive" in title_lower:
                    node["inputs"]["text"] = positive_prompt

        elif class_type == "EmptyHunyuanLatentVideo":
            # Legacy native workflow (short video, fixed length)
            node["inputs"]["width"] = width
            node["inputs"]["height"] = height

        elif class_type == "WanVideoEmptyEmbeds":
            # Kijai Wrapper long-video workflow
            node["inputs"]["width"] = width
            node["inputs"]["height"] = height
            node["inputs"]["length"] = num_frames

        elif class_type == "KSampler" and "seed" in node["inputs"]:
            # Legacy native workflow
            node["inputs"]["seed"] = random.randint(0, 2**32 - 1)

        elif class_type == "WanVideoSampler" and "seed" in node["inputs"]:
            # Kijai Wrapper workflow
            node["inputs"]["seed"] = random.randint(0, 2**32 - 1)

    return wf


def generate_video(
    prompt_file: str,
    reference_images: list[str],
    output_file: str,
    aspect_ratio: str = "16:9",
    duration: float = 10.0,
) -> str:
    # ------------------------------------------------------------------
    # 1. Read the structured JSON prompt
    # ------------------------------------------------------------------
    with open(prompt_file, "r", encoding="utf-8") as f:
        prompt_data = json.load(f)

    if isinstance(prompt_data, dict):
        positive_prompt = str(prompt_data.get("prompt", prompt_data))
        negative_prompt = str(prompt_data.pop("negative_prompt", "")) if isinstance(prompt_data, dict) else ""
    else:
        positive_prompt = str(prompt_data)
        negative_prompt = ""

    # ------------------------------------------------------------------
    # 2. Reference images (not supported by the current Wan workflow)
    # ------------------------------------------------------------------
    if reference_images:
        print(f"Warning: reference images are not supported by the current Wan workflow and will be ignored.")

    # ------------------------------------------------------------------
    # 3. ComfyUI configuration
    # ------------------------------------------------------------------
    base_url = os.getenv("COMFYUI_BASE_URL", "http://host.docker.internal:8188").rstrip("/")

    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Prefer the new long-video workflow; fall back to the legacy 2s workflow
    long_workflow_path = os.path.join(script_dir, "..", "text_to_video_wan_long.json")
    default_workflow_path = os.path.join(script_dir, "..", "text_to_video_wan.json")

    if os.path.exists(long_workflow_path):
        workflow_path = long_workflow_path
        print(f"Using long-video workflow: {workflow_path}")
    else:
        workflow_path = default_workflow_path
        print(f"Using legacy workflow: {workflow_path}")

    if not os.path.exists(workflow_path):
        return f"Workflow file not found: {workflow_path}"

    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    # ------------------------------------------------------------------
    # 4. Build and submit workflow
    # ------------------------------------------------------------------
    wf = prepare_workflow(workflow, positive_prompt, negative_prompt, aspect_ratio, duration)

    client_id = str(uuid.uuid4())
    prompt_id = queue_prompt(base_url, wf, client_id)
    print(f"Queued ComfyUI video job: {prompt_id} ({duration}s @ {aspect_ratio})")

    # ------------------------------------------------------------------
    # 5. Poll until completion
    #    Long videos on modest GPUs can take 30-60 minutes, so we allow
    #    up to ~90 minutes of polling.
    # ------------------------------------------------------------------
    max_polls = 10800  # ~90 minutes with 0.5s interval
    for _ in range(max_polls):
        try:
            history = get_history(base_url, prompt_id)
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_output in outputs.values():
                    # Try video outputs first
                    for key in ("video", "gifs", "images"):
                        items = node_output.get(key, [])
                        if items:
                            download_file(base_url, items[0], output_file)
                            return f"Successfully generated video to {output_file}"
                return "ComfyUI finished but produced no video."
        except Exception as e:
            print(f"Polling error: {e}")
        time.sleep(0.5)

    return "ComfyUI video generation timed out."


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate videos using a local ComfyUI instance (Wan workflow)"
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
        help="Output path for generated video",
    )
    parser.add_argument(
        "--aspect-ratio",
        required=False,
        default="16:9",
        help="Aspect ratio of the generated video (default: 16:9)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        required=False,
        default=10.0,
        help="Target video duration in seconds (default: 10.0)",
    )

    args = parser.parse_args()

    try:
        print(
            generate_video(
                args.prompt_file,
                args.reference_images,
                args.output_file,
                args.aspect_ratio,
                args.duration,
            )
        )
    except Exception as e:
        print(f"Error while generating video: {e}")

import base64
import os
import threading
from io import BytesIO
import requests

from modules.module_config import load_config, get_api_key
from modules.module_messageQue import queue_message

CONFIG = load_config()

# Conditional imports for heavy dependencies
Image = None
BlipProcessor = None
BlipForConditionalGeneration = None
torch = None
openai = None
CameraModule = None

try:
    from PIL import Image as _Image
    Image = _Image
except ImportError:
    pass

try:
    from transformers import BlipProcessor as _BlipProcessor, BlipForConditionalGeneration as _BlipModel
    BlipProcessor = _BlipProcessor
    BlipForConditionalGeneration = _BlipModel
except ImportError:
    pass

try:
    import torch as _torch
    torch = _torch
except ImportError:
    pass

try:
    import openai as _openai
    openai = _openai
except ImportError:
    pass

try:
    from modules.UI.module_ui_camera import CameraModule as _CameraModule
    CameraModule = _CameraModule
except ImportError:
    try:
        from UI.module_ui_camera import CameraModule as _CameraModule
        CameraModule = _CameraModule
    except ImportError:
        pass

# BLIP model state — guarded by _blip_lock
from pathlib import Path

DEVICE = None
if torch:
    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

MODEL_NAME = "Salesforce/blip-image-captioning-base"
CACHE_DIR = Path(__file__).resolve().parent.parent / "vision"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_blip_lock = threading.Lock()
_processor = None
_model = None


def initialize_blip():
    """Initialize BLIP model and processor (thread-safe)."""
    global _processor, _model
    if not CONFIG['VISION']['enabled']:
        return
    if BlipProcessor is None or BlipForConditionalGeneration is None or torch is None:
        queue_message("WARNING: BLIP dependencies not available (transformers, torch)")
        return
    with _blip_lock:
        if _processor is not None and _model is not None:
            return
        queue_message("INFO: Initializing BLIP model...")
        _processor = BlipProcessor.from_pretrained(
            MODEL_NAME,
            cache_dir=str(CACHE_DIR),
            backend="pil",
        )
        _model = BlipForConditionalGeneration.from_pretrained(MODEL_NAME, cache_dir=str(CACHE_DIR)).to(DEVICE)
        _model = torch.quantization.quantize_dynamic(_model, {torch.nn.Linear}, dtype=torch.qint8)
        queue_message("INFO: BLIP model initialized.")


def _to_base64(image_data):
    """Accept bytes or base64 string, always return base64 string."""
    if isinstance(image_data, (bytes, bytearray)):
        return base64.b64encode(image_data).decode('utf-8')
    return image_data  # already a base64 string


def _to_bytes(image_data):
    """Accept bytes or base64 string, always return bytes."""
    if isinstance(image_data, (bytes, bytearray)):
        return bytes(image_data)
    return base64.b64decode(image_data)


def _chat_completions_url(base_url, backend="openai"):
    """Build a chat-completions URL without duplicating an existing /v1."""
    base = str(base_url or "").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if backend == "deepinfra":
        if base.endswith("/v1/openai"):
            return f"{base}/chat/completions"
        return f"{base}/v1/openai/chat/completions"
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _uses_completion_token_limit(model):
    name = str(model or "").lower()
    return name.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4"))


def _extract_vision_reply(payload):
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in ("text", "output_text"):
                parts.append(str(item.get("text", "")))
        return " ".join(part for part in parts if part).strip()
    return str(content or "").strip()


def _post_vision_chat(api_url, api_key, model, prompt, image_data, max_tokens):
    """Send a multimodal chat request with model-compatible token controls."""
    b64 = _to_base64(image_data)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {
                "url": f"data:image/jpeg;base64,{b64}"
            }},
        ]}],
    }
    token_key = (
        "max_completion_tokens" if _uses_completion_token_limit(model) else "max_tokens"
    )
    payload[token_key] = int(max_tokens)

    response = requests.post(api_url, headers=headers, json=payload, timeout=30)
    if response.status_code == 400:
        detail = response.text[:1000]
        parameter_error = (
            "unsupported_parameter" in detail
            or "max_tokens" in detail
            or "max_completion_tokens" in detail
        )
        if parameter_error:
            alternate = (
                "max_tokens" if token_key == "max_completion_tokens"
                else "max_completion_tokens"
            )
            payload.pop(token_key, None)
            payload[alternate] = int(max_tokens)
            queue_message(
                f"WARNING: Vision model rejected {token_key}; retrying with {alternate}"
            )
            response = requests.post(api_url, headers=headers, json=payload, timeout=30)

    if not response.ok:
        queue_message(
            f"ERROR: Vision API returned {response.status_code}: "
            f"{response.text.strip()[:1000]}"
        )
    response.raise_for_status()
    description = _extract_vision_reply(response.json())
    if not description:
        raise RuntimeError("vision API returned an empty description")
    queue_message(f"Vision: {description}")
    return description


# --- Backend implementations ---

def _describe_blip(image_data, prompt):
    """Generate caption using local BLIP model."""
    global _processor, _model
    if _processor is None or _model is None:
        initialize_blip()
    if _processor is None or _model is None:
        return "Error: BLIP model not available"

    img_bytes = _to_bytes(image_data)
    raw_image = Image.open(BytesIO(img_bytes)).convert('RGB')
    inputs = _processor(raw_image, return_tensors="pt").to(DEVICE)
    outputs = _model.generate(**inputs, max_new_tokens=100, num_beams=2)
    caption = _processor.decode(outputs[0], skip_special_tokens=True)
    return caption


def _get_vision_settings():
    """Resolve API key, base URL, and model based on use_llm_backend toggle."""
    use_llm = CONFIG['VISION'].get('use_llm_backend', True)
    llm_backend = CONFIG['LLM']['llm_backend']

    if use_llm:
        # Use main LLM settings
        api_key = CONFIG['LLM']['api_key']
        base_url = CONFIG['LLM']['base_url']
        if llm_backend == "deepinfra":
            model = CONFIG['LLM']['openai_model']
        elif llm_backend == "grok":
            model = CONFIG['LLM']['grok_model']
        elif llm_backend == "openai":
            model = CONFIG['LLM']['openai_model']
        else:
            model = CONFIG['LLM']['other_model']
    else:
        # Use separate vision settings, fall back to LLM settings if blank
        api_key = os.environ.get('VISION_API_KEY', '') or CONFIG['LLM']['api_key']
        base_url = CONFIG['VISION'].get('base_url', '') or CONFIG['LLM']['base_url']
        model = CONFIG['VISION'].get('vision_model', '')
        if not model:
            # Fall back to LLM model
            if llm_backend == "openai":
                model = CONFIG['LLM']['openai_model']
            elif llm_backend == "grok":
                model = CONFIG['LLM']['grok_model']
            elif llm_backend == "deepinfra":
                model = CONFIG['LLM']['openai_model']
            else:
                model = CONFIG['LLM']['other_model']

    return api_key, base_url, model


def _describe_llm(image_data, prompt):
    """Send image to the configured LLM backend for vision."""
    api_key, base_url, model = _get_vision_settings()
    if not api_key:
        return "Error: No API key configured for vision"
    if not base_url:
        return "Error: No base_url configured for vision"
    max_tokens = int(CONFIG['VISION'].get('vision_max_tokens', 150))
    llm_backend = CONFIG['LLM']['llm_backend']

    url = _chat_completions_url(base_url, llm_backend)
    return _post_vision_chat(
        url,
        api_key,
        model,
        prompt,
        image_data,
        max_tokens,
    )


def _describe_openai(image_data, prompt, model_override=None):
    """Send image to OpenAI vision API."""
    use_llm = CONFIG['VISION'].get('use_llm_backend', True)

    if use_llm:
        api_key = os.getenv('OPENAI_API_KEY') or CONFIG['LLM']['api_key']
        api_url = "https://api.openai.com/v1/chat/completions"
        model = model_override or CONFIG['VISION'].get('vision_model', '') or 'gpt-4o-mini'
    else:
        api_key = os.environ.get('VISION_API_KEY', '') or os.getenv('OPENAI_API_KEY') or CONFIG['LLM']['api_key']
        vision_base = CONFIG['VISION'].get('base_url', '')
        api_url = (
            _chat_completions_url(vision_base)
            if vision_base
            else "https://api.openai.com/v1/chat/completions"
        )
        model = model_override or CONFIG['VISION'].get('vision_model', '') or 'gpt-4o-mini'

    if not api_key:
        return "Error: No API key available for OpenAI vision"

    max_tokens = int(CONFIG['VISION'].get('vision_max_tokens', 150))
    return _post_vision_chat(
        api_url,
        api_key,
        model,
        prompt,
        image_data,
        max_tokens,
    )


def _describe_server(image_data, prompt):
    """Send image to external vision server for captioning."""
    base_url = CONFIG['VISION'].get('base_url', '')
    if not base_url:
        return "Error: No base_url configured for server_hosted vision"
    img_bytes = _to_bytes(image_data)
    files = {'image': ('image.jpg', BytesIO(img_bytes), 'image/jpeg')}
    headers = {}
    api_key = os.environ.get('EXTERNAL_API_KEY', '')
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = requests.post(f"{base_url}/caption", files=files, headers=headers, timeout=15)
    if response.status_code == 200:
        return response.json().get("caption", "No caption returned")
    return f"Error: Server returned {response.status_code}"


# Backend dispatch table
_BACKENDS = {
    "blip": _describe_blip,
    "llm": _describe_llm,
    "openai": _describe_openai,
    "external": _describe_server,
    "server_hosted": _describe_server,
}


def process_image(image_data, prompt="Describe this image in detail.", detection_context=None):
    """Unified vision dispatcher. Accepts bytes or base64 string."""
    processor = CONFIG['VISION'].get('vision_processor', 'blip')
    backend = _BACKENDS.get(processor)
    if backend is None:
        queue_message(f"ERROR: Unknown vision_processor '{processor}'")
        return f"Error: Unknown vision_processor '{processor}'"

    if detection_context:
        prompt = f"{detection_context}\n\n{prompt}"

    try:
        result = backend(image_data, prompt)
        result_text = str(result or "").lower()
        refusal_markers = (
            "unable to view",
            "unable to see",
            "can't view",
            "cannot view",
            "can't access the image",
            "cannot access the image",
            "do not have access to the image",
        )
        refused_image = any(marker in result_text for marker in refusal_markers)

        # A general chat model can be valid for conversation while lacking
        # image input. If the configured backend is OpenAI, retry with a known
        # vision-capable model before loading the much heavier local BLIP model.
        configured_vision_model = str(CONFIG['VISION'].get('vision_model', '') or '')
        main_openai_model = str(CONFIG['LLM'].get('openai_model', '') or '')
        should_try_openai_fallback = (
            (processor == "llm" and main_openai_model != "gpt-4o-mini")
            or (
                processor == "openai"
                and bool(configured_vision_model)
                and configured_vision_model != "gpt-4o-mini"
            )
        )
        if (should_try_openai_fallback
                and refused_image
                and CONFIG['LLM'].get('llm_backend') == "openai"
                and CONFIG['LLM'].get('api_key')):
            queue_message(
                f"WARNING: Vision model for '{processor}' refused the frame; "
                "retrying with gpt-4o-mini"
            )
            return _describe_openai(
                image_data,
                prompt,
                model_override="gpt-4o-mini",
            )

        # If the configured chat model is not vision-capable, preserve the
        # robot's camera feature by falling back to its local BLIP captioner.
        if (processor in ("llm", "openai")
                and refused_image
                and BlipProcessor is not None and BlipForConditionalGeneration is not None
                and torch is not None):
            queue_message(
                f"WARNING: Vision backend '{processor}' could not inspect the frame; "
                "falling back to local BLIP"
            )
            return _describe_blip(image_data, prompt)
        return result
    except Exception as e:
        queue_message(f"ERROR: Vision ({processor}) failed - {e}")
        configured_vision_model = str(CONFIG['VISION'].get('vision_model', '') or '')
        main_openai_model = str(CONFIG['LLM'].get('openai_model', '') or '')
        should_try_openai_fallback = (
            (processor == "llm" and main_openai_model != "gpt-4o-mini")
            or (
                processor == "openai"
                and bool(configured_vision_model)
                and configured_vision_model != "gpt-4o-mini"
            )
        )
        if (should_try_openai_fallback
                and CONFIG['LLM'].get('llm_backend') == "openai"
                and CONFIG['LLM'].get('api_key')):
            try:
                queue_message("WARNING: Retrying camera analysis with gpt-4o-mini")
                return _describe_openai(
                    image_data,
                    prompt,
                    model_override="gpt-4o-mini",
                )
            except Exception as fallback_error:
                queue_message(
                    f"ERROR: OpenAI vision fallback failed - {fallback_error}"
                )
        if (processor in ("llm", "openai")
                and BlipProcessor is not None and BlipForConditionalGeneration is not None
                and torch is not None):
            try:
                queue_message("WARNING: Retrying camera analysis with local BLIP")
                return _describe_blip(image_data, prompt)
            except Exception as fallback_error:
                queue_message(f"ERROR: BLIP vision fallback failed - {fallback_error}")
        return f"Error: {e}"


def _get_shared_camera():
    """Return the QML-owned camera when available, otherwise start the singleton."""
    camera = None
    try:
        from modules.module_main import ui_manager

        camera = getattr(ui_manager, "camera_module", None) if ui_manager else None
    except Exception:
        pass

    if camera is None or getattr(camera, "picam2", None) is None:
        camera = CameraModule(1280, 720, use_camera_module=True)
    if getattr(camera, "picam2", None) is None:
        raise RuntimeError("Raspberry Pi camera was not detected")
    if not getattr(camera, "running", False):
        camera.start_camera()
    if not getattr(camera, "running", False):
        raise RuntimeError("Raspberry Pi camera could not be started")
    return camera


def capture_camera_base64():
    """Capture from camera and return base64 string. Returns (b64, None) or (None, error)."""
    if not CONFIG['VISION'].get('enabled', False):
        return None, "Error: Vision is not enabled"
    if CameraModule is None:
        return None, "Error: Camera module not available"
    try:
        # 1280x720 is ample for cloud/local vision while avoiding a costly
        # 1080p capture pipeline on the Pi. CameraModule is a singleton, so if
        # the QML preview already started it this reuses its current frame.
        camera = _get_shared_camera()
        try:
            image_bytes = camera.capture_bytes(timeout=6)
        except Exception as first_error:
            queue_message(
                f"WARNING: Camera frame capture failed once; restarting camera: {first_error}"
            )
            camera.restart_camera()
            image_bytes = camera.capture_bytes(timeout=8)
        if not image_bytes:
            raise RuntimeError("camera returned an empty frame")
        queue_message(f"INFO: Camera frame captured ({len(image_bytes)} bytes)")
        return _to_base64(image_bytes), None
    except Exception as e:
        queue_message(f"ERROR: Camera capture failed - {e}")
        return None, f"Error: Camera capture failed: {e}"


def process_camera_image(user_prompt="Describe what you see.", detection_context=None):
    """Capture from camera and process with configured vision backend."""
    b64, error = capture_camera_base64()
    if error:
        return error
    try:
        return process_image(b64, user_prompt, detection_context=detection_context)
    except Exception as e:
        queue_message(f"ERROR: Camera vision failed - {e}")
        return "I tried to look but encountered an error."

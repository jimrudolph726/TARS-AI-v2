"""Skill: capture_camera_view — Analyze what the camera sees."""

import threading

_vision_lock = threading.Lock()
_vision_active = False  # process-wide flag (not thread-local)


def _extract_reply(raw):
    """Extract just the reply text from a raw LLM response (may be JSON)."""
    if not raw:
        return None
    try:
        import json
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "reply" in parsed:
            return parsed["reply"]
    except (json.JSONDecodeError, TypeError):
        pass
    return raw

SKILL = {
    "name": "capture_camera_view",
    "required_params": ["query"],
    "followup": True,
    "description": "Capture and analyze what the camera sees",
    "prompt": """capture_camera_view
   Triggers: MUST USE when user asks ANY question about vision/seeing:
     * "what do you see", "look at", "what's visible", "describe surroundings"
     * "what's in front", "what's around", "look around", "check visually"
     * "what's that", "can you see", "describe view"
     * ANY question asking about current visual state
   You HAVE a camera and CAN see - always use this function for vision queries
   CRITICAL: When you use capture_camera_view, your "reply" MUST be a short placeholder like "Let me take a look" or "Checking now." Do NOT describe or guess what you see — you haven't looked yet. The camera result will be delivered separately.
   Parameters: {{"query": "string describing what to analyze in the image"}}
   Example: {{"function": "capture_camera_view", "parameters": {{"query": "describe what you see"}}}}""",
    "examples": [
        """Example - Camera function:
User: "What do you see?"
Response: {{"reply": "Let me take a look.", "function_calls": [{{"function": "capture_camera_view", "parameters": {{"query": "describe what you see"}}}}], "new_memories": []}}""",
        """Example - Camera function (implicit):
User: "What's in front of you?"
Response: {{"reply": "Checking now.", "function_calls": [{{"function": "capture_camera_view", "parameters": {{"query": "describe what is in front"}}}}], "new_memories": []}}""",
        """Example - capture_camera_view vs take_photo (KNOW THE DIFFERENCE):
User: "Take a picture" -> take_photo (saves a file)
User: "What do you see?" -> capture_camera_view (analyzes the view)
User: "Snap a photo of this" -> take_photo
User: "Look at this" -> capture_camera_view""",
    ],
}

def execute(parameters, context):
    """Capture and analyze camera view. Returns reply text."""
    global _vision_active
    from modules.module_messageQue import queue_message
    from modules.module_config import load_config

    # Skip if user already provided an image
    if context.get("has_image"):
        queue_message("INFO: Skipping camera capture — user already provided an image")
        return None

    if _vision_active:
        queue_message("WARN: Skipping recursive capture_camera_view call")
        return None

    try:
        from modules.module_vision import process_camera_image
    except ImportError:
        return "Vision is not available on this device."

    config = load_config()
    debug = config.get('debug_mode', False)
    query = parameters.get("query", context.get("user_input", ""))
    vision_processor = config.get('VISION', {}).get('vision_processor', 'blip')

    # Pull detection context from UI if available
    detection_context = ""
    try:
        from modules.module_main import ui_manager
        if ui_manager and hasattr(ui_manager, 'detection_manager'):
            detection_context = ui_manager.detection_manager.get_detection_summary() or ""
    except Exception:
        pass

    _vision_active = True
    try:
        # Capture and analyze directly through the configured vision backend.
        # Previously the multimodal path called get_completion(), which rebuilt
        # the normal tool-enabled prompt.  On a "what do you see?" request the
        # model could invoke capture_camera_view a second time instead of
        # analyzing the image already attached to that request.
        if debug:
            queue_message(f"DEBUG VISION: Capturing frame with {vision_processor}")
        description = process_camera_image(
            query or "Describe what you see.",
            detection_context=detection_context or None,
        )
        failed = (
            not description
            or str(description).startswith("Error:")
            or "couldn't process the image" in str(description).lower()
            or "encountered an error" in str(description).lower()
        )
        if failed:
            queue_message(f"ERROR: Camera analysis failed: {description}")
            return "I tried to look but couldn't process the camera image."

        # Caption-only backends need one text-only pass to turn the terse
        # caption into a natural answer. Multimodal backends already return the
        # completed visual answer and should not be sent through tool routing.
        if vision_processor in ("blip", "server_hosted", "external"):
            if debug:
                queue_message(f"DEBUG VISION: Refining {vision_processor} caption")
            if description:
                vision_prompt = f"*You looked through your camera and saw: {description}*"
                if detection_context:
                    vision_prompt += f" {detection_context}"
                if query:
                    vision_prompt += f" The user asked: {query}"
                try:
                    from modules.module_llm import raw_complete_llm
                    raw = raw_complete_llm(vision_prompt)
                    reply = _extract_reply(raw)
                    return reply if reply else description
                except Exception as e:
                    queue_message(f"WARN: Vision follow-up LLM call failed: {e}")
                    return description
        return description
    finally:
        _vision_active = False

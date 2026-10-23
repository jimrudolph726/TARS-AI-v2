"""Retired compatibility shim for the former arbitrary-Python skill.

The original implementation executed LLM-generated Python in the main TARS
process. Its AST denylist was bypassable and its thread timeout could not stop
runaway code. Keep the skill name registered so stale function calls fail
closed, but never execute supplied code.
"""

SKILL = {
    "name": "sandbox_exec",
    "required_params": ["code"],
    "followup": True,
    "description": "Retired arbitrary-code executor (disabled for safety)",
    "prompt": "",
    "examples": [],
    "order": 999,
    "enabled_by_default": False,
}


def execute(parameters, context):
    """Reject every legacy call without inspecting or executing its code."""
    del parameters, context
    return (
        "Arbitrary Python execution is disabled for safety. "
        "Use the calculator skill for supported calculations."
    )

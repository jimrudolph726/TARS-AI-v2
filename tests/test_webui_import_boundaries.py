"""Architecture tests for the active Qt/QML and browser interfaces."""

from __future__ import annotations

import ast
import importlib
import sys
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
WEBUI = SRC / "modules" / "webui"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _import_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


class WebUIImportBoundaryTests(unittest.TestCase):
    def test_package_import_is_inert(self):
        sys.modules.pop("modules.webui", None)
        sys.modules.pop("modules.webui.application", None)
        before = {thread.ident for thread in threading.enumerate()}
        servo_loaded_before = "modules.module_servoctl" in sys.modules

        package = importlib.import_module("modules.webui")

        after = {thread.ident for thread in threading.enumerate()}
        self.assertEqual(package.__name__, "modules.webui")
        self.assertNotIn("modules.webui.application", sys.modules)
        self.assertEqual(
            servo_loaded_before,
            "modules.module_servoctl" in sys.modules,
        )
        self.assertEqual(before, after)

    def test_active_interfaces_do_not_import_pygame(self):
        active_files = [
            SRC / "app.py",
            SRC / "modules" / "module_runtime.py",
            SRC / "modules" / "module_ui_qml.py",
            SRC / "modules" / "module_chatui.py",
            *WEBUI.rglob("*.py"),
        ]
        offenders = []
        for path in active_files:
            imports = _import_names(_tree(path))
            if any(name == "pygame" or name.startswith("pygame.") for name in imports):
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual([], offenders)

    def test_webui_does_not_import_servo_hardware_at_module_scope(self):
        offenders = []
        for path in WEBUI.rglob("*.py"):
            tree = _tree(path)
            top_level_imports = _import_names(ast.Module(
                body=[
                    node for node in tree.body
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                ],
                type_ignores=[],
            ))
            if "modules.module_servoctl" in top_level_imports:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual([], offenders)

    def test_webui_has_no_top_level_thread_start(self):
        tree = _tree(WEBUI / "application.py")
        calls = [node for node in tree.body if isinstance(node, ast.Expr)]
        suspicious = []
        for statement in calls:
            text = ast.unparse(statement.value)
            if "Thread(" in text or ".start()" in text:
                suspicious.append(text)
        self.assertEqual([], suspicious)

    def test_compatibility_module_is_a_thin_facade(self):
        path = SRC / "modules" / "module_chatui.py"
        tree = _tree(path)
        imported_modules = _import_names(tree)
        self.assertEqual({"modules.webui.application"}, imported_modules)
        imported_names = {
            alias.asname or alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        required = {
            "flask_app", "socketio", "start_flask_app",
            "begin_bot_stream", "stream_reply_token", "push_user_message",
            "update_emotion", "_cloudflared_bin", "_get_tunnel_status",
            "_install_cloudflared", "_start_tunnel", "_stop_tunnel",
        }
        self.assertEqual(set(), required - imported_names)
        function_defs = [
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual([], function_defs)

    def test_required_route_contract_is_preserved(self):
        route_counts = {}
        for path in WEBUI.rglob("*.py"):
            tree = _tree(path)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call) or not decorator.args:
                        continue
                    function = decorator.func
                    if (
                        isinstance(function, ast.Attribute)
                        and function.attr in {"route", "get", "post", "put", "delete"}
                        and isinstance(decorator.args[0], ast.Constant)
                        and isinstance(decorator.args[0].value, str)
                        and decorator.args[0].value.startswith("/")
                    ):
                        route = decorator.args[0].value
                        route_counts[route] = route_counts.get(route, 0) + 1

        required = {
            "/",
            "/login",
            "/process_llm",
            "/camera_feed",
            "/api/servo/status",
            "/execute_action",
            "/stop_movement",
            "/disable_servos",
            "/enable_servos",
            "/get_config",
            "/save_config",
            "/api/wifi/status",
            "/api/tunnel/status",
            "/api/system/metrics",
            "/api/dashboard/stats",
        }
        self.assertEqual(set(), required - set(route_counts))
        duplicates = {
            route: count for route, count in route_counts.items() if count > 1
        }
        self.assertEqual({}, duplicates)


if __name__ == "__main__":
    unittest.main()

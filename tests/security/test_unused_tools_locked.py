"""Tools without a caller in src/ must stay disabled; recommend() is explicit-dead."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

# Registry pure_operations/ui_actions that are contracts only, not runtime calls.
CONTRACT_ONLY = {
    "retrieve_policy",
    "optimize_ticket_selection",
    "NAVIGATE_TO_BOOKING",
    "SHOW_SUPPORT_CHANNEL",
}


def _src_text() -> str:
    return "\n".join(
        p.read_text(encoding="utf-8") for p in (ROOT / "src").rglob("*.py") if p.is_file()
    )


def _registry() -> dict:
    return yaml.safe_load((ROOT / "configs/runtime_tool_registry.yaml").read_text())


def test_tools_without_callers_stay_disabled() -> None:
    registry = _registry()
    src = _src_text()
    uncalled = []
    for tool in registry["tools"]:
        name = tool["name"]
        called = f'execute("{name}"' in src or f"execute('{name}'" in src
        if not called:
            uncalled.append(name)
            assert tool["enabled"] is False, f"{name} has no caller but is enabled"
    assert "search_events" not in uncalled
    assert len(uncalled) == len(registry["tools"]) - 1


def test_contract_only_operations_have_no_runtime_caller() -> None:
    src = _src_text()
    for name in CONTRACT_ONLY:
        assert f'execute("{name}"' not in src and f"execute('{name}'" not in src


def test_recommend_is_explicit_dead_until_wired() -> None:
    recommendation = (ROOT / "src/smartevent_ai/domain/recommendation.py").read_text(
        encoding="utf-8"
    )
    assert "EXPLICIT_DEAD" in recommendation
    callers = []
    for path in (ROOT / "src").rglob("*.py"):
        if path.name == "recommendation.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(?<![\w.])recommend\(", line):
                callers.append(f"{path.name}:{lineno}")
    assert not callers, f"recommend() gained callers {callers}; wire it properly first"

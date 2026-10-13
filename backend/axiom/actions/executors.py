"""Where approved steps actually run: Composio (Notion / Google Sheets / Slack) or a dry-run stand-in.

Composio tool slugs and argument names vary by toolkit version, so the Composio executor reads each
tool's real input schema and maps our logical fields onto whatever parameter names it exposes. If a
required field cannot be mapped it fails loudly with the schema's property names instead of guessing.
Verify a setup with:  uv run python -m axiom.actions.composio_check
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from axiom.config import Settings, get_settings

from .models import ActionStep


@dataclass
class StepResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class Executor(Protocol):
    name: str

    async def run(self, step: ActionStep) -> StepResult: ...


class DryRunExecutor:
    """Nothing leaves the machine. Used whenever Composio is not configured."""

    name = "dry_run"

    async def run(self, step: ActionStep) -> StepResult:
        return StepResult(True, {"dry_run": True, "would_send": step.preview})


ALIASES: dict[str, dict[str, list[str]]] = {
    "notion_page": {
        "parent": ["parent_id", "parent_page_id", "parent", "page_id"],
        "title": ["title", "page_title", "name"],
        "content": ["content", "markdown", "body", "text", "children"],
    },
    "sheet_row": {
        "spreadsheet": ["spreadsheet_id", "spreadsheetId", "sheet_id"],
        "range": ["range", "sheet_name", "table_range"],
        "values": ["values", "rows", "row", "data"],
        "input_option": ["valueInputOption", "value_input_option"],
    },
    "slack_message": {
        "channel": ["channel", "channel_id", "channel_name"],
        "text": ["text", "markdown_text", "message", "content"],
    },
}
REQUIRED: dict[str, list[str]] = {
    "notion_page": ["parent", "title"],
    "sheet_row": ["spreadsheet", "values"],
    "slack_message": ["channel", "text"],
}


def map_arguments(kind: str, logical: dict[str, Any], schema_props: set[str]) -> dict[str, Any]:
    """Map logical field names to the tool's real parameter names using the alias table."""
    out: dict[str, Any] = {}
    for field_name, value in logical.items():
        if value is None:
            continue
        match = next((a for a in ALIASES[kind][field_name] if a in schema_props), None)
        if match:
            out[match] = value
    missing = [f for f in REQUIRED[kind] if logical.get(f) is not None and not any(
        a in out for a in ALIASES[kind][f])]  # fmt: skip
    if missing:
        raise ValueError(f"cannot map {missing} onto tool parameters {sorted(schema_props)}")
    return out


class ComposioExecutor:
    name = "composio"

    def __init__(self, settings: Settings | None = None, client: Any | None = None):
        self.s = settings or get_settings()
        if client is None:
            from composio import Composio  # optional dependency (uv sync --extra actions)

            client = Composio(api_key=self.s.composio_api_key)
        self.client = client
        self._schemas: dict[str, set[str]] = {}

    def _schema_props(self, slug: str) -> set[str]:
        if slug not in self._schemas:
            tool = self.client.tools.get_raw_composio_tool_by_slug(slug)
            params = getattr(tool, "input_parameters", None)
            if params is None and isinstance(tool, dict):
                params = tool.get("input_parameters")
            self._schemas[slug] = set((params or {}).get("properties", {}))
        return self._schemas[slug]

    def _plan(self, step: ActionStep) -> tuple[str, dict[str, Any], str | None]:
        """(slug, logical args, config error)."""
        s, p = self.s, step.preview
        if step.kind == "notion_page":
            if not s.notion_parent_page_id:
                return "", {}, "NOTION_PARENT_PAGE_ID is not configured"
            return (
                s.composio_notion_slug,
                {"parent": s.notion_parent_page_id, "title": p["title"], "content": p["markdown"]},
                None,
            )
        if step.kind == "sheet_row":
            if not s.sheets_spreadsheet_id:
                return "", {}, "SHEETS_SPREADSHEET_ID is not configured"
            return (
                s.composio_sheets_slug,
                {
                    "spreadsheet": s.sheets_spreadsheet_id,
                    "range": s.sheets_range,
                    "values": [p["values"]],
                    "input_option": "USER_ENTERED",
                },
                None,
            )
        if step.kind == "slack_message":
            if not s.slack_channel:
                return "", {}, "SLACK_CHANNEL is not configured"
            return s.composio_slack_slug, {"channel": s.slack_channel, "text": p["text"]}, None
        return "", {}, f"unsupported step kind {step.kind}"

    async def run(self, step: ActionStep) -> StepResult:
        slug, logical, config_error = self._plan(step)
        if config_error:
            return StepResult(False, error=config_error)
        try:
            args = map_arguments(step.kind, logical, await asyncio.to_thread(self._schema_props, slug))
            resp = await asyncio.to_thread(
                self.client.tools.execute, slug, args, user_id=self.s.composio_user_id
            )
        except Exception as e:  # SDK raises assorted errors (auth, not connected, validation)
            return StepResult(False, error=f"{type(e).__name__}: {e}"[:400])
        ok = bool(
            resp.get("successful", False) if isinstance(resp, dict) else getattr(resp, "successful", False)
        )
        data = resp.get("data", {}) if isinstance(resp, dict) else getattr(resp, "data", {})
        err = resp.get("error") if isinstance(resp, dict) else getattr(resp, "error", None)
        return StepResult(
            ok, data if isinstance(data, dict) else {"data": data}, None if ok else str(err)[:400]
        )


def build_executor(settings: Settings | None = None) -> Executor:
    s = settings or get_settings()
    if s.composio_api_key:
        try:
            return ComposioExecutor(s)
        except ImportError:
            pass  # extra not installed: fall back rather than failing the whole app
    return DryRunExecutor()


__all__ = [
    "Executor",
    "DryRunExecutor",
    "ComposioExecutor",
    "StepResult",
    "build_executor",
    "map_arguments",
    "json",
]

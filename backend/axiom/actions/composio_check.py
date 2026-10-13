"""Verify your Composio setup: lists the configured tool slugs and the parameters each one accepts.

    uv run python -m axiom.actions.composio_check

Run this once after connecting Notion, Google Sheets and Slack in the Composio dashboard. If a slug
is wrong for your toolkit version, set COMPOSIO_NOTION_SLUG / COMPOSIO_SHEETS_SLUG /
COMPOSIO_SLACK_SLUG in backend/.env to the correct one.
"""

from __future__ import annotations

from axiom.config import get_settings

from .executors import ALIASES, REQUIRED, ComposioExecutor


def main() -> None:
    s = get_settings()
    if not s.composio_api_key:
        print("COMPOSIO_API_KEY is not set: Axiom will run actions in dry-run mode.")
        return
    ex = ComposioExecutor(s)
    for kind, slug in (
        ("notion_page", s.composio_notion_slug),
        ("sheet_row", s.composio_sheets_slug),
        ("slack_message", s.composio_slack_slug),
    ):
        try:
            props = ex._schema_props(slug)
        except Exception as e:
            print(f"[FAIL] {kind}: {slug}: {type(e).__name__}: {e}")
            continue
        unmapped = [f for f in REQUIRED[kind] if not any(a in props for a in ALIASES[kind][f])]
        status = "OK  " if props and not unmapped else "WARN"
        print(f"[{status}] {kind}: {slug}\n        parameters: {sorted(props)}")
        if unmapped:
            print(f"        cannot map required fields {unmapped}: adjust ALIASES in executors.py")
    print(
        f"\nconfigured: parent page={bool(s.notion_parent_page_id)}, sheet={bool(s.sheets_spreadsheet_id)}, "
        f"slack channel={bool(s.slack_channel)}"
    )


if __name__ == "__main__":
    main()

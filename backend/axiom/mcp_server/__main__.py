from __future__ import annotations

import argparse

from .server import mcp


def main() -> None:
    p = argparse.ArgumentParser(prog="axiom-mcp", description="Axiom MCP server")
    p.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    if args.transport == "streamable-http":
        mcp.settings.host, mcp.settings.port = args.host, args.port
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()

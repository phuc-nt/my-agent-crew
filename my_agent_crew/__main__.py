"""`python -m my_agent_crew` — start the server."""

from __future__ import annotations

import argparse

import uvicorn

from my_agent_crew.config import load_settings
from my_agent_crew.server import build_deps, create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="my-agent-crew")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    settings = load_settings()
    app = create_app(build_deps(settings))
    routes = ", ".join(f"{r.provider}:{r.model}" for r in settings.routes)
    print(f"my-agent-crew · home={settings.home} · routes={routes}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

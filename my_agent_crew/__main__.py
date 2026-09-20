"""`python -m my_agent_crew` — start the server."""

from __future__ import annotations

import argparse
import logging

import uvicorn

from my_agent_crew.config import load_settings
from my_agent_crew.server import build_runtime, create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="my-agent-crew")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    settings = load_settings()
    runtime = build_runtime(settings)
    app = create_app(runtime)
    routes = ", ".join(f"{r.provider}:{r.model}" for r in settings.routes)
    agents = ", ".join(runtime.agents)
    print(f"my-agent-crew · home={settings.home} · routes={routes} · agents={agents}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

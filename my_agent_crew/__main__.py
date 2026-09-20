"""`python -m my_agent_crew` — start the server, or manage agents with `agent …`."""

from __future__ import annotations

import argparse
import logging

import uvicorn

from my_agent_crew.agents.templates_cli import add_template, list_templates
from my_agent_crew.config import load_settings
from my_agent_crew.server import build_runtime, create_app


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="my-agent-crew")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    # No subcommand keeps starting the server, so the way the service is launched never
    # changes underneath an installed launchd job.
    sub = parser.add_subparsers(dest="command")
    agent = sub.add_parser("agent", help="add an agent from a bundled template").add_subparsers(
        dest="agent_command", required=True
    )
    agent.add_parser("list-templates", help="show the bundled templates")
    add = agent.add_parser("add", help="copy a template into the home")
    add.add_argument("template")
    add.add_argument("--id", default="", help="agent id, defaults to the template name")
    add.add_argument("--force", action="store_true", help="overwrite files that already exist")
    return parser


def _list_templates() -> int:
    for t in list_templates():
        print(f"{t.id:<10} {t.mode:<10} {t.description}")
    return 0


def _add(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        agent_dir, peers = add_template(args.template, settings.home, args.id, args.force)
    except KeyError:
        names = ", ".join(t.id for t in list_templates())
        print(f"không có mẫu {args.template!r}. Có: {names}")
        return 1
    except FileExistsError as exc:
        print(f"{exc.args[0]} đã có rồi. Dùng --force để ghi đè.")
        return 1
    print(f"đã tạo {agent_dir}")
    if peers:
        print(f"kèm theo đồng đội mà agent này giao việc: {', '.join(peers)}")
    print("sửa agent.yaml (workspace, routes) rồi khởi động lại máy chủ.")
    return 0


def _serve(args: argparse.Namespace) -> None:
    settings = load_settings()
    runtime = build_runtime(settings)
    app = create_app(runtime)
    routes = ", ".join(f"{r.provider}:{r.model}" for r in settings.routes)
    agents = ", ".join(runtime.agents)
    print(f"my-agent-crew · home={settings.home} · routes={routes} · agents={agents}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def main() -> int:
    args = _parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if args.command == "agent":
        return _list_templates() if args.agent_command == "list-templates" else _add(args)
    _serve(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

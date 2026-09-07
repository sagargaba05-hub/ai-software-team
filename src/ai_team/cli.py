from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Settings
from .doctor import format_doctor, run_doctor
from .documents import bootstrap_project
from .demo import run_demo
from .models import FakeModelClient, OmniRouteModelClient
from .state_store import StateStore
from .supervisor import Supervisor


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ai_team", description="Reusable AI software delivery team")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="Check local dependencies and model connectivity")
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--no-live-routes", action="store_true")
    init = sub.add_parser("init", help="Bootstrap project documentation only")
    init.add_argument("repository", type=Path)
    run = sub.add_parser("run", help="Run a project objective")
    run.add_argument("repository", type=Path)
    run.add_argument("--objective", required=True)
    status = sub.add_parser("status", help="Show persisted workflow state")
    status.add_argument("repository", type=Path)
    resume = sub.add_parser("resume", help="Resume a persisted workflow")
    resume.add_argument("repository", type=Path)
    dry = sub.add_parser("dry-run", help="Run the complete graph using offline fake agents")
    dry.add_argument("repository", type=Path)
    dry.add_argument("--qa-failures", type=int, default=0)
    dry.add_argument("--review-failures", type=int, default=0)
    demo = sub.add_parser("demo", help="Run the bounded controlled routing demonstration")
    demo.add_argument("repository", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings.load()
    try:
        if args.command == "doctor":
            checks = run_doctor(settings, live_routes=not args.no_live_routes)
            print(format_doctor(checks, args.json))
            return 0 if all(check.ok for check in checks if check.required) else 1
        if args.command == "init":
            created = bootstrap_project(args.repository)
            print(f"Initialized {args.repository.resolve()}; created {len(created)} missing artifacts.")
            return 0
        if args.command == "status":
            repository = args.repository.resolve()
            if not repository.is_dir():
                raise FileNotFoundError(f"Repository does not exist: {repository}")
            state = StateStore.read(repository)
            print(json.dumps(state or {"status": "NOT_INITIALIZED"}, indent=2))
            return 0 if state else 1
        if args.command == "demo":
            repository = args.repository.resolve()
            if not repository.is_dir(): raise FileNotFoundError(f"Repository does not exist: {repository}")
            result = run_demo(settings, repository)
            print(json.dumps(result, indent=2, default=str))
            return 0 if result["status"] == "PASS" else 1
        if args.command == "run":
            if not args.objective.strip(): raise ValueError("Objective must not be empty.")
            result = Supervisor(args.repository, settings, OmniRouteModelClient(settings, args.repository.resolve())).run(args.objective)
        elif args.command == "resume":
            stored = StateStore.read(args.repository.resolve())
            if not stored:
                raise RuntimeError("No persisted run is available to resume.")
            result = Supervisor(args.repository, settings, OmniRouteModelClient(settings, args.repository.resolve())).run(stored["objective"], resume=True)
        else:
            if not args.repository.resolve().is_dir(): raise FileNotFoundError(args.repository)
            bootstrap_project(args.repository)
            fake = FakeModelClient(qa_failures=args.qa_failures, review_failures=args.review_failures)
            result = Supervisor(args.repository, settings, fake).run("Verify the reusable team workflow without changing production code.")
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("status") == "RELEASE_APPROVED" else 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

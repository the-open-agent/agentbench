from __future__ import annotations

import argparse
import os
from pathlib import Path

from .benchcore.runner import run_benchmark
from .suites.baseperf import BasePerfSuite
from .suites.dialogue import DialogueSuite
from .suites.hardchat import HardChatSuite
from .suites.tool import ToolSuite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentBench unified CLI")
    parser.add_argument("command", choices=["run"], help="Subcommand: run")
    parser.add_argument("--suite", default="all", choices=["baseperf", "dialogue", "hardchat", "tool", "all"])
    parser.add_argument("--base-url", default="http://127.0.0.1:14000")
    parser.add_argument("--model", default="deepseek/deepseek-v4-flash")
    parser.add_argument("--provider-key", default=os.environ.get("OPENAGENT_PROVIDER_KEY", ""))
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=240)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command != "run":
        return 2
    if not args.provider_key:
        print("Missing provider key; pass --provider-key or set OPENAGENT_PROVIDER_KEY.")
        return 2
    root = Path(__file__).resolve().parent
    suite_map = {
        "baseperf": BasePerfSuite(root),
        "dialogue": DialogueSuite(root),
        "hardchat": HardChatSuite(root),
        "tool": ToolSuite(root),
    }
    suites = list(suite_map.values()) if args.suite == "all" else [suite_map[args.suite]]
    session_dir = run_benchmark(
        root=root,
        suites=suites,
        base_url=args.base_url,
        provider_key=args.provider_key,
        model=args.model,
        rounds=args.rounds,
        max_attempts=args.max_attempts,
        timeout_s=args.timeout,
    )
    print(f"Session written to: {session_dir}")
    return 0

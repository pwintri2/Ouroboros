"""Command-line entrypoint for Resonant Ouroboros Fase 1."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from .browser import HumanBrowserEngine
from .dashboard import launch_dashboard
from .gordon_bridge import GordonBridge
from .memory import create_memory_from_env
from .oscillator import HertzOscillator
from .paeu_loop import PAEULoop
from .seed import browse_and_learn_seed, queue_seed_topics_without_browser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resonant Ouroboros Proto 1.1 Fase 1")
    sub = parser.add_subparsers(dest="command", required=True)

    learn = sub.add_parser("learn-seed", help="Browse and learn topics from AGI Kennis.txt")
    learn.add_argument("--seed", default="/workspace/agi_kennis.txt")
    learn.add_argument("--max-topics", type=int, default=int(os.getenv("MAX_SEED_TOPICS", "0")) or None)
    learn.add_argument("--steps-per-topic", type=int, default=int(os.getenv("STEPS_PER_TOPIC", "3")))
    learn.add_argument("--dry-run", action="store_true", help="Queue seed topics without opening a browser")

    sub.add_parser("dashboard", help="Launch the Gradio dashboard")
    sub.add_parser("graph-check", help="Check that the LangGraph PAEU graph can compile")
    return parser


async def _learn_seed(args: argparse.Namespace) -> None:
    bridge = GordonBridge()
    bridge.report("Orchestrator", "started", "seed learning command entered")
    oscillator = HertzOscillator()
    memory = create_memory_from_env(fallback_in_memory=args.dry_run)
    if args.dry_run:
        loop = PAEULoop(oscillator, browser=None, memory=memory)  # type: ignore[arg-type]
        ids = queue_seed_topics_without_browser(args.seed, loop, max_topics=args.max_topics)
        bridge.report("Builder", "dry_run_seed_queued", f"{len(ids)} topics queued")
        print(f"Queued {len(ids)} seed topics without browser.")
        return

    async with HumanBrowserEngine() as browser:
        loop = PAEULoop(oscillator, browser, memory)
        results = await browse_and_learn_seed(
            Path(args.seed),
            loop,
            max_topics=args.max_topics,
            steps_per_topic=args.steps_per_topic,
        )
        
        # Report metrics
        m = loop.metrics
        metrics_msg = (
            f"Topics: {m.topics_attempted}, Pages: {m.pages_visited}, "
            f"Useful: {m.useful_records_stored}, Rejected: {m.rejected_pages}, "
            f"Best Band: {max(m.hz_band_performance, key=m.hz_band_performance.get)}"
        )
        bridge.report("Builder", "seed_learned", metrics_msg)
        print(f"Browsed and learned {len(results)} seed topics.")
        print(f"Metrics: {metrics_msg}")
        print(f"Hz Performance: {m.hz_band_performance}")
        
        # Write to file for summary
        with open("/workspace/last_metrics.txt", "w") as f:
            f.write(metrics_msg + "\n")
            f.write(str(m.hz_band_performance) + "\n")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "learn-seed":
        asyncio.run(_learn_seed(args))
    elif args.command == "dashboard":
        GordonBridge().report("Final Integration", "dashboard_starting", "Gradio launch requested")
        launch_dashboard()
    elif args.command == "graph-check":
        from .paeu_graph import build_langgraph_paeu

        graph = build_langgraph_paeu()
        print(graph)
    else:
        parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()

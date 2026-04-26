"""Command-line entrypoint for Resonant Ouroboros Fase 1 and Fase 2."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from .awake_keeper import AwakeKeeper, AwakeKeeperConfig
from .browser import HumanBrowserEngine
from .dashboard import launch_dashboard
from .gordon_bridge import GordonBridge
from .memory import create_memory_from_env
from .oscillator import HertzOscillator
from .paeu_graph import build_langgraph_paeu
from .paeu_loop import PAEULoop
from .seed import browse_and_learn_seed, queue_seed_topics_without_browser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resonant Ouroboros Proto 1.1")
    sub = parser.add_subparsers(dest="command", required=True)

    learn = sub.add_parser("learn-seed", help="Browse and learn topics from AGI Kennis.txt")
    learn.add_argument("--seed", default=os.getenv("AWAKE_KEEPER_SEED", "/workspace/agi_kennis.txt"))
    learn.add_argument("--max-topics", type=int, default=int(os.getenv("MAX_SEED_TOPICS", "3")))
    learn.add_argument("--steps-per-topic", type=int, default=int(os.getenv("STEPS_PER_TOPIC", "3")))
    learn.add_argument("--dry-run", action="store_true", help="Queue seed topics without opening a browser")

    sub.add_parser("dashboard", help="Launch the Gradio dashboard")
    sub.add_parser("awake", help="Run the Fase 2 Awake Keeper loop without the dashboard")
    sub.add_parser("graph-check", help="Check that the LangGraph PAEU graph can compile")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    bridge = GordonBridge()

    if args.command == "dashboard":
        bridge.report("Orchestrator", "started", "dashboard command entered")
        launch_dashboard()
        return

    if args.command == "awake":
        bridge.report("Orchestrator", "started", "awake keeper command entered")
        keeper = AwakeKeeper(config=AwakeKeeperConfig.from_env())
        print(keeper.start())
        try:
            while True:
                print(keeper.status().as_lines())
                asyncio.run(asyncio.sleep(5))
        except KeyboardInterrupt:
            print(keeper.stop())
        return

    if args.command == "graph-check":
        build_langgraph_paeu()
        print("LangGraph PAEU graph compiled.")
        return

    if args.command == "learn-seed":
        seed = Path(args.seed)
        oscillator = HertzOscillator()
        memory = create_memory_from_env(fallback_in_memory=True)
        if args.dry_run:
            loop = PAEULoop(oscillator=oscillator, browser=HumanBrowserEngine(), memory=memory)
            ids = queue_seed_topics_without_browser(seed, loop, max_topics=args.max_topics)
            bridge.report("Builder", "dry_run_seed_queued", f"{len(ids)} topics queued")
            print(f"Queued {len(ids)} seed topics without browser.")
            return

        async def run_learning():
            async with HumanBrowserEngine() as browser:
                loop = PAEULoop(oscillator=oscillator, browser=browser, memory=memory)
                return await browse_and_learn_seed(
                    seed,
                    loop,
                    max_topics=args.max_topics,
                    steps_per_topic=args.steps_per_topic,
                ), loop.metrics

        results, metrics = asyncio.run(run_learning())
        bridge.report("Builder", "seed_learned", f"Browsed and learned {len(results)} seed topics.")
        print(f"Topics: {metrics.topics_attempted}, Pages: {metrics.pages_visited}, Useful: {metrics.useful_records_stored}, Rejected: {metrics.rejected_pages}")
        print(f"Hz Performance: {metrics.hz_band_performance}")
        Path("/workspace/last_metrics.txt").write_text(str(metrics), encoding="utf-8")


if __name__ == "__main__":
    main()

"""Safe guided learning pipeline for Ouroboros.

This package is intentionally separate from the existing self-training and
11D memory layers. It produces inspectable artifacts only: learner attempts,
critic scores, reflections, memory rules, and JSONL audit events.
"""

from .critic import evaluate_attempt
from .scenario_loader import load_demonstration, load_scenario
from .self_improvement_patterns import PREFERRED_LOCAL_MODEL, select_self_improvement_patterns

__all__ = [
    "PREFERRED_LOCAL_MODEL",
    "evaluate_attempt",
    "load_demonstration",
    "load_scenario",
    "select_self_improvement_patterns",
]

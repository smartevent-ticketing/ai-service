"""DEPRECATED shim (1 release): use smartevent_ai.tooling.offline_jobs.benchmark_semantic."""

from smartevent_ai.tooling.offline_jobs.benchmark_semantic import *  # noqa: F401,F403

from smartevent_ai.tooling.offline_jobs.benchmark_semantic import main as _main

if __name__ == "__main__":
    _main()

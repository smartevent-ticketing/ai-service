"""DEPRECATED shim (1 release): use smartevent_ai.tooling.offline_jobs.publish."""

from smartevent_ai.tooling.offline_jobs.publish import *  # noqa: F401,F403

from smartevent_ai.tooling.offline_jobs.publish import main as _main

if __name__ == "__main__":
    _main()

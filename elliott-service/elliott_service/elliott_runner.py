import os
import shutil
from typing import Any

from artcommonlib.dotconfig import Config
from elliottlib import Runtime
from elliottlib.cli import cli_opts
from elliottlib.cli.find_bugs_sweep_cli import (
    FindBugsSweep,
    categorize_bugs_by_type,
    get_assembly_bug_ids,
    get_bugs_sweep,
    get_builds_by_advisory_kind,
)


class ElliottRunner:
    """Wraps elliottlib Python API for use in the FastAPI service."""

    def __init__(self, data_path: str, working_dir: str):
        self.data_path = data_path
        self.working_dir = working_dir

    def _create_runtime(self, group: str, assembly: str = "stream", **kwargs) -> Runtime:
        cli_args = {
            "group": group,
            "assembly": assembly,
            "data_path": self.data_path,
            "working_dir": None,
            "quiet": True,
            "debug": False,
            **kwargs,
        }
        cfg = Config(
            "elliott",
            "settings",
            template=cli_opts.CLI_CONFIG_TEMPLATE,
            envvars=cli_opts.CLI_ENV_VARS,
            cli_args=cli_args,
        )
        return Runtime(cfg_obj=cfg, **cfg.to_dict())

    async def find_bugs(
        self,
        group: str,
        assembly: str = "stream",
        exclude_trackers: bool = False,
        permissive: bool = False,
        cve_only: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:
        """Find bugs eligible for the given group/assembly.

        Returns a dict mapping advisory kind to list of bug dicts.
        """
        runtime = self._create_runtime(group=group, assembly=assembly)
        try:
            runtime.initialize(mode="both")
            bug_tracker = runtime.get_bug_tracker("jira")

            find_bugs_obj = FindBugsSweep(cve_only=cve_only)
            bugs = await get_bugs_sweep(runtime, find_bugs_obj, bug_tracker)
            included_bug_ids, _ = get_assembly_bug_ids(runtime, bug_tracker_type=bug_tracker.type)
            major_version, minor_version = runtime.get_major_minor()
            builds_by_advisory_kind = get_builds_by_advisory_kind(runtime)

            bugs_by_type, issues = categorize_bugs_by_type(
                runtime=runtime,
                bugs=bugs,
                builds_by_advisory_kind=builds_by_advisory_kind,
                permitted_bug_ids=included_bug_ids,
                major_version=major_version,
                minor_version=minor_version,
                operator_bundle_advisory="metadata",
                permissive=permissive,
                exclude_trackers=exclude_trackers,
            )

            result = {}
            for kind, kind_bugs in bugs_by_type.items():
                result[str(kind)] = [_bug_to_dict(b) for b in sorted(kind_bugs, key=lambda b: b.id)]
            return result
        finally:
            if hasattr(runtime, "working_dir") and getattr(runtime, "remove_tmp_working_dir", False):
                if runtime.working_dir and os.path.isdir(runtime.working_dir):
                    shutil.rmtree(runtime.working_dir, ignore_errors=True)


def _bug_to_dict(bug) -> dict[str, Any]:
    """Convert a Bug object to a serializable dict."""
    return {
        "id": bug.id,
        "summary": getattr(bug, "summary", ""),
        "status": getattr(bug, "status", ""),
        "component": getattr(bug, "component", ""),
        "target_release": getattr(bug, "target_release", []),
    }

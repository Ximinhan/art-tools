import io
import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

import click
import gitlab
from github import Github, GithubException
from artcommonlib import exectools
from artcommonlib.assembly import AssemblyTypes, assembly_config_struct, assembly_group_config
from artcommonlib.constants import SHIPMENT_DATA_URL_TEMPLATE
from artcommonlib.model import Model
from artcommonlib.util import get_assembly_release_date_async, isolate_major_minor_in_group, new_roundtrip_yaml_handler
from doozerlib.backend.konflux_image_builder import KonfluxImageBuilder
from elliottlib.errata_async import AsyncErrataAPI
from elliottlib.cli.find_bugs_sweep_cli import validate_tracker_bugs
from elliottlib import shipment_model

from pyartcd import constants
from pyartcd.cli import cli, click_coroutine, pass_runtime
from pyartcd.runtime import Runtime
from pyartcd.slack import SlackClient
from pyartcd.util import (
    get_assembly_basis,
    get_assembly_type,
    get_release_name_for_assembly,
    nightlies_with_pullspecs,
)

_LOGGER = logging.getLogger(__name__)
yaml = new_roundtrip_yaml_handler()


class PrepareReleaseKonfluxPipeline:
    def __init__(
        self,
        slack_client: SlackClient,
        runtime: Runtime,
        group: str,
        assembly: str,
        github_token: str,
        gitlab_token: str,
        build_repo_url: Optional[str] = None,
        shipment_repo_url: Optional[str] = None,
        job_url: Optional[str] = None,
        date: Optional[str] = None,
    ) -> None:
        self.runtime = runtime
        self.assembly = assembly
        self.group = group
        self._slack_client = slack_client
        self.github_client = Github(github_token)
        self.gitlab_client = gitlab.Gitlab(url="https://gitlab.cee.redhat.com", private_token=gitlab_token)
        self.release_date = date
        self.job_url = job_url
        self.dry_run = self.runtime.dry_run
        self.build_repo_url = build_repo_url
        build_repo_vars = self._build_repo_vars(build_repo_url)
        self.build_repo_pull_url, self.build_data_gitref, self.build_data_push_url = build_repo_vars
        self.working_dir = self.runtime.working_dir.absolute()
        self.elliott_working_dir = self.working_dir / "elliott-working"

        self._elliott_base_command = [
            'elliott',
            f'--group={group}{f"@{self.build_data_gitref}" if self.build_data_gitref else ""}',
            f'--assembly={self.assembly}',
            '--build-system=konflux',
            f'--working-dir={self.elliott_working_dir}',
            f'--data-path={self.build_repo_pull_url}',
        ]

    async def run(self):
        await self.init_assembly_data()
        # advisories, jira_issue_key = await self.create_and_prepare_advisory()
        shipment = await self.prepare_shipment()
        shipment_mr = self.create_shipment(shipment)
        # self.update_build_data(advisories, jira_issue_key, shipment_mr)

    async def init_assembly_data(self):
        """
        load necessary data for release
        """
        self.build_repo = constants.GITHUB_OWNER
        build_gitref = self.group
        if self.build_repo_url:
            self.build_repo, build_gitref = build_repo_url.split("@", 1)
        upstream_repo = self.github_client.get_repo(f"{self.build_repo}/ocp-build-data")
        group_config = yaml.load(upstream_repo.get_contents("group.yml", ref=build_gitref).decoded_content)
        release_config = yaml.load(upstream_repo.get_contents("releases.yml", ref=build_gitref).decoded_content)
        self.group_config = assembly_group_config(
            Model(release_config), self.assembly, Model(group_config)
        ).primitive()
        self.release_name = get_release_name_for_assembly(self.group, release_config, self.assembly)
        nightlies = get_assembly_basis(release_config, self.assembly).get("reference_releases", {}).values()
        self.candidate_nightlies = nightlies_with_pullspecs(nightlies)
        return

    async def create_and_prepare_advisory(self):
        """
        create and prepare adivosries under groups
        """
        if not self.release_date:
            _LOGGER.info("Release date not provided. Fetching release date from release schedule...")
            try:
                self.release_date = await get_assembly_release_date_async(self.release_name)
                _LOGGER.info("Release date: %s", self.release_date)
            except Exception as ex:
                raise ValueError(f"Failed to fetch release date from release schedule for {self.release_name}: {ex}")
        # create advisory and sweep bug
        self.release_version = semver.VersionInfo.parse(self.release_name).to_tuple()
        is_ga = self.release_version[2] == 0
        advisory_type = "RHEA" if is_ga else "RHBA"
        self.advisories = self.group_config.get("advisories", {})
        for ad in self.advisories:
            if self.advisories[ad] >= 0:
                continue
            if ad == "prerelease":
                release_date = datetime.now(tz=timezone.utc) + timedelta(days=3)
                if release_date.weekday() >= 5:
                    release_date += timedelta(days=7 - release_date.weekday())
                prerelease_advisory_num = self.create_advisory(
                    advisory_type=advisory_type, art_advisory_key=ad, release_date=release_date
                )
                self.advisories[ad] = prerelease_advisory_num
                await self.build_and_attach_bundles(prerelease_advisory_num)
                self.sweep_bugs(advisory=prerelease_advisory_num, permissive=True)
                break
            # usually this should be rpm advisory
            standard_advisory_num = self.create_advisory(
                advisory_type=advisory_type, art_advisory_key=ad, release_date=self.release_date
            )
            self.advisories[ad] = standard_advisory_num
            await self.sweep_builds_async(ad, standard_advisory_num)
            self.sweep_bugs(default_advisory_type=ad, permissive=False)  # sweep bugs for type ad
            self.attach_cve_flaws(standard_advisory_num)  # attach cve falws for advisory
            await self.change_advisory_state_qe(standard_advisory_num)  # change advisory to QE
        # create release jira
        jira_issue_key = self.group_config.get("release_jira")
        jira_issue = None
        jira_template_vars = {
            "release_name": self.release_name,
            "x": self.release_version[0],
            "y": self.release_version[1],
            "z": self.release_version[2],
            "release_date": self.release_date,
            "advisories": self.advisories,
            "candidate_nightlies": self.candidate_nightlies,
        }
        if jira_issue_key and jira_issue_key != "ART-0":
            _LOGGER.info("Reusing existing release JIRA %s", jira_issue_key)
            jira_issue = self._jira_client.get_issue(jira_issue_key)
            subtasks = [self._jira_client.get_issue(subtask.key) for subtask in jira_issue.fields.subtasks]
            self.update_release_jira(jira_issue, subtasks, jira_template_vars)
        else:
            _LOGGER.info("Creating a release JIRA...")
            jira_issues = self.create_release_jira(jira_template_vars)
            jira_issue = jira_issues[0] if jira_issues else None
            jira_issue_key = jira_issue.key if jira_issue else None
        self.jira_issue_key = jira_issue_key
        return advisories, jira_issue_key

    async def prepare_shipment(self):
        """
        prepare shipment data
        """
        # find builds for image
        image_builds, extra_builds, olm_builds, olm_builds_not_found = await self.find_builds()
        # TODO: rebuild olm_builds_not_found
        # find bugs for image, note the bugs didn't sweep and didn't find cve_flaws
        image_bugs, extras_bugs, metadata_bugs, cve_list_map = await self.find_bugs_with_flaws(image_builds, extra_builds, olm_builds)
        # TODO:find cve falws

        # return a dict contains builds, bugs, cves
        res = []
        for kind, builds, bugs, cve_list in [
            ("image", image_builds, image_bugs, cve_list_map['image']),
            ("extras", extra_builds, extras_bugs, cve_list_map['extras']),
            ("metadata", olm_builds, metadata_bugs, cve_list_map['metadata']),
        ]:
            res.append({"kind": kind, "builds": builds, "bugs": bugs, "cves": cve_list,})
        _LOGGER.info(f"Generated shipment data: \n {res}")
        return res

    def create_shipment(self, shipment_data):
        """
        check shipment mr
        create/rebase shipment branch
        """
        _LOGGER.info(f"Creating shipment mr ...")
        match = re.search(r"\d+.\d+.\d+", self.assembly)
        if match:
            major, minor, patch = self.assembly.split(".")
        else:
            major, minor = isolate_major_minor_in_group(self.group)
            patch = 0
        self.for_fbc = False
        upstream_repo = self.github_client.get_repo(f"{self.build_repo}/ocp-build-data")
        common_advisory_template = yaml.load(
            upstream_repo.get_contents("config/advisory_templates.yml", ref="main").decoded_content
        )
        boilerplate = common_advisory_template.get("boilerplates", {})

        # get gitlab shipment config, project id is 116177
        project = self.gitlab_client.projects.get(116177)
        application = self.group.replace(".", "-")
        shipment_env_config = yaml.load(project.files.get(file_path='config.yaml', ref='main').decode())
        app_env_config = shipment_env_config.get("applications", {}).get(application, {}).get("environments", {})
        self.stage_rpa = app_env_config.get("stage", {}).get("releasePlan", "test-stage-rpa")
        self.prod_rpa = app_env_config.get("prod", {}).get("releasePlan", "test-prod-rpa")
        time_suffix = datetime.now().strftime("%Y%m%d%H%M%S")
        branch_name = f"Add_shipment_{self.assembly}"
        # create gitlab shipment fork branch
        branches = project.branches.list(search=branch_name)
        for branch in branches:
            if branch.name == branch_name:
                branch.delete()
                _LOGGER.info(f"Deleted existing branch {branch_name}")
                break
        fork_branch = project.branches.create({'branch': branch_name, 'ref': 'main'})
        _LOGGER.info(f"Created fork branch {fork_branch.name} : {fork_branch.web_url}")

        for shipment_item in shipment_data:
            errata_type = "rhsa" if shipment_item['cves'] else "rhba"
            advisory_boilerplate = boilerplate[shipment_item['kind']][errata_type]
            shipment = shipment_model.ShipmentConfig(
                shipment=shipment_model.Shipment(
                    metadata=shipment_model.Metadata(
                        product="ocp",
                        application=application,
                        group=self.group,
                        assembly=self.assembly,
                        fbc=self.for_fbc,
                    ),
                    environments=shipment_model.Environments(
                        stage=shipment_model.ShipmentEnv(releasePlan=self.stage_rpa),
                        prod=shipment_model.ShipmentEnv(releasePlan=self.prod_rpa),
                    ),
                    snapshot=shipment_model.Snapshot(
                        name=f"ose-{self.assembly}-{time_suffix}",
                        spec=shipment_model.Spec(nvrs=shipment_item['builds'])
                    ),
                    data=shipment_model.Data(
                        releaseNotes=shipment_model.ReleaseNotes(
                            type=errata_type.upper(),
                            issues=shipment_model.Issues(fixed=[shipment_model.Issue(id=bug["id"], source=urlparse(bug['url']).hostname) for bug in shipment_item['bugs']]),
                            synopsis=advisory_boilerplate['synopsis'].format(MINOR=minor, PATCH=patch),
                            topic=advisory_boilerplate['topic'].format(MINOR=minor, PATCH=patch),
                            description=advisory_boilerplate['description'].format(MINOR=minor, PATCH=patch),
                            solution=advisory_boilerplate['solution'].format(MINOR=minor, PATCH=patch),
                        ),
                    ),
                ),
            )
            shipment_yaml = shipment.model_dump(exclude_unset=True, exclude_none=True)
            _LOGGER.info(f"created shipment yaml for {shipment_item['kind']}: \n {shipment_yaml}")
            output = StringIO()
            yaml.dump(shipment_yaml, output)
            # add shipment to fork repo
            project.files.create({
                'file_path': f"shipment/ocp/{self.group}/{application}/prod/{self.assembly}-{shipment_item['kind']}.{time_suffix}.yaml",
                'branch': fork_branch.name,
                'content': output.getvalue(),
                'commit_message': f"Add shipment files for {self.assembly}",
            })
        mr = project.mergerequests.create({
            'source_branch': fork_branch.name,
            'target_branch': 'main',
            'title': f"[TEST] Add shipment files for {self.assembly}",
        })
        _LOGGER.info(f"Created shipment mr {mr.web_url}")
        return mr.web_url

    async def find_bugs_with_flaws(self, image_builds, extra_builds, olm_builds)
        """
        Run the elliott 'find-bugs:sweep' command and extract bug IDs and URLs for each bug type.
        Returns:
            tuple: Three lists of dictionaries, each containing 'id' and 'url' for:
                - image_bugs: Bugs related to images
                - extras_bugs: Extra bugs
                - metadata_bugs: Metadata bugs
        """
        cmd = self._elliott_base_command + ["find-bugs:sweep", "--report", "--noop", "--output=json"]
        rc, stdout, stderr = await exectools.cmd_gather_async(cmd)
        if not stdout:
            return [], [], [], {}
        #_LOGGER.info(f"find-bugs:sweep output:\n{stdout}")
        out = json.loads(stdout)
        cve_list_map = {'image': [], 'extras': [], 'metadata': []}

        def extract_bugs(bug_list, cve_bug_type):
            res = []
            for bug in bug_list:
                if isinstance(bug, dict):
                    res.append({"id": bug["id"], "url": bug["url"]})
                else:
                    # this should be tracker bug
                    if bug.cve_id not in cve_list_map[cve_bug_type]:
                        cve_list_map[cve_bug_type].append(bug.cve_id)
                    res.append({"id": bug.id, "url": bug.url})
            return res

        tracker_bugs = [
            SimpleNamespace(
                id=bug['id'],
                component=bug['component'],
                sub_component=bug['sub_component'],
                whiteboard_component=bug['whiteboard_component'],
                status=bug['status'],
                url=bug['url'],
                cve_id=bug['cve_id'],
            )
            for bug in out.get("tracker", [])
        ]
        permitted_bug_ids = out.get("permitted", [])
        kind_nvrs_map = {
            "image": image_builds,
            "extras": extra_builds,
            "metadata": olm_builds,
        }
        _LOGGER.info(f"validate tracker bug {tracker_bugs}")
        bugs_by_type = validate_tracker_bugs(out, _LOGGER, tracker_bugs, kind_nvrs_map, permitted_bug_ids, False)
        image_bugs = extract_bugs(bugs_by_type.get("image", []), "image")
        extras_bugs = extract_bugs(bugs_by_type.get("extras", []), "extras")
        metadata_bugs = extract_bugs(bugs_by_type.get("metadata", []), "metadata")
        return image_bugs, extras_bugs, metadata_bugs, cve_list_map

    async def find_builds(self):
        """
        Run the elliott 'find-builds' command for images and return categorized build NVRs.
        Returns:
            tuple: Four lists containing:
                - payload_builds: NVRs of payload image builds
                - non_payload_builds: NVRs of non-payload image builds
                - olm_builds: NVRs of OLM bundle builds
                - olm_builds_not_found: NVRs of OLM operator builds for which no bundle build was found
        """
        cmd = self._elliott_base_command + ["find-builds", "--kind=image", "--json=-"]
        rc, stdout, stderr = await exectools.cmd_gather_async(cmd)
        if not stdout:
            _LOGGER.warning("No output received from find-builds command.")
            return [], [], [], []

        out = json.loads(stdout)
        _LOGGER.info("Find image builds: \n%s", stdout)

        return (
            out.get("payload", []),
            out.get("nonpayload", []),
            out.get("olm_builds", []),
            out.get("olm_builds_not_found", []),
        )

    def _build_repo_vars(self, build_repo_url: Optional[str]):
        build_repo_pull_url = (
            build_repo_url
            or self.runtime.config.get("build_config", {}).get("ocp_build_data_url")
            or constants.OCP_BUILD_DATA_URL
        )
        build_data_gitref = None
        if "@" in build_repo_pull_url:
            build_repo_pull_url, build_data_gitref = build_repo_pull_url.split("@", 1)

        build_data_push_url = (
            self.runtime.config.get("build_config", {}).get("ocp_build_data_push_url") or constants.OCP_BUILD_DATA_URL
        )
        return build_repo_pull_url, build_data_gitref, build_data_push_url


@cli.command("prepare-release-konflux")
@click.option(
    "-g",
    "--group",
    metavar='NAME',
    required=True,
    help="The group to operate on e.g. openshift-4.18",
)
@click.option(
    "--assembly",
    metavar="ASSEMBLY_NAME",
    required=True,
    callback=lambda ctx, param, value: value if value != "stream" else click.BadParameter("stream is not allowed for this command"),
    help="The assembly to operate on e.g. 4.18.5",
)
@click.option(
    '--build-repo-url',
    help='ocp-build-data repo to use. Defaults to group branch - to use a different branch/commit use repo@branch',
)
@click.option(
    '--shipment-repo-url',
    help='shipment-data repo to use for reading and as shipment MR target. Defaults to main branch. Should reside in gitlab.cee.redhat.com',
)
@click.option("--date", metavar="YYYY-MMM-DD", help="Expected release date (e.g. 2020-Nov-25)")
@pass_runtime
@click_coroutine
async def prepare_release(
    runtime: Runtime,
    group: str,
    assembly: str,
    build_repo_url: Optional[str],
    shipment_repo_url: Optional[str],
    date: Optional[str],
):
    check_env_var = lambda var_name, error_msg: os.getenv(var_name) or ValueError(error_msg)
    github_token = check_env_var('GITHUB_TOKEN', "GITHUB_TOKEN environment variable is required to create a pull request")
    gitlab_token = check_env_var("GITLAB_TOKEN", "GITLAB_TOKEN environment variable is required to create a merge request")
    slack_client = runtime.new_slack_client()
    slack_client.bind_channel(group)
    #await slack_client.say_in_thread(f":construction: prepare-release-konflux for {assembly} :construction:")
    try:
        # start pipeline
        pipeline = PrepareReleaseKonfluxPipeline(
            slack_client=slack_client,
            runtime=runtime,
            group=group,
            assembly=assembly,
            github_token=github_token,
            gitlab_token=gitlab_token,
            build_repo_url=build_repo_url,
            shipment_repo_url=shipment_repo_url,
            job_url=os.getenv('BUILD_URL'),
            date=date,
        )
        await pipeline.run()
        #await slack_client.say_in_thread(f":white_check_mark: prepare-release-konflux for {assembly} completes.")
    except Exception as e:
        #await slack_client.say_in_thread(f":warning: prepare-release-konflux for {assembly} has result FAILURE.")
        raise e

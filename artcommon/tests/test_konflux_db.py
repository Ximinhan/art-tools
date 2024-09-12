import asyncio
import os
from datetime import datetime, timedelta
from unittest import TestCase
from unittest.mock import patch

from artcommonlib.konflux.konflux_build_record import KonfluxBuildRecord
from artcommonlib.konflux.konflux_db import KonfluxDb


class TestKonfluxDB(TestCase):
    @patch('os.environ', {'DATASET_ID': 'dataset', 'TABLE_ID': 'builds',
                          'GOOGLE_CLOUD_PROJECT': 'project', 'GOOGLE_APPLICATION_CREDENTIALS': ''})
    @patch('artcommonlib.bigquery.bigquery.Client')
    def setUp(self, _):
        self.db = KonfluxDb()
        self.db.bq_client._table_ref = \
            f'{os.environ["GOOGLE_CLOUD_PROJECT"]}.{os.environ["DATASET_ID"]}.{os.environ["TABLE_ID"]}'

    def test_column_names(self):
        expected_names = {'name', 'group', 'version', 'release', 'assembly', 'el_target', 'arches',
                          'installed_packages', 'parent_images', 'source_repo', 'commitish', 'rebase_repo_url',
                          'rebase_commitish', 'embargoed', 'start_time', 'end_time', 'artifact_type', 'engine',
                          'image_pullspec', 'image_tag', 'outcome', 'art_job_url', 'build_pipeline_url',
                          'pipeline_commit', 'schema_level', 'ingestion_time', 'record_id', 'build_id', 'nvr'}
        names = set(self.db.column_names)
        self.assertEqual(names, expected_names)

    @patch('artcommonlib.bigquery.BigQueryClient.query')
    def test_add_builds(self, query_mock):
        build = KonfluxBuildRecord()

        self.db.add_build(build)
        query_mock.assert_called_once()

        query_mock.reset_mock()
        asyncio.run(self.db.add_builds([]))
        query_mock.assert_not_called()

        query_mock.reset_mock()
        asyncio.run(self.db.add_builds([build]))
        query_mock.assert_called_once()

        query_mock.reset_mock()
        asyncio.run(self.db.add_builds([build for _ in range(10)]))
        self.assertEqual(query_mock.call_count, 10)

    @patch('artcommonlib.bigquery.BigQueryClient.query')
    def test_search_builds_by_fields(self, query_mock):
        self.db.search_builds_by_fields(names=[], values=[])
        query_mock.assert_called_once_with('SELECT * FROM `project.dataset.builds`')

        query_mock.reset_mock()
        self.db.search_builds_by_fields(names=['name', 'group'], values=['ironic', 'openshift-4.18'])
        query_mock.assert_called_once_with(
            "SELECT * FROM `project.dataset.builds` WHERE `name` = 'ironic' AND `group` = 'openshift-4.18'")

        query_mock.reset_mock()
        self.db.search_builds_by_fields(names=['name', 'group'], values=['ironic', 'openshift-4.18'],
                                        order_by='start_time')
        query_mock.assert_called_once_with("SELECT * FROM `project.dataset.builds` WHERE `name` = 'ironic' "
                                           "AND `group` = 'openshift-4.18' ORDER BY `start_time` DESC")

        query_mock.reset_mock()
        self.db.search_builds_by_fields(names=['name', 'group'], values=['ironic', 'openshift-4.18'],
                                        order_by='start_time', sorting='ASC')
        query_mock.assert_called_once_with("SELECT * FROM `project.dataset.builds` WHERE `name` = 'ironic' "
                                           "AND `group` = 'openshift-4.18' ORDER BY `start_time` ASC")

        query_mock.reset_mock()
        self.db.search_builds_by_fields(names=['name', 'group'], values=['ironic', 'openshift-4.18'],
                                        order_by='start_time', sorting='ASC', limit=0)
        query_mock.assert_called_once_with("SELECT * FROM `project.dataset.builds` WHERE `name` = 'ironic' "
                                           "AND `group` = 'openshift-4.18' ORDER BY `start_time` ASC LIMIT 0")

        query_mock.reset_mock()
        self.db.search_builds_by_fields(names=['name', 'group'], values=['ironic', 'openshift-4.18'],
                                        order_by='start_time', sorting='ASC', limit=10)
        query_mock.assert_called_once_with("SELECT * FROM `project.dataset.builds` WHERE `name` = 'ironic' "
                                           "AND `group` = 'openshift-4.18' ORDER BY `start_time` ASC LIMIT 10")

        query_mock.reset_mock()
        with self.assertRaises(AssertionError):
            self.db.search_builds_by_fields(names=['name', 'group'], values=['ironic', 'openshift-4.18'],
                                            order_by='start_time', sorting='ASC', limit=-1)

    @patch('artcommonlib.konflux.konflux_db.datetime')
    @patch('artcommonlib.bigquery.BigQueryClient.query')
    def test_get_latest_build(self, query_mock, datetime_mock):
        now = datetime(2022, 1, 1, 12, 0, 0)
        lower_bound = now - 3 * timedelta(days=30)
        datetime_mock.now.return_value = now
        self.db.get_latest_build(name='ironic', group='openshift-4.18', outcome='success')
        query_mock.assert_called_once_with("SELECT * FROM `project.dataset.builds` WHERE name = 'ironic' "
                                           "AND `group` = 'openshift-4.18' AND outcome = 'success' "
                                           "AND assembly = 'stream' AND end_time IS NOT NULL "
                                           f"AND end_time < '{str(now)}' "
                                           f"AND start_time >= '{str(lower_bound)}' "
                                           f"AND start_time < '{now}' "
                                           "ORDER BY `start_time` DESC LIMIT 1")

        query_mock.reset_mock()
        asyncio.run(self.db.get_latest_builds(names=['ironic', 'ose-installer-artifacts'], group='openshift-4.18',
                                              outcome='success'))

        actual_calls = [query_mock.call_args_list[x][0][0] for x in range(0, 2)]
        self.assertIn("SELECT * FROM `project.dataset.builds` WHERE name = 'ironic' "
                      "AND `group` = 'openshift-4.18' AND outcome = 'success' "
                      "AND assembly = 'stream' AND end_time IS NOT NULL "
                      f"AND end_time < '{str(now)}' "
                      f"AND start_time >= '{str(lower_bound)}' "
                      f"AND start_time < '{now}' "
                      "ORDER BY `start_time` DESC LIMIT 1", actual_calls)

        self.assertIn("SELECT * FROM `project.dataset.builds` WHERE name = 'ose-installer-artifacts' "
                      "AND `group` = 'openshift-4.18' AND outcome = 'success' "
                      "AND assembly = 'stream' AND end_time IS NOT NULL "
                      f"AND end_time < '{str(now)}' "
                      f"AND start_time >= '{str(lower_bound)}' "
                      f"AND start_time < '{now}' "
                      "ORDER BY `start_time` DESC LIMIT 1", actual_calls)

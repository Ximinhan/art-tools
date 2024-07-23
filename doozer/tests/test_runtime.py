#!/usr/bin/env python
import unittest
from flexmock import flexmock
import logging

from artcommonlib import logutil, exectools
from artcommonlib.model import Model
from doozerlib import runtime


def stub_runtime():
    rt = runtime.Runtime(
        latest_parent_version=False,
        stage=False,
        branch='test-branch',
        rhpkg_config="",
    )
    rt._logger = logging.getLogger(__name__)
    rt.group_config = Model()
    return rt


if __name__ == "__main__":
    unittest.main()

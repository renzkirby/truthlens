import unittest

from django.core.cache import caches
from django.test.runner import (
    DebugSQLTextTestResult,
    DiscoverRunner,
    PDBDebugResult,
)


class _ClearDefaultCacheBeforeTestMixin:
    """Prevent cache/throttle state from leaking across isolated tests."""

    def startTest(self, test):
        caches["default"].clear()
        super().startTest(test)


class CacheClearingTextTestResult(
    _ClearDefaultCacheBeforeTestMixin,
    unittest.TextTestResult,
):
    pass


class CacheClearingDebugSQLTextTestResult(
    _ClearDefaultCacheBeforeTestMixin,
    DebugSQLTextTestResult,
):
    pass


class CacheClearingPDBDebugResult(
    _ClearDefaultCacheBeforeTestMixin,
    PDBDebugResult,
):
    pass


class TruthLensTestRunner(DiscoverRunner):
    """Run each test with a fresh default cache namespace/state."""

    def get_resultclass(self):
        if self.debug_sql:
            return CacheClearingDebugSQLTextTestResult
        if self.pdb:
            return CacheClearingPDBDebugResult
        return CacheClearingTextTestResult

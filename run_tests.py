#!/usr/bin/env python
"""
Standalone test runner for TruthLens moderation system tests
"""
import os
import sys
import django

# Add backend to path
sys.path.insert(0, r"c:\Users\Admin\Desktop\TruthLens\backend\truthlens_backend")

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "truthlens_backend.settings")
django.setup()

# Now run tests
from django.test.utils import get_runner
from django.conf import settings

TestRunner = get_runner(settings)
test_runner = TestRunner(verbosity=2, interactive=False, keepdb=False)

# Run only the moderator tests
failures = test_runner.run_tests(["api.tests.ModeratorEvidenceVerificationTests"])

sys.exit(bool(failures))

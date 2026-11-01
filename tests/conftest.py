"""Shared fixtures. The Home Assistant ones only apply when the test plugin is installed,
so the pure protocol tests also run with a plain ``pip install pytest``."""

import importlib.util

import pytest

if importlib.util.find_spec("pytest_homeassistant_custom_component") is not None:

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(enable_custom_integrations):
        """Let Home Assistant load custom_components/emoose_x300 during tests."""
        return

    @pytest.fixture
    def expected_lingering_timers() -> bool:
        """The MQTT integration's own periodic timer outlives the test; it is not ours."""
        return True

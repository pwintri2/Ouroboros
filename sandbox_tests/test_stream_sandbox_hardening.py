# sandbox_tests/test_stream_sandbox_hardening.py
# Phase 7.X — Sandbox hardening verificatietests
# Wintrip AI | task_id: wintrip-soc-008
#
# Verifieert dat _SANDBOX_DEFAULTS de vereiste hardening-instellingen bevat
# en dat run_python_code de juiste container-configuratie doorgeeft aan Docker.
#
# Geen echte Docker-daemon vereist: docker.from_env() wordt gemockt.
# Draait met: python sandbox_tests/test_stream_sandbox_hardening.py

import sys
import os
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Import de module — docker en reflector worden gemockt zodat
# de module geladen kan worden zonder echte Docker-daemon of ChromaDB.
# ---------------------------------------------------------------------------
_mock_docker = MagicMock()
_mock_reflector_module = MagicMock()

with patch.dict("sys.modules", {
    "docker": _mock_docker,
    "controller.reflector": _mock_reflector_module,
    "requests": MagicMock(),
}):
    from controller.sandbox import _SANDBOX_DEFAULTS, SandboxExecutor


# ---------------------------------------------------------------------------
# Tests: _SANDBOX_DEFAULTS structuur
# ---------------------------------------------------------------------------
class TestSandboxDefaults(unittest.TestCase):
    """Verifieert dat alle hardening-velden aanwezig zijn in _SANDBOX_DEFAULTS."""

    def test_netwerk_standaard_uitgeschakeld(self):
        """Netwerk moet standaard UIT zijn voor code-executie."""
        self.assertTrue(
            _SANDBOX_DEFAULTS.get("network_disabled"),
            "_SANDBOX_DEFAULTS['network_disabled'] moet True zijn (netwerk standaard uit)."
        )

    def test_geheugen_limiet_aanwezig(self):
        """mem_limit moet aanwezig zijn (DoD: resource limits)."""
        self.assertIn("mem_limit", _SANDBOX_DEFAULTS)
        self.assertIsNotNone(_SANDBOX_DEFAULTS["mem_limit"])

    def test_geheugen_limiet_niet_groter_dan_512m(self):
        """mem_limit mag niet groter zijn dan 512m."""
        raw = _SANDBOX_DEFAULTS["mem_limit"]
        # Normaliseer naar MB
        if isinstance(raw, str):
            value_mb = int(raw.rstrip("m").rstrip("M"))
        else:
            value_mb = raw // (1024 * 1024)
        self.assertLessEqual(value_mb, 512, f"mem_limit {raw} overschrijdt 512m.")

    def test_swap_limiet_aanwezig(self):
        """memswap_limit moet aanwezig zijn om swap-ontwijking te voorkomen."""
        self.assertIn("memswap_limit", _SANDBOX_DEFAULTS)

    def test_cpu_quota_aanwezig(self):
        """cpu_quota moet aanwezig zijn (CPU-limiet)."""
        self.assertIn("cpu_quota", _SANDBOX_DEFAULTS)
        self.assertGreater(_SANDBOX_DEFAULTS["cpu_quota"], 0)

    def test_cpu_period_aanwezig(self):
        """cpu_period moet aanwezig zijn (scheduling window)."""
        self.assertIn("cpu_period", _SANDBOX_DEFAULTS)
        self.assertGreater(_SANDBOX_DEFAULTS["cpu_period"], 0)

    def test_cpu_limiet_max_100_procent(self):
        """cpu_quota / cpu_period mag niet > 1.0 zijn (max 100% van 1 kern)."""
        ratio = _SANDBOX_DEFAULTS["cpu_quota"] / _SANDBOX_DEFAULTS["cpu_period"]
        self.assertLessEqual(ratio, 1.0, "CPU quota mag niet meer dan 100% zijn.")

    def test_pids_limiet_aanwezig(self):
        """pids_limit moet aanwezig zijn (fork-bomb preventie)."""
        self.assertIn("pids_limit", _SANDBOX_DEFAULTS)
        self.assertGreater(_SANDBOX_DEFAULTS["pids_limit"], 0)

    def test_pids_limiet_redelijk_begrensd(self):
        """pids_limit moet <= 256 zijn."""
        self.assertLessEqual(
            _SANDBOX_DEFAULTS["pids_limit"], 256,
            "pids_limit te hoog — stel in op <= 256 voor fork-bomb bescherming."
        )

    def test_rootfs_readonly(self):
        """read_only moet True zijn (rootfs read-only)."""
        self.assertTrue(
            _SANDBOX_DEFAULTS.get("read_only"),
            "_SANDBOX_DEFAULTS['read_only'] moet True zijn."
        )

    def test_tmpfs_aanwezig(self):
        """tmpfs moet aanwezig zijn als writable in-memory schrijfpad."""
        self.assertIn("tmpfs", _SANDBOX_DEFAULTS)
        self.assertIsInstance(_SANDBOX_DEFAULTS["tmpfs"], dict)
        self.assertTrue(len(_SANDBOX_DEFAULTS["tmpfs"]) > 0, "tmpfs dict moet minimaal één entry hebben.")

    def test_security_opt_no_new_privileges(self):
        """security_opt moet 'no-new-privileges:true' bevatten."""
        security_opts = _SANDBOX_DEFAULTS.get("security_opt", [])
        self.assertIn(
            "no-new-privileges:true",
            security_opts,
            "security_opt moet 'no-new-privileges:true' bevatten."
        )

    def test_image_is_python_slim(self):
        """Basis-image moet python:3.10-slim zijn."""
        self.assertEqual(_SANDBOX_DEFAULTS.get("image"), "python:3.10-slim")

    def test_detach_is_true(self):
        """detach moet True zijn voor asynchrone controle."""
        self.assertTrue(_SANDBOX_DEFAULTS.get("detach"))


# ---------------------------------------------------------------------------
# Tests: run_python_code container-configuratie (gemockte Docker)
# ---------------------------------------------------------------------------

def _maak_mock_executor() -> SandboxExecutor:
    """
    Maakt een SandboxExecutor met volledige Docker-mock.
    Geen echte container wordt gestart.
    """
    with patch.dict("sys.modules", {
        "docker": _mock_docker,
        "controller.reflector": _mock_reflector_module,
        "requests": MagicMock(),
    }):
        executor = SandboxExecutor.__new__(SandboxExecutor)
        executor.reflector = None
        # Mock Docker client
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.return_value = b"test output"
        mock_client.containers.run.return_value = mock_container
        mock_client.ping.return_value = True
        executor.client = mock_client
    return executor


class TestRunPythonCodeHardening(unittest.TestCase):
    """Verifieert dat run_python_code de juiste hardened configuratie doorgeeft."""

    def setUp(self):
        self.executor = _maak_mock_executor()

    def _get_run_kwargs(self):
        """Voert run_python_code uit en retourneert de kwargs die naar containers.run werden doorgegeven."""
        with patch("os.makedirs"), patch("tempfile.NamedTemporaryFile") as mock_tmp, \
             patch("os.path.exists", return_value=False):
            mock_file = MagicMock()
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_file.name = "/tmp/fake_script.py"
            mock_tmp.return_value = mock_file
            self.executor.run_python_code("print('test')", return_dict=True)
        return self.executor.client.containers.run.call_args

    def test_netwerk_uitgeschakeld_by_default(self):
        """network_disabled moet True zijn als allow_network=False (default)."""
        call_args = self._get_run_kwargs()
        kwargs = call_args.kwargs if call_args.kwargs else {}
        self.assertTrue(
            kwargs.get("network_disabled"),
            "network_disabled moet True zijn bij default allow_network=False."
        )

    def test_netwerk_ingeschakeld_met_allow_network(self):
        """network_disabled moet False zijn als allow_network=True."""
        with patch("os.makedirs"), patch("tempfile.NamedTemporaryFile") as mock_tmp, \
             patch("os.path.exists", return_value=False):
            mock_file = MagicMock()
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_file.name = "/tmp/fake_script.py"
            mock_tmp.return_value = mock_file
            self.executor.run_python_code("print('test')", return_dict=True, allow_network=True)
        call_args = self.executor.client.containers.run.call_args
        kwargs = call_args.kwargs if call_args.kwargs else {}
        self.assertFalse(
            kwargs.get("network_disabled"),
            "network_disabled moet False zijn als allow_network=True."
        )

    def test_mem_limit_doorgegeven(self):
        """mem_limit moet worden doorgegeven aan containers.run."""
        call_args = self._get_run_kwargs()
        kwargs = call_args.kwargs if call_args.kwargs else {}
        self.assertIn("mem_limit", kwargs)

    def test_read_only_doorgegeven(self):
        """read_only moet worden doorgegeven aan containers.run."""
        call_args = self._get_run_kwargs()
        kwargs = call_args.kwargs if call_args.kwargs else {}
        self.assertTrue(kwargs.get("read_only"))

    def test_pids_limit_doorgegeven(self):
        """pids_limit moet worden doorgegeven aan containers.run."""
        call_args = self._get_run_kwargs()
        kwargs = call_args.kwargs if call_args.kwargs else {}
        self.assertIn("pids_limit", kwargs)

    def test_security_opt_doorgegeven(self):
        """security_opt moet worden doorgegeven aan containers.run."""
        call_args = self._get_run_kwargs()
        kwargs = call_args.kwargs if call_args.kwargs else {}
        security_opts = kwargs.get("security_opt", [])
        self.assertIn("no-new-privileges:true", security_opts)

    def test_script_volume_readonly(self):
        """/script.py volume moet read-only zijn (mode='ro')."""
        call_args = self._get_run_kwargs()
        kwargs = call_args.kwargs if call_args.kwargs else {}
        volumes = kwargs.get("volumes", {})
        script_vol = next((v for v in volumes.values() if v.get("bind") == "/script.py"), None)
        self.assertIsNotNone(script_vol, "/script.py volume niet gevonden.")
        self.assertEqual(script_vol.get("mode"), "ro")

    def test_data_volume_readwrite(self):
        """/app/data volume moet read-write zijn (mode='rw')."""
        call_args = self._get_run_kwargs()
        kwargs = call_args.kwargs if call_args.kwargs else {}
        volumes = kwargs.get("volumes", {})
        data_vol = next((v for v in volumes.values() if v.get("bind") == "/app/data"), None)
        self.assertIsNotNone(data_vol, "/app/data volume niet gevonden.")
        self.assertEqual(data_vol.get("mode"), "rw")

    def test_docker_offline_geeft_foutmelding(self):
        """Als Docker offline is, geeft run_python_code een foutmelding terug."""
        self.executor.client = None
        result = self.executor.run_python_code("print('test')", return_dict=True)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "docker_offline")


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

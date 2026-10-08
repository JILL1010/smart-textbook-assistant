import importlib.util
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import mock_open, patch

launcher_path = Path(__file__).resolve().parents[2] / "desktop" / "launcher.py"
spec = importlib.util.spec_from_file_location("desktop_launcher", launcher_path)
launcher = importlib.util.module_from_spec(spec)
with patch("builtins.open", mock_open()):
    spec.loader.exec_module(launcher)


class DesktopReliabilityTests(unittest.TestCase):
    def test_occupied_port_is_skipped(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen(1)
            port = occupied.getsockname()[1]
            chosen = launcher._find_free_port(port)
            self.assertGreater(chosen, port)
            self.assertLess(chosen, port + 100)

    def test_web_process_gets_runtime_api_port(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "node.exe").touch()
            server = root / "standalone" / "apps" / "web" / "server.js"
            server.parent.mkdir(parents=True)
            server.touch()
            with patch.object(launcher.subprocess, "Popen") as spawn:
                launcher._start_web(root, root, 3002, 8083)
            environment = spawn.call_args.kwargs["env"]
            self.assertEqual(environment["API_UPSTREAM_URL"], "http://127.0.0.1:8083")
            self.assertEqual(environment["PORT"], "3002")

    def test_api_audio_directory_is_independent_of_working_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original_path = launcher.sys.path[:]
            try:
                with patch.dict(os.environ, {}, clear=False), patch("uvicorn.run") as run:
                    thread = launcher._start_api(root, 8083)
                    thread.join(timeout=2)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual(os.environ["AUDIO_DIR"], str(root / "data" / "audio"))
                    self.assertEqual(run.call_args.kwargs["port"], 8083)
            finally:
                launcher.sys.path[:] = original_path

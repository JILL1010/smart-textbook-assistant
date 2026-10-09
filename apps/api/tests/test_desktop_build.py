import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[2] / "desktop" / "build.py"
spec = importlib.util.spec_from_file_location("desktop_build", path)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class DesktopBuildTests(unittest.TestCase):
    def test_cleanup_refuses_workspace_and_dist_roots(self):
        for path in (build.ROOT, build.ROOT / "dist", build.ROOT.parent):
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                build.remove_build_directory(path)

    def test_materialized_bundle_keeps_dependencies_and_excludes_private_configuration(self):
        (build.ROOT / "dist").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build.ROOT / "dist") as folder:
            root = Path(folder)
            source = root / "source"
            web = source / "apps" / "web"
            web.mkdir(parents=True)
            (web / "server.js").write_text("require('fixture')", encoding="utf-8")
            module = web / "node_modules" / "fixture"
            module.mkdir(parents=True)
            (module / "index.js").write_text("module.exports = 1", encoding="utf-8")
            (module / "LICENSE").write_text("fixture license", encoding="utf-8")
            (web / ".env").write_text("PRIVATE_SENTINEL=secret", encoding="utf-8")
            helper = source / "node_modules/.pnpm/helper@1.0.0/node_modules/@fixture/helper"
            helper.mkdir(parents=True)
            (helper / "package.json").write_text('{"name":"@fixture/helper","version":"1.0.0"}', encoding="utf-8")
            (helper / "index.js").write_text("module.exports = 2", encoding="utf-8")
            destination = root / "bundle"
            with patch.object(build, "WEB_DIR", root / "missing"), patch.object(build, "run_shell") as shell:
                build.step_materialize_standalone(source, destination)
            shell.assert_not_called()
            self.assertTrue((destination / "apps/web/node_modules/fixture/index.js").is_file())
            self.assertTrue((destination / "apps/web/node_modules/fixture/LICENSE").is_file())
            self.assertFalse((destination / "apps/web/.env").exists())
            self.assertTrue((destination / "apps/web/node_modules/@fixture/helper/index.js").is_file())
            self.assertFalse((destination / "node_modules/.pnpm").exists())

    def test_conflicting_traced_versions_fail_instead_of_silently_changing_resolution(self):
        (build.ROOT / "dist").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build.ROOT / "dist") as folder:
            root = Path(folder)
            source = root / "source"
            web = source / "apps/web"
            web.mkdir(parents=True)
            (web / "server.js").write_text("fixture", encoding="utf-8")
            for version in ("1.0.0", "2.0.0"):
                module = source / f"node_modules/.pnpm/helper@{version}/node_modules/helper"
                module.mkdir(parents=True)
                (module / "package.json").write_text(f'{{"name":"helper","version":"{version}"}}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Multiple traced versions"), patch.object(build, "WEB_DIR", root / "missing"):
                build.step_materialize_standalone(source, root / "bundle")

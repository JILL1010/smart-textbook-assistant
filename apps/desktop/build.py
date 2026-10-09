"""
智能课本助手 — Build Script

Orchestrates: Frontend build → Node.js portable download → PyInstaller packaging.
"""
import os
import sys
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
import argparse
import re
import json
from datetime import datetime, timezone
from importlib.metadata import distributions
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent  # vibecoding/
WEB_DIR = ROOT / "apps" / "web"
API_DIR = ROOT / "apps" / "api"
DESKTOP_DIR = ROOT / "apps" / "desktop"
DIST_DIR = ROOT / "dist"

# https://nodejs.org/dist
NODE_VERSION = "v24.13.0"
NODE_URL = f"https://nodejs.org/dist/{NODE_VERSION}/node-{NODE_VERSION}-win-x64.zip"


def remove_build_directory(path: Path) -> None:
    target = path.resolve()
    allowed = (ROOT / "dist").resolve()
    if target == allowed or not target.is_relative_to(allowed):
        raise RuntimeError(f"Build cleanup outside dist refused: {target}")
    if path.exists():
        shutil.rmtree(path)


def run(cmd: list[str], cwd: Path | None = None, **kwargs) -> None:
    """Run a command, printing output in real-time."""
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=cwd or ROOT, **kwargs)
    if result.returncode != 0:
        print(f"  ERROR: exit code {result.returncode}")
        sys.exit(result.returncode)


def run_shell(cmd: str, cwd: Path | None = None, **kwargs) -> None:
    """Run a shell command (use for npm/pnpm which are shell scripts)."""
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, cwd=cwd or ROOT, shell=True, **kwargs)
    if result.returncode != 0:
        print(f"  ERROR: exit code {result.returncode}")
        sys.exit(result.returncode)


def step_build_frontend() -> None:
    """Build Next.js production build with standalone output."""
    print("\n[1/4] Building frontend (Next.js standalone)...")
    env = os.environ.copy()
    env["NEXT_PUBLIC_API_URL"] = ""
    run_shell("pnpm build", cwd=WEB_DIR, env=env)

    standalone = WEB_DIR / ".next" / "standalone"
    if not (standalone / "apps" / "web" / "server.js").exists():
        print(f"  ERROR: server.js not found in {standalone}")
        sys.exit(1)
    print(f"  Standalone build ready at: {standalone}")


def step_download_node() -> Path:
    """Download portable Node.js for Windows."""
    print(f"\n[2/4] Downloading Node.js {NODE_VERSION} portable...")

    cache_dir = Path(tempfile.gettempdir()) / "textbook-assistant-cache"
    cache_dir.mkdir(exist_ok=True)

    node_exe = cache_dir / f"node-{NODE_VERSION}.exe"
    if node_exe.exists():
        print(f"  Using cached: {node_exe}")
        return node_exe

    zip_path = cache_dir / f"node-{NODE_VERSION}-win-x64.zip"
    if not zip_path.exists():
        print(f"  Downloading {NODE_URL}...")
        urllib.request.urlretrieve(NODE_URL, zip_path)
        print(f"  Downloaded to {zip_path}")

    print("  Extracting...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.endswith("node.exe"):
                with zf.open(name) as src, open(node_exe, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                break
    print(f"  Node.js extracted to: {node_exe}")
    return node_exe


def step_materialize_standalone(standalone_src: Path, dest: Path) -> None:
    """Materialize the traced, locked dependencies without requiring another install."""
    if dest.exists():
        remove_build_directory(dest)

    def _ignore_private_files(src_dir: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            if name in ("__pycache__", ".git", ".cache") or name.startswith(".env"):
                ignored.add(name)
        return ignored

    print("  Copying standalone and materializing traced dependency links...")
    shutil.copytree(standalone_src, dest, symlinks=False, ignore=_ignore_private_files)

    # Verify server.js exists
    web_dir = dest / "apps" / "web"
    server_js = web_dir / "server.js"
    if not server_js.exists():
        print(f"  ERROR: server.js not found after copy at {server_js}")
        sys.exit(1)

    # Dereferencing pnpm junctions moves a package away from the virtual-store
    # siblings that supplied its dependencies. Expose the traced packages by name.
    store = dest / "node_modules" / ".pnpm"
    manifests = list(store.glob("*/node_modules/*/package.json")) + list(store.glob("*/node_modules/@*/*/package.json"))
    versions = {}
    for manifest in manifests:
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
        name, version = metadata["name"], metadata["version"]
        if not re.fullmatch(r"(?:@[a-z0-9_.-]+/)?[a-z0-9_.-]+", name):
            raise RuntimeError(f"Invalid traced package name: {name}")
        if name in versions and versions[name] != version:
            raise RuntimeError(f"Multiple traced versions of {name}; cannot flatten safely")
        versions[name] = version
        target = web_dir / "node_modules" / name
        if target.exists():
            existing = json.loads((target / "package.json").read_text(encoding="utf-8"))
            if existing.get("version") != version:
                raise RuntimeError(f"Traced dependency version conflict: {name}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        installed = ROOT / manifest.parent.relative_to(dest)
        source = installed if (installed / "package.json").is_file() else manifest.parent
        installed_metadata = json.loads((source / "package.json").read_text(encoding="utf-8"))
        if (installed_metadata.get("name"), installed_metadata.get("version")) != (name, version):
            raise RuntimeError(f"Installed dependency differs from traced build: {name}")
        # Full matching packages retain their licenses as well as runtime files.
        shutil.copytree(source, target, symlinks=False, ignore=_ignore_private_files)
    if store.exists():
        remove_build_directory(store)

    # Copy .next/static (CSS/JS/assets) — not included in standalone output by default
    static_src = WEB_DIR / ".next" / "static"
    static_dst = web_dir / ".next" / "static"
    if static_src.exists():
        if static_dst.exists():
            remove_build_directory(static_dst)
        shutil.copytree(static_src, static_dst)
        print(f"  Copied .next/static → {static_dst}")
    else:
        print(f"  WARNING: .next/static not found at {static_src}")

    # Copy public/ (favicon, robots.txt, etc.)
    public_src = WEB_DIR / "public"
    public_dst = web_dir / "public"
    if public_src.exists() and any(public_src.iterdir()):
        if public_dst.exists():
            remove_build_directory(public_dst)
        shutil.copytree(public_src, public_dst)
        print(f"  Copied public/ → {public_dst}")

    print("  Traced dependencies copied without links or a fresh install.")


def step_pyinstaller(node_exe: Path) -> None:
    """Package with PyInstaller directly from source paths."""
    print("\n[3/4] Materializing standalone for packaging...")

    standalone_src = WEB_DIR / ".next" / "standalone"
    bundle = DIST_DIR / ".build-stage"
    bundle.mkdir(parents=True, exist_ok=True)
    step_materialize_standalone(standalone_src, bundle / "standalone")

    # Copy API code
    api_dst = bundle / "api"
    print(f"  Copying API → {api_dst}")
    if api_dst.exists():
        remove_build_directory(api_dst)
    shutil.copytree(API_DIR, api_dst, ignore=shutil.ignore_patterns(
        "__pycache__", ".venv", "data", "uploads", ".env*", ".git", "tests", "*.pdf"
    ))

    # Copy Node.js portable
    node_dst = bundle / "node.exe"
    print(f"  Copying node.exe → {node_dst}")
    shutil.copy2(node_exe, node_dst)

    # Copy launcher
    launcher_dst = bundle / "launcher.py"
    print(f"  Copying launcher → {launcher_dst}")
    shutil.copy2(DESKTOP_DIR / "launcher.py", launcher_dst)

    print("\n[4/4] Packaging with PyInstaller...")

    DIST_DIR.mkdir(exist_ok=True)

    # Clean previous build output
    output_dir = DIST_DIR / "智能课本助手"
    if output_dir.exists():
        print(f"  Cleaning previous build: {output_dir}")
        if (output_dir / "data").exists() or (output_dir / ".env").exists():
            raise RuntimeError("Output contains user data; choose a new --output-dir")
        remove_build_directory(output_dir)

    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
a = Analysis(
    [r"{bundle / 'launcher.py'}"],
    pathex=[r"{bundle / 'api'}"],
    binaries=[],
    datas=[
        (r"{bundle / 'api'}", "api"),
    ],
    hiddenimports=["uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
                   "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
                   "uvicorn.lifespan", "uvicorn.lifespan.on",
                   "fastapi", "fastapi.middleware", "fastapi.middleware.cors",
                   "sqlalchemy", "pydantic_settings",
                   "docx", "fitz", "edge_tts", "openai",
                   "aiofiles", "python_multipart"],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="智能课本助手",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="智能课本助手",
)
'''

    spec_path = bundle / "app.spec"
    spec_path.write_text(spec_content, encoding="utf-8")
    print(f"  Spec written to: {spec_path}")

    run([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--distpath", str(DIST_DIR),
        "--workpath", str(bundle / "build"),
        str(spec_path),
    ])

    output = DIST_DIR / "智能课本助手"
    if output.exists():
        # Node owns these resources, including its native addons. Keep them opaque
        # to PyInstaller's Python binary classification and dependency analysis.
        shutil.copytree(bundle / "standalone", output / "_internal" / "standalone")
        # Copy node.exe to output root so launcher can use it without PyInstaller temp dir
        node_dst = output / "node.exe"
        if not node_dst.exists():
            shutil.copy2(bundle / "node.exe", node_dst)
            print(f"  node.exe → {node_dst}")
        # Remove redundant node.exe from _internal (saves 86MB)
        node_dup = output / "_internal" / "node.exe"
        if node_dup.exists():
            try:
                node_dup.unlink()
                print(f"  Removed duplicate: {node_dup}")
            except PermissionError:
                print(f"  WARNING: Cannot remove {node_dup} — permission denied (harmless, but wastes 86MB)")
        for name in (".env.example", "LICENSE", "README.md", "CONTRIBUTING.md"):
            shutil.copy2(ROOT / name, output / name)
        shutil.copy2(DESKTOP_DIR / "START_HERE.md", output / "START_HERE.md")
        notices = output / "licenses"
        notices.mkdir(exist_ok=True)
        for distribution in distributions():
            for file in distribution.files or []:
                if any(marker in file.name.lower() for marker in ("license", "copying", "notice")) and ".dist-info" in str(file):
                    source = Path(distribution.locate_file(file))
                    if source.is_file():
                        target = notices / distribution.metadata["Name"] / str(file).split(".dist-info/", 1)[-1]
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
        for source, name in [(node_exe.parent / "LICENSE", "node.txt"), (Path(sys.base_prefix) / "LICENSE.txt", "python.txt")]:
            if source.is_file():
                shutil.copy2(source, notices / name)
        if not (notices / "node.txt").exists():
            version = subprocess.check_output([str(node_exe), "--version"], text=True).strip()
            if not re.fullmatch(r"v\d+\.\d+\.\d+", version):
                raise RuntimeError("Cannot determine the bundled Node.js license version")
            urllib.request.urlretrieve(f"https://raw.githubusercontent.com/nodejs/node/{version}/LICENSE", notices / "node.txt")

        print(f"\n  Output: {output}")
        exe = output / "智能课本助手.exe"
        if exe.exists():
            print(f"  Executable: {exe}")
    else:
        print(f"\n  WARNING: Output directory {output} not found")


def main() -> None:
    global DIST_DIR
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--node-path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist" / "releases" / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    DIST_DIR = args.output_dir.resolve()
    if not DIST_DIR.is_relative_to((ROOT / "dist").resolve()) or DIST_DIR == (ROOT / "dist").resolve():
        parser.error("--output-dir must be a subdirectory of this project's dist/")
    print("=" * 50)
    print("  智能课本助手 — Desktop Build")
    print("=" * 50)

    if not args.skip_frontend:
        step_build_frontend()
    node_exe = args.node_path.resolve() if args.node_path else step_download_node()
    if not node_exe.is_file():
        parser.error("Node executable does not exist")
    step_pyinstaller(node_exe)

    print("\n" + "=" * 50)
    print("  Build complete!")
    print(f"  Output: {DIST_DIR / '智能课本助手' / '智能课本助手.exe'}")
    print("=" * 50)


if __name__ == "__main__":
    main()

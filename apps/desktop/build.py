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
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent  # vibecoding/
WEB_DIR = ROOT / "apps" / "web"
API_DIR = ROOT / "apps" / "api"
DESKTOP_DIR = ROOT / "apps" / "desktop"
DIST_DIR = ROOT / "dist"

# https://nodejs.org/dist
NODE_VERSION = "v24.13.0"
NODE_URL = f"https://nodejs.org/dist/{NODE_VERSION}/node-{NODE_VERSION}-win-x64.zip"


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
    """Copy standalone directory and create real node_modules via npm install."""
    if dest.exists():
        shutil.rmtree(dest)

    # Copy everything EXCEPT node_modules (will reinstall with npm)
    def _ignore_node_modules(src_dir: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            if name == "node_modules":
                ignored.add(name)
            elif name in ("__pycache__", ".git", ".cache"):
                ignored.add(name)
        return ignored

    print("  Copying standalone (excluding node_modules)...")
    shutil.copytree(standalone_src, dest, symlinks=True, ignore=_ignore_node_modules)

    # Verify server.js exists
    web_dir = dest / "apps" / "web"
    server_js = web_dir / "server.js"
    if not server_js.exists():
        print(f"  ERROR: server.js not found after copy at {server_js}")
        sys.exit(1)

    # Copy .next/static (CSS/JS/assets) — not included in standalone output by default
    static_src = WEB_DIR / ".next" / "static"
    static_dst = web_dir / ".next" / "static"
    if static_src.exists():
        if static_dst.exists():
            shutil.rmtree(static_dst)
        shutil.copytree(static_src, static_dst)
        print(f"  Copied .next/static → {static_dst}")
    else:
        print(f"  WARNING: .next/static not found at {static_src}")

    # Copy public/ (favicon, robots.txt, etc.)
    public_src = WEB_DIR / "public"
    public_dst = web_dir / "public"
    if public_src.exists() and any(public_src.iterdir()):
        if public_dst.exists():
            shutil.rmtree(public_dst)
        shutil.copytree(public_src, public_dst)
        print(f"  Copied public/ → {public_dst}")

    # Run npm install to get real node_modules (no symlinks)
    print("  Installing production dependencies with npm...")
    run_shell("npm install --omit=dev --legacy-peer-deps --no-optional", cwd=web_dir)
    print("  Dependencies installed.")


def step_pyinstaller(node_exe: Path) -> None:
    """Package with PyInstaller directly from source paths."""
    print("\n[3/4] Materializing standalone for packaging...")

    standalone_src = WEB_DIR / ".next" / "standalone"
    bundle = Path(tempfile.gettempdir()) / "textbook-assistant-bundle"
    step_materialize_standalone(standalone_src, bundle / "standalone")

    # Copy API code
    api_dst = bundle / "api"
    print(f"  Copying API → {api_dst}")
    if api_dst.exists():
        shutil.rmtree(api_dst)
    shutil.copytree(API_DIR, api_dst, ignore=shutil.ignore_patterns(
        "__pycache__", ".venv", "data", "uploads", ".env", ".git"
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
        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(output_dir)],
                       check=False, timeout=30)
        if output_dir.exists():
            print(f"  WARNING: Could not fully clean {output_dir}, continuing anyway")

    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
a = Analysis(
    [r"{bundle / 'launcher.py'}"],
    pathex=[r"{bundle / 'api'}"],
    binaries=[],
    datas=[
        (r"{bundle / 'standalone'}", "standalone"),
        (r"{bundle / 'api'}", "api"),
        (r"{bundle / 'node.exe'}", "node.exe"),
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

# Filter out large user data from EXE PKG (keep stdlib data like encodings).
# These user data files are still included in COLLECT below → _internal/.
_user_data_dests = {{"standalone", "api", "node.exe"}}
_exe_datas = [t for t in a.datas if t[0] not in _user_data_dests]

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    _exe_datas,
    [],
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
        # Copy .env to output root so API config can be loaded at runtime
        env_src = API_DIR / ".env"
        env_dst = output / ".env"
        if env_src.exists():
            shutil.copy2(env_src, env_dst)
            print(f"  .env → {env_dst}")
        else:
            print(f"  WARNING: .env not found at {env_src}, API key will not be configured")

        print(f"\n  Output: {output}")
        exe = output / "智能课本助手.exe"
        if exe.exists():
            print(f"  Executable: {exe}")
    else:
        print(f"\n  WARNING: Output directory {output} not found")


def main() -> None:
    print("=" * 50)
    print("  智能课本助手 — Desktop Build")
    print("=" * 50)

    step_build_frontend()
    node_exe = step_download_node()
    step_pyinstaller(node_exe)

    print("\n" + "=" * 50)
    print("  Build complete!")
    print(f"  Output: {DIST_DIR / '智能课本助手' / '智能课本助手.exe'}")
    print("=" * 50)


if __name__ == "__main__":
    main()

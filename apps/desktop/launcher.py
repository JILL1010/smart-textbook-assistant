"""
智能课本助手 — Desktop Launcher

Starts FastAPI backend + Next.js standalone frontend, opens browser.
Supports both dev mode (python launcher.py) and PyInstaller bundle mode.
"""
import os
import shutil
import sys
import time
import socket
import subprocess
import tempfile
import threading
import webbrowser
import traceback
from pathlib import Path

# Early crash detection: write marker using raw file I/O (no imports needed beyond builtins)
try:
    _marker = os.path.join(tempfile.gettempdir(), "sb_launcher_startup.txt")
    with open(_marker, "w") as _f:
        _f.write(f"module_loaded|frozen={getattr(sys, 'frozen', False)}|exe={sys.executable}\n")
except Exception:
    pass


# --- Logging ---

LOG_FILE = None

def _log(msg: str) -> None:
    """Write to log file and print to stdout."""
    print(msg, flush=True)
    global LOG_FILE
    if LOG_FILE:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass


# --- Path resolution ---

def _is_frozen() -> bool:
    """True when running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def _bundle_dir() -> Path:
    """Directory containing bundled resources (PyInstaller temp or source tree)."""
    if _is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent  # apps/


def _data_dir() -> Path:
    """Directory for persistent data (DB, uploads, audio)."""
    if _is_frozen():
        # Use the directory containing the .exe
        return Path(sys.executable).resolve().parent
    # Dev: use apps/api/ as working directory
    return Path(__file__).resolve().parent.parent / "api"


# --- Ports ---

API_PORT = 8081
WEB_PORT = 3000


def _find_free_port(start: int) -> int:
    """Find a free port starting from `start`."""
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start  # fallback


def _wait_for_port(port: int, timeout: float = 30) -> bool:
    """Wait until a server is listening on the given port."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.3)
    return False


# --- FastAPI runner ---

def _start_api(data_dir: Path, port: int) -> threading.Thread:
    """Start the FastAPI server in a background thread."""
    # Ensure data directories exist
    (data_dir / "data" / "audio").mkdir(parents=True, exist_ok=True)
    (data_dir / "uploads").mkdir(parents=True, exist_ok=True)

    # Set environment for the API process
    os.environ["DATABASE_URL"] = f"sqlite:///{(data_dir / 'data' / 'app.db').as_posix()}"
    os.environ["UPLOAD_DIR"] = str(data_dir / "uploads")
    os.environ["AUDIO_DIR"] = str(data_dir / "data" / "audio")

    # Load .env from data dir if present (user can edit it next to the EXE)
    env_path = data_dir / ".env"
    if env_path.exists():
        _log(f"[launcher] 加载环境配置: {env_path}")
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key, val = key.strip(), val.strip()
                    if key and key not in ("DATABASE_URL", "UPLOAD_DIR", "AUDIO_DIR", "CORS_ORIGINS"):
                        os.environ[key] = val
    else:
        _log("[launcher] 未找到 .env 配置文件，将使用默认设置")

    api_dir = _bundle_dir() / "api"

    import uvicorn

    # Ensure api_dir is on sys.path so uvicorn can import main:app
    sys.path.insert(0, str(api_dir))
    _log(f"[launcher] API 模块搜索路径: {api_dir}")

    def _run():
        try:
            uvicorn.run(
                "main:app",
                host="127.0.0.1",
                port=port,
                log_level="info",
                reload=False,
            )
        except Exception:
            _log(f"[launcher] API 线程异常:\n{traceback.format_exc()}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


# --- Next.js standalone runner ---

def _start_web(bundle_dir: Path, data_dir: Path, web_port: int, api_port: int) -> subprocess.Popen:
    """Start Next.js standalone server as a subprocess."""
    # Copy node.exe to data dir — PyInstaller temp extraction dir may deny execution
    node_exe = data_dir / "node.exe"
    if not node_exe.exists():
        src = bundle_dir / "node.exe"
        if not src.exists():
            raise FileNotFoundError(f"Node.js not found at {src}")
        shutil.copy2(src, node_exe)
        node_exe.chmod(0o755)

    standalone_dir = bundle_dir / "standalone" / "apps" / "web"
    server_js = standalone_dir / "server.js"
    if not server_js.exists():
        raise FileNotFoundError(f"server.js not found at {server_js}")

    env = os.environ.copy()
    env["PORT"] = str(web_port)
    env["API_UPSTREAM_URL"] = f"http://127.0.0.1:{api_port}"
    env["HOSTNAME"] = "127.0.0.1"

    proc = subprocess.Popen(
        [str(node_exe), str(server_js)],
        cwd=str(standalone_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc


# --- Main ---

def main() -> None:
    global LOG_FILE

    bundle_dir = _bundle_dir()
    data_dir = _data_dir()

    # Set up log file early
    LOG_FILE = str(data_dir / "launcher.log")
    try:
        (data_dir / "data" / "audio").mkdir(parents=True, exist_ok=True)
        (data_dir / "uploads").mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    _log("=" * 50)
    _log("  智能课本助手 — Smart Textbook Assistant")
    _log("=" * 50)

    if _is_frozen():
        _log(f"[launcher] 打包模式 (PyInstaller)")
    _log(f"[launcher] 资源目录: {bundle_dir}")
    _log(f"[launcher] 数据目录: {data_dir}")
    _log(f"[launcher] 日志文件: {LOG_FILE}")

    # Resolve ports
    api_port = _find_free_port(API_PORT)
    web_port = _find_free_port(WEB_PORT)
    os.environ["CORS_ORIGINS"] = f"http://127.0.0.1:{web_port},http://localhost:{web_port}"
    _log(f"[launcher] API 端口: {api_port}")
    _log(f"[launcher] Web 端口: {web_port}")

    # Start FastAPI
    _log("[launcher] 启动后端服务...")
    api_thread = _start_api(data_dir, api_port)

    if not _wait_for_port(api_port, timeout=30):
        _log("[launcher] 错误: 后端服务启动超时")
        _log("--- Last log entries above ---")
        sys.exit(1)
    _log("[launcher] 后端服务已就绪")

    # Start Next.js
    _log("[launcher] 启动前端服务...")
    try:
        web_proc = _start_web(bundle_dir, data_dir, web_port, api_port)
    except FileNotFoundError as e:
        _log(f"[launcher] 错误: {e}")
        _log(traceback.format_exc())
        sys.exit(1)
    except Exception as e:
        _log(f"[launcher] 启动前端时发生错误: {e}")
        _log(traceback.format_exc())
        sys.exit(1)

    if not _wait_for_port(web_port, timeout=60):
        _log("[launcher] 错误: 前端服务启动超时")
        web_proc.kill()
        sys.exit(1)
    _log("[launcher] 前端服务已就绪")

    # Open browser
    url = f"http://127.0.0.1:{web_port}"
    _log(f"[launcher] 打开浏览器: {url}")
    webbrowser.open(url)

    _log("[launcher] 应用运行中。关闭此窗口即可退出。")

    # Wait for shutdown
    try:
        web_proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        _log("[launcher] 正在关闭...")
        web_proc.terminate()
        try:
            web_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            web_proc.kill()
        _log("[launcher] 已退出")


if __name__ == "__main__":
    main()

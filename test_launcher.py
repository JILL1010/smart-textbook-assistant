"""Test the packaged launcher — use text mode for line buffering."""
import subprocess
import time
import os
import sys
import threading

EXE_PATH = r"D:\vibecoding\dist\智能课本助手\智能课本助手.exe"
CWD = os.path.dirname(EXE_PATH)

os.chdir(CWD)

proc = subprocess.Popen(
    [EXE_PATH],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    encoding="utf-8",
    errors="replace",
)

print(f"Started PID: {proc.pid}")
output_lines = []

def read_output():
    for line in proc.stdout:
        output_lines.append(line.rstrip())
        print(line, end="", flush=True)

reader = threading.Thread(target=read_output, daemon=True)
reader.start()

for i in range(30):
    time.sleep(1)
    if proc.poll() is not None:
        print(f"\nProcess exited after {i+1}s with code {proc.returncode}")
        break
else:
    print(f"\nTimeout after 30s, terminating...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except:
        proc.kill()

reader.join(timeout=3)
print(f"Total lines: {len(output_lines)}")

# Also check if data directories were created
for d in [r"D:\vibecoding\dist\智能课本助手\data",
           r"D:\vibecoding\dist\智能课本助手\uploads"]:
    if os.path.exists(d):
        print(f"  EXISTS: {d}")
        for f in os.listdir(d):
            print(f"    {f}")

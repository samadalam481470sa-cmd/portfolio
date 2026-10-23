"""HomeGrok's own code runner: Python that HomeGrok writes runs by itself, inside a macOS sandbox.

macOS (sandbox-exec) enforces the rules, not HomeGrok, so even code planted by a malicious web page
can't escape them:
  * no network at all;
  * no reading your home folder (documents, browser data, keychains, SSH keys, HomeGrok's own files);
  * writing only inside its own scratch folder;
  * limited time, memory and output.
"""
import os
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TIME_LIMIT = 60          # seconds
MEMORY_LIMIT = 1 << 30   # 1 GB
OUTPUT_LIMIT = 20_000    # characters


def _profile(scratch):
    home = str(Path.home())
    return f"""(version 1)
(deny default)
(allow process-fork signal sysctl-read mach-lookup ipc-posix-shm iokit-open)
(allow process-exec (literal "{Path(sys.executable).resolve()}"))
(allow file-read*)
(deny file-read* (subpath "{home}"))
(allow file-read* (subpath "{Path(sys.prefix).resolve()}") (subpath "{Path(sys.base_prefix).resolve()}"))
(allow file-read* file-write* (subpath "{scratch}"))
(allow file-write* (literal "/dev/null"))
(deny network*)
"""


def _limits():
    resource.setrlimit(resource.RLIMIT_CPU, (TIME_LIMIT, TIME_LIMIT))
    resource.setrlimit(resource.RLIMIT_FSIZE, (50 << 20, 50 << 20))
    try:
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
    except (ValueError, OSError):
        pass


def run_python(code, ws):
    """Run code in the sandbox. Returns {"ok", "output", "seconds", "files"}."""
    root = ws.root / "sandbox"
    root.mkdir(exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="run-", dir=root)).resolve()
    (scratch / "main.py").write_text(code)
    start = time.time()
    try:
        proc = subprocess.run(
            ["/usr/bin/sandbox-exec", "-p", _profile(scratch), sys.executable, "-I", "main.py"],
            cwd=scratch, capture_output=True, text=True, timeout=TIME_LIMIT + 5, preexec_fn=_limits,
            env={"PATH": "/usr/bin:/bin", "HOME": str(scratch), "TMPDIR": str(scratch), "PYTHONDONTWRITEBYTECODE": "1"})
        output, ok = (proc.stdout + proc.stderr), proc.returncode == 0
    except subprocess.TimeoutExpired:
        output, ok = f"Stopped: took longer than {TIME_LIMIT} seconds.", False
    files = [p.name for p in scratch.iterdir() if p.name != "main.py"]
    return {"ok": ok, "output": output[-OUTPUT_LIMIT:], "seconds": round(time.time() - start, 1),
            "files": files, "folder": str(scratch)}

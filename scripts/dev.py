"""Run the local API, background worker, and web development server together."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


def main() -> int:
    from gamecrafter.config.development import development_commands
    from gamecrafter.config.settings import get_settings

    settings = get_settings()
    pnpm = shutil.which("pnpm") or shutil.which("pnpm.cmd")
    if pnpm is None:
        print("pnpm was not found. Run scripts/setup.ps1 after installing pnpm.", file=sys.stderr)
        return 2

    commands = development_commands(settings, pnpm=pnpm, python=sys.executable)
    child_environment = os.environ.copy()
    existing_python_path = child_environment.get("PYTHONPATH")
    child_environment["PYTHONPATH"] = str(REPO_ROOT / "src")
    if existing_python_path:
        child_environment["PYTHONPATH"] += os.pathsep + existing_python_path

    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    processes = [
        subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            creationflags=creation_flags,
            env=child_environment,
        )
        for command in commands
    ]

    print("GameCrafter API, worker, and web services started.")
    print("Web: http://localhost:5173")
    print(f"API: http://{settings.api_host}:{settings.api_port}/health")
    print("Press Ctrl+C to stop all services.")

    try:
        return_code = 0
        while all(process.poll() is None for process in processes):
            for process in processes:
                try:
                    return_code = process.wait(timeout=0.3)
                except subprocess.TimeoutExpired:
                    continue
                if return_code:
                    return return_code
        return return_code
    except KeyboardInterrupt:
        return 0
    finally:
        for process in processes:
            if process.poll() is None:
                if os.name == "nt":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())

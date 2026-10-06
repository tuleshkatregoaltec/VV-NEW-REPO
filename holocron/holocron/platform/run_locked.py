"""Run a local maintenance command under a lock released automatically on exit."""

import fcntl
import os
import sys
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1])
    command = sys.argv[2:]
    if not command:
        raise SystemExit("Usage: run_locked LOCK COMMAND [ARG ...]")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"Maintenance is already running: {path.name}", flush=True)
            return 0
        os.set_inheritable(lock.fileno(), True)
        os.execvp(command[0], command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

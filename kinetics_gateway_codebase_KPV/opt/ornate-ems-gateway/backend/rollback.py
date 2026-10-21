#!/usr/bin/env python3
"""Run from the /root/kalpa-acrel-backup-* directory printed by install.py."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    if os.geteuid() != 0:
        raise SystemExit("Run as root")
    backup = Path(__file__).resolve().parent
    records = json.loads((backup / "restore.json").read_text())
    for name, record in records.items():
        path = Path(name)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record["installed_sha256"]:
            raise SystemExit(f"Refusing rollback over subsequent changes: {path}")
    subprocess.run(["systemctl", "stop", "ornate-ems-gateway"], check=True, timeout=30)
    for name, record in records.items():
        path = Path(name)
        if not record["existed"]:
            path.unlink()
            continue
        fd, temp = tempfile.mkstemp(prefix=".acrel-rollback-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(Path(record["saved"]).read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp, record["mode"])
            os.chown(temp, record["uid"], record["gid"])
            os.replace(temp, path)
        finally:
            Path(temp).unlink(missing_ok=True)
    subprocess.run(["systemctl", "start", "ornate-ems-gateway"], check=True, timeout=30)
    print("Original code and configuration restored; historian database retained.")


if __name__ == "__main__":
    main()

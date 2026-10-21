import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

PACKAGE = Path(__file__).resolve().parents[1]


def installer():
    spec = importlib.util.spec_from_file_location("acrel_install_test", PACKAGE / "install.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def baseline(tmp_path):
    # The baseline can be reconstructed exactly from patched files by reversing
    # each contextual edit; the two new modules do not belong to that baseline.
    from app.core.config import project_root
    backend = tmp_path / "backend"
    shutil.copytree(project_root() / "app", backend / "app", ignore=shutil.ignore_patterns("__pycache__"))
    patches = json.loads((PACKAGE / "integration-patches.json").read_text())
    for name, chunks in patches.items():
        text = (backend / name).read_text()
        for chunk in reversed(chunks):
            assert text.count(chunk["new"]) == 1
            text = text.replace(chunk["new"], chunk["old"], 1)
        (backend / name).write_text(text)
    for source in (PACKAGE / "payload").rglob("*.py"):
        (backend / source.relative_to(PACKAGE / "payload")).unlink()
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"mode": "mock", "test_keep_this": "unchanged"}))
    return backend, config


def test_context_patch_preserves_unrelated_connectivity_changes(tmp_path):
    backend, _ = baseline(tmp_path)
    path = backend / "app/api/routes.py"
    path.write_text(path.read_text() + "\n# Separate connectivity update retained\n")
    planned = installer().prepare(backend)
    assert planned["app/api/routes.py"].endswith(b"# Separate connectivity update retained\n")
    assert "Separate connectivity" in path.read_text()  # preparation never writes deployed source


def test_conflicting_context_aborts_before_changes(tmp_path):
    backend, _ = baseline(tmp_path)
    path = backend / "app/api/routes.py"
    original = path.read_text().replace('@router.get("/api/telemetry/snapshot")', '@router.get("/changed")')
    path.write_text(original)
    with pytest.raises(RuntimeError, match="cleanly patch"):
        installer().prepare(backend)
    assert path.read_text() == original
    assert not (backend / "app/assets/acrel_meter.py").exists()


def test_check_only_compiles_and_validates_without_writes(tmp_path):
    backend, config = baseline(tmp_path)
    original = (backend / "app/main.py").read_bytes()
    result = subprocess.run([
        sys.executable, str(PACKAGE / "install.py"), "--check-only", "--enable-meter",
        "--backend", str(backend), "--config", str(config),
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Preflight configuration and imports: PASS" in result.stdout
    assert (backend / "app/main.py").read_bytes() == original
    assert "meter" not in json.loads(config.read_text())


@pytest.mark.parametrize("healthy", [True, False])
def test_install_and_startup_failure_rollback(tmp_path, monkeypatch, healthy):
    backend, config = baseline(tmp_path)
    module = installer()
    real_path = Path
    module.Path = lambda value=".": tmp_path / "backups" if value == "/root" else real_path(value)
    (tmp_path / "backups").mkdir()
    monkeypatch.setattr(sys, "argv", [str(PACKAGE / "install.py"), "--backend", str(backend), "--config", str(config)])
    real_run = subprocess.run
    commands = []
    def run(args, **kwargs):
        if args[0] == "systemctl":
            commands.append(args)
            return SimpleNamespace(returncode=0)
        return real_run(args, **kwargs)
    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Opener:
        def open(self, *args, **kwargs):
            if not healthy: raise ConnectionError("Simulated API startup failure")
            return Response()
    monkeypatch.setattr(module.urllib.request, "build_opener", lambda *args: Opener())
    originals = {str(p.relative_to(backend)): p.read_bytes() for p in backend.rglob("*.py")}
    if healthy:
        module.main()
        assert not json.loads(config.read_text())["meter"]["enabled"]
        assert json.loads(config.read_text())["test_keep_this"] == "unchanged"
        assert (backend / "app/assets/acrel_meter.py").is_file()
    else:
        with pytest.raises(RuntimeError, match="did not recover"):
            module.main()
        after = {str(p.relative_to(backend)): p.read_bytes() for p in backend.rglob("*.py")}
        assert after == originals
        assert "meter" not in json.loads(config.read_text())
    assert commands and any("start" in command for command in commands)

from app.services.runtime_metrics import RuntimeMetrics


def test_runtime_metrics_are_bounded_and_account_requests():
    metrics = RuntimeMetrics(max_routes=2, slow_request_ms=10)
    metrics.request_started()
    metrics.request_finished("GET", "/one", 200, 5)
    metrics.request_started()
    metrics.request_finished("GET", "/two", 503, 12)
    metrics.request_started()
    metrics.request_finished("GET", "/three", 200, 1)

    snapshot = metrics.snapshot()
    assert snapshot["http"]["in_flight"] == 0
    assert snapshot["http"]["peak_in_flight"] == 1
    assert len(snapshot["http"]["routes"]) == 3
    assert snapshot["http"]["routes"]["GET /two"]["errors"] == 1
    assert snapshot["http"]["routes"]["GET /two"]["slow"] == 1
    assert snapshot["http"]["routes"]["__other__"]["count"] == 1
    assert snapshot["process"]["peak_rss_bytes"] > 0
    assert snapshot["process"]["peak_rss_bytes"] >= snapshot["process"]["rss_bytes"]
    assert "breakdown" in snapshot["process"]
    assert "available" in snapshot["cgroup"]


def test_runtime_metrics_track_background_and_event_loop():
    metrics = RuntimeMetrics()
    metrics.background_finished("bms-fast", 3.5, missed=1)
    metrics.event_loop_sample(4.2, 7)

    snapshot = metrics.snapshot()
    assert snapshot["background"]["bms-fast"]["missed_cycles"] == 1
    assert snapshot["event_loop"]["lag_ms"] == 4.2
    assert snapshot["event_loop"]["task_count"] == 7


def test_runtime_metrics_track_websocket_backpressure():
    metrics = RuntimeMetrics()
    metrics.websocket_connected()
    metrics.websocket_rejected()
    metrics.websocket_send_timeout()
    metrics.websocket_disconnected()

    websocket = metrics.snapshot()["websockets"]
    assert websocket["active"] == 0
    assert websocket["accepted"] == 1
    assert websocket["rejected_clients"] == 1
    assert websocket["send_timeouts"] == 1
    assert websocket["backpressure_disconnects"] == 1


def test_runtime_metrics_track_http_admission():
    metrics = RuntimeMetrics()
    metrics.http_admission_accepted(priority=False)
    metrics.http_admission_accepted(priority=True)
    metrics.http_admission_rejected(priority=False)
    metrics.http_admission_released(priority=False)

    admission = metrics.snapshot()["http"]["admission"]
    assert admission["active"] == 1
    assert admission["active_general"] == 0
    assert admission["active_priority"] == 1
    assert admission["accepted"] == 2
    assert admission["accepted_general"] == 1
    assert admission["accepted_priority"] == 1
    assert admission["rejected"] == 1
    assert admission["rejected_general"] == 1
    assert admission["rejected_priority"] == 0


def test_cgroup_memory_v2_breakdown(monkeypatch, tmp_path):
    proc = tmp_path / "proc" / "self"
    cgroup = tmp_path / "sys" / "fs" / "cgroup" / "system.slice" / "gateway.service"
    proc.mkdir(parents=True)
    cgroup.mkdir(parents=True)
    (proc / "cgroup").write_text("0::/system.slice/gateway.service\n", encoding="utf-8")
    (cgroup / "memory.current").write_text("1000\n", encoding="utf-8")
    (cgroup / "memory.peak").write_text("2000\n", encoding="utf-8")
    (cgroup / "memory.swap.current").write_text("0\n", encoding="utf-8")
    (cgroup / "memory.stat").write_text("anon 300\nfile 600\nslab 100\nignored 99\n", encoding="utf-8")
    (cgroup / "memory.events").write_text("low 0\noom 1\noom_kill 1\n", encoding="utf-8")
    (cgroup / "cgroup.procs").write_text("10\n11\n", encoding="utf-8")
    (cgroup / "cgroup.threads").write_text("10\n12\n13\n", encoding="utf-8")
    (cgroup / "pids.current").write_text("3\n", encoding="utf-8")

    real_path = __import__("pathlib").Path

    def redirected_path(value):
        path = str(value)
        if path == "/proc/self/cgroup":
            return proc / "cgroup"
        if path.startswith("/sys/fs/cgroup"):
            return real_path(str(tmp_path) + path)
        return real_path(value)

    monkeypatch.setattr("app.services.runtime_metrics.Path", redirected_path)
    snapshot = RuntimeMetrics._cgroup_memory()

    assert snapshot["available"] is True
    assert snapshot["current_bytes"] == 1000
    assert snapshot["peak_bytes"] == 2000
    assert snapshot["process_count"] == 2
    assert snapshot["thread_count"] == 3
    assert snapshot["breakdown"]["file_bytes"] == 600
    assert "ignored_bytes" not in snapshot["breakdown"]
    assert snapshot["events"]["oom_kill"] == 1

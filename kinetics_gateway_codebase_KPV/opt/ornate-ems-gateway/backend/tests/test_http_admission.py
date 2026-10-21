import asyncio

from app.services.http_admission import HttpAdmissionController, is_priority_http_path


def test_general_capacity_is_bounded_and_priority_reserve_remains_available():
    async def scenario():
        controller = HttpAdmissionController(
            max_concurrent=3,
            reserved_priority=1,
            wait_timeout_seconds=0.01,
        )
        general_one = await controller.acquire(priority=False)
        general_two = await controller.acquire(priority=False)
        assert general_one is not None
        assert general_two is not None
        assert await controller.acquire(priority=False) is None

        priority = await controller.acquire(priority=True)
        assert priority is not None
        assert await controller.acquire(priority=True) is None

        controller.release(priority)
        controller.release(general_two)
        controller.release(general_one)

    asyncio.run(scenario())


def test_priority_path_classification_keeps_control_and_health_reachable():
    assert is_priority_http_path("/api/health")
    assert is_priority_http_path("/api/auth/login")
    assert is_priority_http_path("/api/diagnostics/runtime")
    assert is_priority_http_path("/api/control/bms_bank/reset")
    assert is_priority_http_path("/api/control-sequence/pair_1/status")
    assert not is_priority_http_path("/api/telemetry/snapshot")
    assert not is_priority_http_path("/api/events")

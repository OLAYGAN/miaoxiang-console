import asyncio

from backend.events import EventBus
from backend.models import MultiStageItem, MultiStageSnapshot
from backend.multi_stage import MultiStageEngine


async def test_stop_converges_when_runner_handles_cancellation() -> None:
    engine = MultiStageEngine(EventBus())
    started = asyncio.Event()

    async def runner(item: MultiStageItem) -> dict:
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            # This mirrors the generation runner: it stops its inner task and
            # can return the inner snapshot instead of re-raising immediately.
            return {"status": "stopped"}

    engine.start(
        stage="repair",
        day="2026-10-19",
        items=[MultiStageItem(account_id="account", account_name="账号")],
        runner=runner,
    )
    await started.wait()

    snapshot = await engine.stop()

    assert snapshot.status == "stopped"
    assert snapshot.items[0].status == "stopped"
    assert snapshot.items[0].result == {"status": "stopped"}
    assert not engine.is_running


async def test_stop_finalizes_stale_stopping_snapshot() -> None:
    engine = MultiStageEngine(EventBus())
    engine.current = MultiStageSnapshot(
        stage="repair",
        day="2026-10-19",
        status="stopping",
        items=[
            MultiStageItem(account_id="account", account_name="账号"),
            MultiStageItem(account_id="pending", account_name="等待账号"),
        ],
    )

    snapshot = await engine.stop()

    assert snapshot.status == "stopped"
    assert [item.status for item in snapshot.items] == ["stopped", "stopped"]

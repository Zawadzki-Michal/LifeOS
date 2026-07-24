"""Redis pub/sub is what makes scheduler messages show up live in the web
app (app.scheduler._broadcast_to_web -> app.routers.stream's SSE endpoint).
This pins down the wire format both sides agree on."""

import asyncio

from app import redis_client


async def test_publish_then_subscribe_delivers_the_event():
    async def _collect_first_event():
        async for event in redis_client.subscribe_chat_events(poll_timeout=0.2):
            if event is not None:
                return event

    task = asyncio.ensure_future(_collect_first_event())
    await asyncio.sleep(0.05)  # let the subscribe() land before we publish
    await redis_client.publish_chat_event(5, {"role": "assistant", "content": "hi"})

    result = await asyncio.wait_for(task, timeout=2)
    assert result == {"session_id": 5, "message": {"role": "assistant", "content": "hi"}}


async def test_subscribe_yields_none_on_timeout_with_no_messages():
    events = redis_client.subscribe_chat_events(poll_timeout=0.1)
    first = await asyncio.wait_for(events.__anext__(), timeout=2)
    assert first is None


async def test_publish_status_event_delivers_over_the_same_channel():
    async def _collect_first_event():
        async for event in redis_client.subscribe_chat_events(poll_timeout=0.2):
            if event is not None:
                return event

    task = asyncio.ensure_future(_collect_first_event())
    await asyncio.sleep(0.05)
    await redis_client.publish_status_event(7, "thinking_cloud")

    result = await asyncio.wait_for(task, timeout=2)
    assert result == {"session_id": 7, "status": "thinking_cloud"}

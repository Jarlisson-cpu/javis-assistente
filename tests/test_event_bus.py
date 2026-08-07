"""Testes do barramento de eventos."""

import pytest

from core.event_bus import Event, EventBus


@pytest.mark.asyncio
async def test_publish_calls_sync_handler() -> None:
    bus = EventBus()
    received = []

    bus.subscribe("ping", lambda e: received.append(e.payload))

    await bus.publish(Event(name="ping", payload={"value": 42}))

    assert received == [{"value": 42}]


@pytest.mark.asyncio
async def test_publish_calls_async_handler() -> None:
    bus = EventBus()
    received = []

    async def handler(event: Event) -> None:
        received.append(event.payload)

    bus.subscribe("ping", handler)
    await bus.publish(Event(name="ping", payload={"value": 1}))

    assert received == [{"value": 1}]


def test_publish_sync_calls_async_handler() -> None:
    bus = EventBus()
    received = []

    async def handler(event: Event) -> None:
        received.append(event.payload)

    bus.subscribe("ping", handler)
    bus.publish_sync(Event(name="ping", payload={"value": 1}))

    assert received == [{"value": 1}]


@pytest.mark.asyncio
async def test_publish_without_handlers_does_not_raise() -> None:
    bus = EventBus()
    await bus.publish(Event(name="nobody_listening"))  # não deve levantar exceção


@pytest.mark.asyncio
async def test_unsubscribe_stops_receiving_events() -> None:
    bus = EventBus()
    received = []

    def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("ping", handler)
    bus.unsubscribe("ping", handler)
    await bus.publish(Event(name="ping"))

    assert received == []

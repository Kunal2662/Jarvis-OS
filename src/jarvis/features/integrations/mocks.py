"""Mock implementations of the Milestone 5 future-integration provider
ports (``core/interfaces/providers.py``).

Every one of these returns realistic, static-but-varied mock data with
a small simulated network delay -- "use mock data only, design so real
APIs can later replace the mock providers without UI changes" from the
brief. Swapping a mock for a real adapter later is a one-line DI wire
change (see ``core/di/container.py``); no widget imports these classes
directly by name, only by the interface type.
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta
from typing import Any

from jarvis.core.interfaces.providers import ActivityItem, ConnectionStatus

_MOCK_DELAY_SECONDS = 0.05


async def _simulate_latency() -> None:
    await asyncio.sleep(_MOCK_DELAY_SECONDS)


def _ago(minutes: int) -> datetime:
    return datetime.now() - timedelta(minutes=minutes)


class MockGmailProvider:
    def __init__(self) -> None:
        self._messages = [
            {
                "from": "Priya Sharma",
                "subject": "Q3 roadmap review",
                "snippet": "Attaching the deck for tomorrow…",
                "unread": True,
                "minutes_ago": 4,
            },
            {
                "from": "GitHub",
                "subject": "[jarvis-os] CI passed on main",
                "snippet": "All checks passed for commit 8f3a1c…",
                "unread": True,
                "minutes_ago": 22,
            },
            {
                "from": "Aditya (You)",
                "subject": "Re: Vendor contract",
                "snippet": "Sounds good, sending the signed copy…",
                "unread": False,
                "minutes_ago": 55,
            },
            {
                "from": "LinkedIn",
                "subject": "5 people viewed your profile",
                "snippet": "See who's been checking you out…",
                "unread": False,
                "minutes_ago": 130,
            },
            {
                "from": "Notion",
                "subject": "Weekly digest",
                "snippet": "3 pages updated in Engineering workspace…",
                "unread": False,
                "minutes_ago": 340,
            },
        ]

    async def get_connection_status(self) -> ConnectionStatus:
        await _simulate_latency()
        return ConnectionStatus(connected=True, detail="mock@gmail.com", last_sync=_ago(2))

    async def get_unread_count(self) -> int:
        await _simulate_latency()
        return sum(1 for m in self._messages if m["unread"])

    async def list_recent_messages(self, limit: int = 10) -> list[dict[str, Any]]:
        await _simulate_latency()
        return self._messages[:limit]

    async def get_recent_activity(self, limit: int = 5) -> list[ActivityItem]:
        await _simulate_latency()
        return [
            ActivityItem("✉", f"New mail from {m['from']}: {m['subject']}", _ago(m["minutes_ago"]))
            for m in self._messages[:limit]
        ]

    async def send_message(self, to: str, subject: str, body: str) -> bool:
        await _simulate_latency()
        return True  # mock -- no real send


class MockSpotifyProvider:
    def __init__(self) -> None:
        self._tracks = [
            {
                "title": "Weightless",
                "artist": "Marconi Union",
                "album": "Weightless",
                "duration": "8:10",
            },
            {
                "title": "Clair de Lune",
                "artist": "Debussy",
                "album": "Suite Bergamasque",
                "duration": "5:02",
            },
            {
                "title": "Night Owl",
                "artist": "Galimatias",
                "album": "Ancient Beat",
                "duration": "3:41",
            },
            {
                "title": "Circles",
                "artist": "Post Malone",
                "album": "Hollywood's Bleeding",
                "duration": "3:35",
            },
        ]
        self._playing = True

    async def get_connection_status(self) -> ConnectionStatus:
        await _simulate_latency()
        return ConnectionStatus(connected=True, detail="Premium · mock@spotify", last_sync=_ago(1))

    async def get_now_playing(self) -> dict[str, Any] | None:
        await _simulate_latency()
        track = self._tracks[0]
        return {**track, "is_playing": self._playing, "progress_pct": 42}

    async def list_recent_tracks(self, limit: int = 10) -> list[dict[str, Any]]:
        await _simulate_latency()
        return self._tracks[:limit]

    async def get_recent_activity(self, limit: int = 5) -> list[ActivityItem]:
        await _simulate_latency()
        return [
            ActivityItem("🎵", f"Played \"{t['title']}\" by {t['artist']}", _ago(i * 12 + 3))
            for i, t in enumerate(self._tracks[:limit])
        ]

    async def play(self) -> bool:
        await _simulate_latency()
        self._playing = True
        return True

    async def pause(self) -> bool:
        await _simulate_latency()
        self._playing = False
        return True

    async def next_track(self) -> bool:
        await _simulate_latency()
        self._tracks.append(self._tracks.pop(0))
        return True


class MockWeatherProvider:
    async def get_connection_status(self) -> ConnectionStatus:
        await _simulate_latency()
        return ConnectionStatus(connected=True, detail="Open-Meteo (mock)", last_sync=_ago(6))

    async def get_current(self, location: str) -> dict[str, Any]:
        await _simulate_latency()
        return {
            "location": location,
            "temp_c": 27,
            "condition": "Partly Cloudy",
            "humidity": 61,
            "wind_kph": 14,
        }

    async def get_forecast(self, location: str, days: int = 5) -> list[dict[str, Any]]:
        await _simulate_latency()
        base = 25
        conditions = ["Sunny", "Partly Cloudy", "Rain", "Cloudy", "Thunderstorms"]
        return [
            {
                "day": (datetime.now() + timedelta(days=i)).strftime("%a"),
                "high_c": base + random.randint(-2, 4),
                "low_c": base - random.randint(4, 8),
                "condition": conditions[i % len(conditions)],
            }
            for i in range(days)
        ]


class MockFinanceProvider:
    def __init__(self) -> None:
        self._holdings = [
            {"symbol": "NIFTY50", "qty": 12, "value": 412300.0, "change_pct": 0.8},
            {"symbol": "AAPL", "qty": 6, "value": 168200.0, "change_pct": -0.4},
            {"symbol": "BTC", "qty": 0.15, "value": 91500.0, "change_pct": 2.1},
            {"symbol": "GOLD-ETF", "qty": 40, "value": 58900.0, "change_pct": 0.2},
        ]

    async def get_connection_status(self) -> ConnectionStatus:
        await _simulate_latency()
        return ConnectionStatus(connected=True, detail="mock brokerage feed", last_sync=_ago(15))

    async def get_portfolio_summary(self) -> dict[str, Any]:
        await _simulate_latency()
        total = sum(h["value"] for h in self._holdings)
        return {"total_value": total, "day_change_pct": 0.9, "day_change_value": total * 0.009}

    async def list_holdings(self) -> list[dict[str, Any]]:
        await _simulate_latency()
        return self._holdings

    async def list_transactions(self, limit: int = 20) -> list[dict[str, Any]]:
        await _simulate_latency()
        txns = [
            {"type": "BUY", "symbol": "AAPL", "qty": 2, "price": 27950.0, "minutes_ago": 90},
            {"type": "SELL", "symbol": "GOLD-ETF", "qty": 5, "price": 5920.0, "minutes_ago": 260},
            {"type": "BUY", "symbol": "BTC", "qty": 0.02, "price": 12150.0, "minutes_ago": 500},
        ]
        return txns[:limit]

    async def get_recent_activity(self, limit: int = 5) -> list[ActivityItem]:
        await _simulate_latency()
        txns = await self.list_transactions(limit)
        return [
            ActivityItem(
                "📈",
                f"{t['type'].title()} {t['qty']} {t['symbol']} @ ₹{t['price']:.0f}",
                _ago(t["minutes_ago"]),
            )
            for t in txns
        ]


class MockSmartHomeProvider:
    def __init__(self) -> None:
        self._devices = [
            {
                "id": "living-room-light",
                "name": "Living Room Light",
                "type": "light",
                "state": "on",
                "online": True,
            },
            {
                "id": "thermostat",
                "name": "Thermostat",
                "type": "climate",
                "state": "24°C",
                "online": True,
            },
            {
                "id": "front-door-lock",
                "name": "Front Door Lock",
                "type": "lock",
                "state": "locked",
                "online": True,
            },
            {
                "id": "garage-camera",
                "name": "Garage Camera",
                "type": "camera",
                "state": "recording",
                "online": False,
            },
        ]

    async def get_connection_status(self) -> ConnectionStatus:
        await _simulate_latency()
        online = sum(1 for d in self._devices if d["online"])
        return ConnectionStatus(
            connected=True,
            detail=f"{online}/{len(self._devices)} devices online",
            last_sync=_ago(1),
        )

    async def list_devices(self) -> list[dict[str, Any]]:
        await _simulate_latency()
        return self._devices

    async def set_device_state(self, device_id: str, state: dict[str, Any]) -> bool:
        await _simulate_latency()
        for device in self._devices:
            if device["id"] == device_id:
                device.update(state)
                return True
        return False

    async def get_recent_activity(self, limit: int = 5) -> list[ActivityItem]:
        await _simulate_latency()
        return [
            ActivityItem("🏡", f"{d['name']} is {d['state']}", _ago(i * 8 + 5))
            for i, d in enumerate(self._devices[:limit])
        ]

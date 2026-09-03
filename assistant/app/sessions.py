"""Диалоги в памяти процесса.

Сознательное упрощение, как у соседнего ассистента ХАК ИТС: истории живут
в словаре одного процесса, а не в Redis. Отсюда следствие, которое нельзя
терять при деплое — сервис запускается РОВНО ОДНИМ воркером uvicorn. Два
воркера раскидают запросы одного человека по разным процессам, и он будет
разговаривать то с одним ассистентом, то с другим.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from app.agent import Agent
from app.config import settings


@dataclass
class Session:
    id: str
    ip: str
    agent: Agent
    created_at: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)
    messages: int = 0
    last_user_text: str = ""

    def touch(self) -> None:
        self.last_seen = time.monotonic()


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def _evict_expired(self) -> None:
        now = time.monotonic()
        stale = [
            key
            for key, session in self._sessions.items()
            if now - session.last_seen > settings.session_ttl_seconds
        ]
        for key in stale:
            del self._sessions[key]

    def _count_for_ip(self, ip: str) -> int:
        return sum(1 for session in self._sessions.values() if session.ip == ip)

    def create(self, ip: str) -> Session:
        self._evict_expired()
        if self._count_for_ip(ip) >= settings.max_sessions_per_ip:
            raise TooManySessions()

        session = Session(id=uuid.uuid4().hex, ip=ip, agent=Agent())
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        self._evict_expired()
        session = self._sessions.get(session_id)
        if session is not None:
            session.touch()
        return session

    @property
    def active(self) -> int:
        return len(self._sessions)


class TooManySessions(Exception):
    """С одного адреса открыто слишком много диалогов."""

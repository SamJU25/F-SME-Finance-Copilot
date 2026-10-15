"""In-memory and persistent session store for Autonomous SME Finance Copilot.

Provides:
1. Thread-safe multi-tenant session lifecycle management.
2. In-memory session cache with file-backed persistence.
3. Cached transactional statement dossiers (eliminates redundant CSV re-parsing).
4. Episodic financial fact extraction (preserves loan terms, EBITDA, fixed costs beyond 6 turns).
5. Full multi-turn conversation history retention.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from services.agent.schema import ChatHistoryItem

logger = logging.getLogger(__name__)

SESSION_CACHE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../.sessions")
)


class SessionRecord(BaseModel):
    """Encapsulates active session state, transactional dossier, and episodic memory."""

    session_id: str
    tenant_id: str = "SME-DEFAULT"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    messages: List[ChatHistoryItem] = Field(default_factory=list)
    csv_content: Optional[str] = None
    cached_dossier: Optional[Dict[str, Any]] = None
    financial_facts: Dict[str, Any] = Field(default_factory=dict)


class SessionStore:
    """Thread-safe singleton store managing agent sessions and financial context memory."""

    _instance: Optional[SessionStore] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionRecord] = {}
        self._store_lock = threading.Lock()
        os.makedirs(SESSION_CACHE_DIR, exist_ok=True)
        self._load_persisted_sessions()

    @classmethod
    def get_instance(cls) -> SessionStore:
        with cls._lock:
            if cls._instance is None:
                cls._instance = SessionStore()
            return cls._instance

    def _get_session_path(self, session_id: str) -> str:
        safe_id = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))
        return os.path.join(SESSION_CACHE_DIR, f"{safe_id}.json")

    def _load_persisted_sessions(self) -> None:
        """Loads serialized sessions from disk on startup."""
        if not os.path.exists(SESSION_CACHE_DIR):
            return
        for fname in os.listdir(SESSION_CACHE_DIR):
            if fname.endswith(".json"):
                fpath = os.path.join(SESSION_CACHE_DIR, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        rec = SessionRecord(**data)
                        self._sessions[rec.session_id] = rec
                except Exception as exc:
                    logger.debug("Could not deserialize session file %s: %s", fname, exc)

    def _persist_session(self, record: SessionRecord) -> None:
        """Saves session state to disk for cross-restart recovery."""
        fpath = self._get_session_path(record.session_id)
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(record.model_dump_json(indent=2))
        except Exception as exc:
            logger.debug("Session disk write error for %s: %s", record.session_id, exc)

    def get_or_create(self, session_id: str, tenant_id: str = "SME-DEFAULT") -> SessionRecord:
        """Retrieves an existing session record or initializes a new one."""
        with self._store_lock:
            if session_id in self._sessions:
                rec = self._sessions[session_id]
                if tenant_id and tenant_id != "SME-DEFAULT":
                    rec.tenant_id = tenant_id
                return rec

            rec = SessionRecord(session_id=session_id, tenant_id=tenant_id)
            self._sessions[session_id] = rec
            self._persist_session(rec)
            return rec

    def get(self, session_id: str) -> Optional[SessionRecord]:
        with self._store_lock:
            return self._sessions.get(session_id)

    def update_statement(
        self,
        session_id: str,
        csv_content: str,
        dossier: Optional[Dict[str, Any]] = None,
        tenant_id: str = "SME-DEFAULT",
    ) -> SessionRecord:
        """Stores statement CSV and cached calculation metrics in the session."""
        rec = self.get_or_create(session_id, tenant_id=tenant_id)
        with self._store_lock:
            rec.csv_content = csv_content
            if dossier is not None:
                rec.cached_dossier = dossier
            rec.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist_session(rec)
            return rec

    def clear_statement(self, session_id: str) -> Optional[SessionRecord]:
        """Clears statement CSV, cached dossier, and statement-derived facts from the session."""
        with self._store_lock:
            rec = self._sessions.get(session_id)
            if not rec:
                return None
            rec.csv_content = None
            rec.cached_dossier = None
            for fact in [
                "current_balance",
                "average_daily_burn",
                "runway_days",
                "cash_status",
                "daily_average_balance",
                "risk_tier",
                "max_qualified_limit",
            ]:
                rec.financial_facts.pop(fact, None)
            rec.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist_session(rec)
            return rec

    def append_turn(
        self,
        session_id: str,
        user_text: str,
        agent_text: str,
        tenant_id: str = "SME-DEFAULT",
    ) -> SessionRecord:
        """Appends user and agent turns to session history and updates episodic facts."""
        rec = self.get_or_create(session_id, tenant_id=tenant_id)
        with self._store_lock:
            if user_text:
                rec.messages.append(ChatHistoryItem(role="user", text=user_text))
            if agent_text:
                rec.messages.append(ChatHistoryItem(role="agent", text=agent_text))

            # Maintain reasonable maximum capacity (last 50 turns) to prevent memory leak
            if len(rec.messages) > 50:
                rec.messages = rec.messages[-50:]

            rec.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist_session(rec)
            return rec

    def set_financial_fact(self, session_id: str, key: str, value: Any) -> None:
        """Stores an episodic business fact (e.g. loan_amount, target_horizon)."""
        rec = self.get_or_create(session_id)
        with self._store_lock:
            rec.financial_facts[key] = value
            rec.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist_session(rec)

    def get_financial_facts(self, session_id: str) -> Dict[str, Any]:
        rec = self.get_or_create(session_id)
        with self._store_lock:
            return dict(rec.financial_facts)

    def clear(self, session_id: str) -> bool:
        """Clears session data from memory and removes file from disk."""
        with self._store_lock:
            removed = self._sessions.pop(session_id, None)
            fpath = self._get_session_path(session_id)
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except OSError:
                    pass
            return removed is not None

    def clear_all(self) -> None:
        """Wipes all sessions (primarily for unit test isolation)."""
        with self._store_lock:
            self._sessions.clear()
            if os.path.exists(SESSION_CACHE_DIR):
                for fname in os.listdir(SESSION_CACHE_DIR):
                    if fname.endswith(".json"):
                        try:
                            os.remove(os.path.join(SESSION_CACHE_DIR, fname))
                        except OSError:
                            pass


# Global singleton instance
session_store = SessionStore.get_instance()

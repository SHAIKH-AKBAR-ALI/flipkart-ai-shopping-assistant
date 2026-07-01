import json
import os
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import Column, DateTime, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from agents.state import AgentState, new_state

# Separate DB file from V1's backend/data/sessions.db — V2 session state must
# never touch or mix with V1's data.
_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sessions_v2.db")
_ENGINE = create_engine(f"sqlite:///{_DB_PATH}", connect_args={"check_same_thread": False})

# Internal-only AgentState keys that are turn-scoped bookkeeping, not durable state.
_TRANSIENT_KEYS = ("_agent_responded", "_used_keyword_fallback", "_last_response")


class _Base(DeclarativeBase):
    pass


class _SessionRecordV2(_Base):
    __tablename__ = "sessions_v2"

    session_id = Column(String, primary_key=True)
    state_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


_Base.metadata.create_all(_ENGINE)


def _serialize_messages(messages) -> list:
    out = []
    for m in messages:
        role = "user" if isinstance(m, HumanMessage) else "assistant"
        out.append({"role": role, "content": m.content})
    return out


def _deserialize_messages(raw: list) -> list:
    out = []
    for m in raw:
        if m["role"] == "user":
            out.append(HumanMessage(content=m["content"]))
        else:
            out.append(AIMessage(content=m["content"]))
    return out


def _state_to_json(state: AgentState) -> str:
    serializable = {k: v for k, v in dict(state).items() if k not in _TRANSIENT_KEYS}
    serializable["messages"] = _serialize_messages(state.get("messages", []))
    return json.dumps(serializable)


def _json_to_state(raw: str) -> AgentState:
    data = json.loads(raw)
    state = new_state()
    state.update(data)
    state["messages"] = _deserialize_messages(data.get("messages", []))
    return state


class SessionStoreV2:
    def get_state(self, session_id: str) -> AgentState:
        with Session(_ENGINE) as db:
            record = db.get(_SessionRecordV2, session_id)
            if record is None:
                return new_state()
            return _json_to_state(record.state_json)

    def save_state(self, session_id: str, state: AgentState) -> None:
        with Session(_ENGINE) as db:
            record = db.get(_SessionRecordV2, session_id)
            if record is None:
                record = _SessionRecordV2(session_id=session_id)
                db.add(record)
            record.state_json = _state_to_json(state)
            record.updated_at = datetime.now(timezone.utc)
            db.commit()

    def clear_session(self, session_id: str) -> None:
        with Session(_ENGINE) as db:
            record = db.get(_SessionRecordV2, session_id)
            if record:
                db.delete(record)
                db.commit()

    def exists(self, session_id: str) -> bool:
        with Session(_ENGINE) as db:
            return db.get(_SessionRecordV2, session_id) is not None

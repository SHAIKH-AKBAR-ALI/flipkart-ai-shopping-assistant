import json
import os
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sessions.db")
_ENGINE = create_engine(f"sqlite:///{_DB_PATH}", connect_args={"check_same_thread": False})


class _Base(DeclarativeBase):
    pass


class _SessionRecord(_Base):
    __tablename__ = "sessions"

    session_id = Column(String, primary_key=True)
    messages = Column(Text, default="[]")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


_Base.metadata.create_all(_ENGINE)


class SessionStore:
    def _get_record(self, db: Session, session_id: str) -> _SessionRecord:
        record = db.get(_SessionRecord, session_id)
        if record is None:
            record = _SessionRecord(session_id=session_id, messages="[]")
            db.add(record)
            db.flush()
        return record

    def get_history(self, session_id: str) -> list[dict]:
        with Session(_ENGINE) as db:
            record = db.get(_SessionRecord, session_id)
            if record is None:
                return []
            return json.loads(record.messages)

    def save_message(self, session_id: str, role: str, content: str) -> None:
        with Session(_ENGINE) as db:
            record = self._get_record(db, session_id)
            messages = json.loads(record.messages)
            messages.append({"role": role, "content": content})
            record.messages = json.dumps(messages)
            record.updated_at = datetime.now(timezone.utc)
            db.commit()

    def get_last_n_turns(self, session_id: str, n: int = 6) -> list[dict]:
        messages = self.get_history(session_id)
        # each turn = 1 user + 1 assistant message; n turns = 2n messages
        return messages[-(n * 2):]

    def summarize_old_messages(self, session_id: str) -> None:
        """Keep last 6 messages, replace older ones with a placeholder summary."""
        with Session(_ENGINE) as db:
            record = self._get_record(db, session_id)
            messages = json.loads(record.messages)

            if len(messages) <= 6:
                return

            old = messages[:-6]
            recent = messages[-6:]

            summary_text = f"[Earlier conversation: {len(old)} messages omitted]"
            summary_msg = {"role": "system", "content": summary_text}

            record.messages = json.dumps([summary_msg] + recent)
            record.updated_at = datetime.now(timezone.utc)
            db.commit()

    def clear_session(self, session_id: str) -> None:
        with Session(_ENGINE) as db:
            record = db.get(_SessionRecord, session_id)
            if record:
                db.delete(record)
                db.commit()

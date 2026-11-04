"""Saúde das fontes: registra cada tentativa, avisa no Telegram quando uma para de funcionar."""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import SourceStatus
from app.notify.telegram import send_telegram
from app.stores import aliexpress, amazon

log = logging.getLogger("precim.health")
FAILURES_BEFORE_WARNING = 3
LABELS = {"buscape": "Buscapé/Zoom", "kabum": "Kabum", "amazon": "Amazon", "aliexpress": "AliExpress"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def record(session: Session, source: str, ok: bool, detail: str | None = None) -> None:
    """Registra o resultado de uma tentativa. Avisa no Telegram na 3ª falha seguida e na volta."""
    st = session.get(SourceStatus, source) or SourceStatus(
        source=source, consecutive_failures=0, warned=False)
    session.add(st)
    st.last_attempt_at = _now()
    message = None
    if ok:
        if st.warned:
            message = f"✅ {LABELS.get(source, source)} voltou a responder."
        st.last_ok_at, st.consecutive_failures, st.last_error, st.warned = _now(), 0, None, False
    else:
        st.consecutive_failures += 1
        st.last_error = (detail or "sem detalhe")[:300]
        if st.consecutive_failures >= FAILURES_BEFORE_WARNING and not st.warned:
            st.warned = True
            message = (f"⚠️ {LABELS.get(source, source)} falhou {st.consecutive_failures} "
                       f"varreduras seguidas ({st.last_error}). O site pode ter mudado ou bloqueado.")
    session.commit()
    if message:
        try:
            await send_telegram(message)
        except Exception:
            log.exception("falha ao enviar aviso de saúde")


def _blocked(source: str) -> bool:
    return (source == "amazon" and amazon.blocked_now()) or (
        source == "aliexpress" and aliexpress.blocked_now())


def snapshot(session: Session) -> list[dict]:
    rows = {s.source: s for s in session.query(SourceStatus).all()}
    out = []
    for source, label in LABELS.items():
        st = rows.get(source)
        if _blocked(source):
            state = "bloqueada"
        elif st is None or st.last_attempt_at is None:
            state = "aguardando"
        elif st.consecutive_failures > 0:
            state = "falhando"
        else:
            state = "ok"
        out.append({
            "source": source, "label": label, "state": state,
            "last_ok_at": _iso(st.last_ok_at) if st and st.last_ok_at else None,
            "failures": st.consecutive_failures if st else 0,
            "detail": st.last_error if st else None,
        })
    return out


def _iso(dt: datetime) -> str:
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()

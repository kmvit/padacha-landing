"""HTTP-сервис ассистента.

Отдельный процесс рядом с лендингом, а не встроенный в него: лендинг —
статический index.html, серверной части у него нет вовсе. nginx хоста
проксирует сюда путь /api/assistant/ (см. deploy/).

Запускать одним воркером: истории диалогов лежат в памяти процесса
(см. app/sessions.py).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.agent import GREETING, build_sdk
from app.config import settings
from app.kb import kb
from app.limits import DailyBudget, IpLimiter, canned_reply
from app.sessions import SessionStore, TooManySessions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("assistant")

app = FastAPI(title="Ассистент «Падачи»", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)

store = SessionStore()
budget = DailyBudget(settings.daily_model_calls)
limiter = IpLimiter(
    per_day=settings.messages_per_ip_per_day,
    per_minute=settings.messages_per_ip_per_minute,
    min_interval=settings.min_seconds_between_messages,
)


@app.on_event("startup")
async def startup() -> None:
    settings.require_credentials()
    build_sdk()
    # Модель — в лог первой строкой: незамеченный откат на дорогую модель
    # обнаруживается по счёту, а не по поведению, отвечает-то она хорошо.
    logger.info("Модель: %s", settings.llm_model)
    logger.info(
        "Потолки: %d вызовов модели в сутки, %d реплик на адрес",
        settings.daily_model_calls,
        settings.messages_per_ip_per_day,
    )
    logger.info(
        "База знаний от %s: тарифов %d, вопросов %d, тем о продукте %d",
        kb.generated_at or "неизвестно",
        len(kb.tariffs),
        len(kb.faq),
        len(kb.product_topics),
    )
    if not kb.tariffs:
        logger.error("База знаний пуста — запустите `python -m scripts.export_kb`")


class StartRequest(BaseModel):
    pass


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=64)
    message: str = Field(..., min_length=1)


def client_ip(request: Request) -> str:
    """Адрес посетителя. Сервис всегда стоит за nginx хоста.

    X-Real-IP ставит собственный nginx из уже разобранного адреса — подделать
    его снаружи нельзя. X-Forwarded-For — запасной вариант; берём из него
    первый адрес.
    """
    real = request.headers.get("x-real-ip", "").strip()
    if real:
        return real
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _limit_reply(reason: str) -> str:
    if reason == "часто":
        return "Секунду — отвечаю на предыдущий вопрос. Напишите через пару секунд."
    if reason == "минута":
        return "Слишком много сообщений подряд. Давайте помедленнее."
    contact = kb.contact or "команде"
    return f"На сегодня мы наговорились — дальше полезнее написать напрямую: {contact}."


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "model": settings.llm_model,
            "kb_generated_at": kb.generated_at,
            "tariffs": len(kb.tariffs),
            "faq": len(kb.faq),
            "active_sessions": store.active,
            "расход": budget.stats(),
        }
    )


@app.post("/api/reload")
async def reload_kb(x_assistant_token: str = Header(default="")) -> JSONResponse:
    """Перечитать снапшот базы знаний без перезапуска сервиса.

    Дёргается руками после `python -m scripts.export_kb` — лендинг статический,
    сигнала от него, в отличие от сайта ХАК ИТС, не приходит.
    """
    if not settings.reload_token or x_assistant_token != settings.reload_token:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    kb.reload()
    logger.info(
        "База знаний перечитана: тарифов %d, вопросов %d, тем %d",
        len(kb.tariffs), len(kb.faq), len(kb.product_topics),
    )
    return JSONResponse(
        {"ok": True, "kb_generated_at": kb.generated_at, "tariffs": len(kb.tariffs)}
    )


@app.post("/api/start")
async def start(request: Request) -> JSONResponse:
    """Открывает диалог. Приветствие статичное — вызов модели не нужен."""
    try:
        session = store.create(ip=client_ip(request))
    except TooManySessions:
        return JSONResponse(
            {"error": "too_many_sessions", "message": "Слишком много открытых диалогов с этого адреса."},
            status_code=429,
        )
    return JSONResponse({"session_id": session.id, "greeting": GREETING})


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request) -> JSONResponse:
    session = store.get(payload.session_id)
    if session is None:
        # Диалог протух или сервис перезапустили. Виджет по этому коду
        # молча откроет новый — посетитель ничего не заметит.
        return JSONResponse(
            {"error": "session_expired", "message": "Диалог истёк, начните заново."},
            status_code=410,
        )

    ip = client_ip(request)
    text = payload.message.strip()[: settings.max_message_length]

    # 1. Темп — бережёт сервер, проверяется для любой реплики первым.
    reason = limiter.check_rate(ip)
    if reason:
        return JSONResponse({"reply": _limit_reply(reason)})
    limiter.record_rate(ip)

    # 2. Пустое, повтор, набор символов — заготовка, модель не трогаем.
    canned = canned_reply(text, session.last_user_text)
    if canned:
        session.last_user_text = text
        return JSONResponse({"reply": canned})

    if session.messages >= settings.max_messages_per_session:
        contact = kb.contact or "команде"
        return JSONResponse(
            {"reply": f"Мы с вами долго общаемся — дальше полезнее написать напрямую: {contact}."}
        )

    # 3. Предохранитель: суточный потолок на весь сервис исчерпан.
    if budget.exhausted:
        contact = kb.contact or "команде"
        return JSONResponse(
            {"reply": f"На сегодня лимит вопросов исчерпан. Напишите напрямую: {contact}."}
        )

    # 4. Платная реплика — вот теперь дневная квота на адрес.
    reason = limiter.check_quota(ip)
    if reason:
        return JSONResponse({"reply": _limit_reply(reason)})

    limiter.record_quota(ip)
    session.messages += 1
    session.last_user_text = text

    contact = kb.contact or "почту команды"
    try:
        answer = await session.agent.ask(text)
    except Exception:  # noqa: BLE001 — посетителю нужен ответ, а не 500
        logger.exception("Сбой при обработке реплики")
        return JSONResponse({"reply": f"Технический сбой. Напишите напрямую: {contact}."})

    budget.record()

    if not answer:
        answer = f"Не понял вопрос. Переформулируйте, либо напишите напрямую: {contact}."

    logger.info(
        "сессия=%s адрес=%s реплик=%d осталось_адресу=%d",
        session.id[:8], ip, session.messages, limiter.left_today(ip),
    )
    return JSONResponse({"reply": answer})


def main() -> None:
    import uvicorn

    # workers=1 не случайность: см. app/sessions.py.
    uvicorn.run("app.server:app", host=settings.host, port=settings.port, workers=1, log_level="info")


if __name__ == "__main__":
    main()

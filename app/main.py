import json
import os
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import fitz
from fastapi import FastAPI, Request, Form, Query, UploadFile, File, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func

from app.database import init_db, get_session, Job, ScrapeLog, ChatMessage, Setting
from app.config import SEARCH_KEYWORDS as FALLBACK_KEYWORDS, VC_BOARDS, RESUME_TEXT as FALLBACK_RESUME
from app.scheduler import start_scheduler, start_agent_scheduler, run_full_scrape
from app.ai.engine import AIEngine
from app.utils.env_writer import read_env, write_env


def _get_setting(key: str, default: str = "") -> str:
    session = get_session()
    row = session.query(Setting).filter(Setting.key == key).first()
    val = row.value if row and row.value else default
    session.close()
    return val


def _set_setting(key: str, value: str) -> None:
    session = get_session()
    row = session.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    else:
        session.add(Setting(key=key, value=value))
    session.commit()
    session.close()


def _del_setting(key: str) -> None:
    session = get_session()
    session.query(Setting).filter(Setting.key == key).delete()
    session.commit()
    session.close()


def _load_keywords() -> list[str]:
    raw = _get_setting("search_keywords")
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
    return list(FALLBACK_KEYWORDS)


def _save_keywords(kws: list[str]) -> None:
    _set_setting("search_keywords", json.dumps(kws))
    write_env({"SEARCH_KEYWORDS": ",".join(kws)})
    import app.config as cfg
    cfg.SEARCH_KEYWORDS = kws


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        start_scheduler()
    except Exception as e:
        print(f"Scheduler start skipped: {e}")
    try:
        start_agent_scheduler()
    except Exception as e:
        print(f"Agent scheduler start skipped: {e}")
    yield


app = FastAPI(title="Jobs Agent", lifespan=lifespan)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

ai_engine = AIEngine()


@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    search: str = Query("", alias="search"),
    source: str = Query("", alias="source"),
    sort: str = Query("created_at", alias="sort"),
    order: str = Query("desc", alias="order"),
):
    session = get_session()
    query = session.query(Job)

    if search:
        query = query.filter(
            Job.title.ilike(f"%{search}%") | Job.company.ilike(f"%{search}%")
        )
    if source:
        query = query.filter(Job.source == source)

    order_col = getattr(Job, sort, Job.created_at)
    if order == "asc":
        query = query.order_by(order_col.asc())
    else:
        query = query.order_by(order_col.desc())

    jobs = query.limit(200).all()
    sources = [r[0] for r in session.query(Job.source).distinct().all()]

    last_log = (
        session.query(ScrapeLog).order_by(desc(ScrapeLog.id)).first()
    )

    session.close()

    return templates.TemplateResponse(request, "dashboard.html", {
        "jobs": jobs,
        "sources": sources,
        "active_search": search,
        "active_source": source,
        "active_sort": sort,
        "active_order": order,
        "last_log": last_log,
        "keywords": FALLBACK_KEYWORDS,
        "vc_boards": VC_BOARDS,
    })


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    session = get_session()
    logs = session.query(ScrapeLog).order_by(desc(ScrapeLog.id)).limit(50).all()
    session.close()
    return templates.TemplateResponse(request, "logs.html", {"logs": logs})


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse(request, "chat.html", {
        "ai_configured": ai_engine.is_available(),
    })


@app.get("/api/chat/messages")
async def chat_messages():
    session = get_session()
    msgs = (
        session.query(ChatMessage).order_by(desc(ChatMessage.id)).limit(100).all()
    )
    msgs.reverse()
    session.close()
    return [{"role": m.role, "content": m.content, "id": m.id} for m in msgs]


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    session = get_session()
    db_kw = session.query(Setting).filter(Setting.key == "search_keywords").first()
    keywords = json.loads(db_kw.value) if db_kw and db_kw.value else FALLBACK_KEYWORDS
    db_resume = session.query(Setting).filter(Setting.key == "resume_text").first()
    resume_text = db_resume.value if db_resume and db_resume.value else FALLBACK_RESUME
    db_groq = session.query(Setting).filter(Setting.key == "groq_api_key").first()
    groq_set = db_groq.value if db_groq and db_groq.value else ""
    session.close()
    return templates.TemplateResponse(request, "settings.html", {
        "keywords": keywords,
        "vc_boards": VC_BOARDS,
        "resume_text": resume_text[:80] + "..." if len(resume_text) > 80 else (resume_text or ""),
        "resume_len": len(resume_text),
        "ai_configured": ai_engine.is_available(),
        "groq_configured": bool(groq_set),
    })


@app.post("/api/chat")
async def chat_send(request: Request):
    data = await request.json()
    message = data.get("message", "")

    session = get_session()
    user_msg = ChatMessage(role="user", content=message)
    session.add(user_msg)
    session.commit()
    session.close()

    from app.agent.engine import JobAgent
    agent = JobAgent()
    response_text = agent.chat_respond(message)

    session = get_session()
    assistant_msg = ChatMessage(role="assistant", content=response_text)
    session.add(assistant_msg)
    session.commit()
    session.close()

    return JSONResponse({
        "user": {"role": "user", "content": message},
        "assistant": {"role": "assistant", "content": response_text},
    })


@app.post("/api/scrape")
async def trigger_scrape():
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        executor.submit(run_full_scrape)
    return JSONResponse({"status": "started"})


@app.get("/api/agent/status")
async def agent_status():
    from app.agent.engine import JobAgent
    agent = JobAgent()
    return agent.get_status()


@app.get("/api/agent/cycle")
async def trigger_agent_cycle():
    from app.agent.engine import JobAgent
    agent = JobAgent()
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        executor.submit(agent.cycle)
    return JSONResponse({"status": "started"})


@app.get("/api/stats")
async def api_stats():
    session = get_session()
    total_jobs = session.query(Job).count()
    source_counts = dict(
        session.query(Job.source, func.count(Job.id)).group_by(Job.source).all()
    )
    last_log = (
        session.query(ScrapeLog).order_by(desc(ScrapeLog.id)).first()
    )
    session.close()
    return {
        "total_jobs": total_jobs,
        "source_counts": source_counts,
        "last_scrape": {
            "status": last_log.status if last_log else None,
            "jobs_found": last_log.jobs_found if last_log else 0,
            "at": last_log.finished_at.isoformat() if last_log and last_log.finished_at else None,
        } if last_log else None,
    }


@app.get("/api/settings")
async def api_settings():
    keywords = _load_keywords()
    resume_text = _get_setting("resume_text", FALLBACK_RESUME)
    groq_key = _get_setting("groq_api_key", "")
    return {
        "keywords": keywords,
        "resume_len": len(resume_text),
        "resume_preview": resume_text[:120] + "..." if len(resume_text) > 120 else resume_text,
        "groq_configured": bool(groq_key),
        "ai_configured": ai_engine.is_available(),
    }


@app.post("/api/settings/groq")
async def api_set_groq(data: dict = Body(...)):
    key = (data.get("key") or "").strip()
    if not key:
        return JSONResponse({"ok": False, "error": "Key is required"}, status_code=400)
    _set_setting("groq_api_key", key)
    os.environ["GROQ_API_KEY"] = key
    write_env({"GROQ_API_KEY": key})
    import app.config as cfg
    cfg.GROQ_API_KEY = key
    global ai_engine
    ai_engine = AIEngine()
    return {"ok": True, "configured": ai_engine.is_available()}


@app.get("/api/settings/keywords")
async def api_get_keywords():
    return {"keywords": _load_keywords()}


@app.post("/api/settings/keywords")
async def api_add_keyword(data: dict = Body(...)):
    kw = (data.get("keyword") or "").strip()
    if not kw:
        return JSONResponse({"ok": False, "error": "Keyword is required"}, status_code=400)
    kws = _load_keywords()
    if kw in kws:
        return {"ok": False, "error": "Already exists"}
    kws.append(kw)
    _save_keywords(kws)
    return {"ok": True, "keywords": kws}


@app.delete("/api/settings/keywords/{keyword:path}")
async def api_delete_keyword(keyword: str):
    kws = _load_keywords()
    keyword = keyword.strip()
    if keyword not in kws:
        return {"ok": False, "error": "Not found"}
    kws.remove(keyword)
    _save_keywords(kws)
    return {"ok": True, "keywords": kws}


@app.post("/api/settings/resume")
async def api_upload_resume(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"ok": False, "error": "Only PDF files accepted"}, status_code=400)
    content = await file.read()
    doc = fitz.open(stream=content, filetype="pdf")
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    if not text.strip():
        return JSONResponse({"ok": False, "error": "Could not extract text from PDF"}, status_code=400)
    _set_setting("resume_text", text.strip())
    write_env({"RESUME_TEXT": text.strip()[:500]})
    import app.config as cfg
    cfg.RESUME_TEXT = text.strip()
    return {
        "ok": True,
        "len": len(text.strip()),
        "preview": text.strip()[:200] + "..." if len(text.strip()) > 200 else text.strip(),
    }


@app.delete("/api/settings/resume")
async def api_delete_resume():
    _del_setting("resume_text")
    write_env({"RESUME_TEXT": ""})
    import app.config as cfg
    cfg.RESUME_TEXT = ""
    return {"ok": True}

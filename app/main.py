from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.logging_config import setup_logging
from app.services.auth import get_current_user_optional


# ------------------------------------------------------------------
# Lifespan: start/stop browser & worker depending on RUN_MODE
# ------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    run_mode = settings.run_mode.lower()

    if run_mode in ("worker", "both"):
        from app.services.screenshot import start_browser
        from app.services.queue_svc import start_worker

        await start_browser()
        await start_worker()

    yield  # --- App is running ---

    if run_mode in ("worker", "both"):
        from app.services.queue_svc import stop_worker
        from app.services.screenshot import stop_browser

        await stop_worker()
        await stop_browser()


# ------------------------------------------------------------------
# App factory
# ------------------------------------------------------------------
app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

# CORS — restrict to your domain in production
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Rate-limit error handler
from app.routes.webhook import limiter  # noqa: E402
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ------------------------------------------------------------------
# Mount routers
# ------------------------------------------------------------------
from app.routes.auth import router as auth_router         # noqa: E402
from app.routes.webhook import router as webhook_router   # noqa: E402
from app.routes.dashboard import router as dashboard_router  # noqa: E402
from app.routes.billing import router as billing_router   # noqa: E402
from app.routes.admin import router as admin_router     # noqa: E402

app.include_router(auth_router)
app.include_router(webhook_router)
app.include_router(dashboard_router)
app.include_router(billing_router)
app.include_router(admin_router)

# ------------------------------------------------------------------
# Page routes (landing, login, register)
# ------------------------------------------------------------------
templates = Jinja2Templates(directory="app/templates")


@app.get("/")
async def landing(request: Request):
    user = await get_current_user_optional(request)
    return templates.TemplateResponse(
        "landing.html",
        {"request": request, "user": user, "app_name": settings.app_name, "title": "Home"},
    )


@app.get("/login")
async def login_page(request: Request):
    user = await get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "user": None, "app_name": settings.app_name, "title": "Login"},
    )


@app.get("/register")
async def register_page(request: Request):
    user = await get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "user": None, "app_name": settings.app_name, "title": "Sign Up"},
    )


@app.get("/pricing")
async def pricing_page(request: Request):
    user = await get_current_user_optional(request)
    return templates.TemplateResponse(
        "pricing.html",
        {"request": request, "user": user, "app_name": settings.app_name, "title": "Pricing"},
    )


@app.get("/terms")
async def terms_page(request: Request):
    user = await get_current_user_optional(request)
    return templates.TemplateResponse(
        "terms.html",
        {"request": request, "user": user, "app_name": settings.app_name, "app_url": settings.app_url, "title": "Terms & Conditions"},
    )


# ------------------------------------------------------------------
# Health checks
# ------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/playwright")
async def health_playwright():
    from app.services.screenshot import _browser

    return {
        "browser_running": _browser is not None and _browser.is_connected(),
    }


@app.get("/health/queue")
async def health_queue():
    """Report pending job count — useful for monitoring dashboards."""
    from app.db import AsyncSessionLocal
    from app.models.alert import AlertLog
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(func.count(AlertLog.id)).where(AlertLog.status == "queued")
        )
        pending = result.scalar()
    return {"pending_jobs": pending}


# ------------------------------------------------------------------
# Custom error pages
# ------------------------------------------------------------------
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "user": None,
            "app_name": settings.app_name,
            "title": "Page Not Found",
            "message": "The page you're looking for doesn't exist.",
            "emoji": "🔍",
        },
        status_code=404,
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "user": None,
            "app_name": settings.app_name,
            "title": "Server Error",
            "message": "Something went wrong on our end. Please try again later.",
            "emoji": "💥",
        },
        status_code=500,
    )

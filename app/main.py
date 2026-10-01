from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.logging_config import setup_logging
from app.services.auth import get_current_user_optional
from app.templates_config import templates


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
# templates is imported from app.templates_config


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


@app.get("/tradingview-alerts-to-discord")
async def tradingview_discord_page(request: Request):
    """SEO landing page for "TradingView alerts to Discord" searches."""
    user = await get_current_user_optional(request)
    name = settings.app_name
    faqs = [
        ("Do I need a paid TradingView plan?",
         "Yes. TradingView only allows webhook notifications on its paid plans, and webhooks are how "
         f"alerts reach {name}. Discord itself is free."),
        ("Do I have to change how I write my alerts?",
         "No. Messages like \"AAPL, 1D Crossing horizontal ray\" or \"NASDAQ:AAPL breakout\" are read "
         "automatically. For the most reliable results you can paste the one-line message from your dashboard, "
         "which lets TradingView fill in the exact symbol."),
        ("Which chart timeframe is shown?",
         "The daily chart by default. You can pick a fixed timeframe in your settings, or have each screenshot "
         "match the chart the alert came from."),
        ("Can the screenshot show my own indicators?",
         "Yes. Turn on sharing for a TradingView chart layout and paste its link in your settings. Screenshots "
         "then use that layout's indicators, drawings and style."),
        ("How fast do alerts arrive in Discord?",
         "Usually within 20 seconds of TradingView firing the alert, including the time to load and capture the chart."),
        ("Can I post to more than one Discord channel?",
         "Yes. Add as many Discord webhooks as you need and every alert is posted to all of them."),
        ("Is there a free plan?",
         f"Yes. The free plan includes {settings.free_alerts_per_day} "
         f"alert{'' if settings.free_alerts_per_day == 1 else 's'} a day, with no card required."),
    ]
    return templates.TemplateResponse(
        "tradingview_discord.html",
        {
            "request": request,
            "user": user,
            "app_name": name,
            "app_url": settings.app_url,
            "faqs": faqs,
        },
    )


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    return (
        "User-agent: *\n"
        "Disallow: /dashboard\n"
        "Disallow: /admin\n"
        "Disallow: /billing\n"
        "Disallow: /webhook\n"
        f"Sitemap: {settings.app_url}/sitemap.xml\n"
    )


@app.get("/sitemap.xml")
async def sitemap_xml():
    pages = ["/", "/tradingview-alerts-to-discord", "/pricing", "/register", "/terms"]
    urls = "".join(f"<url><loc>{settings.app_url}{p}</loc></url>" for p in pages)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    )
    return Response(content=xml, media_type="application/xml")


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
@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok"}


@app.get("/health/playwright")
async def health_playwright():
    from app.services.screenshot import _browser

    return {
        "browser_running": _browser is not None and _browser.is_connected(),
    }


@app.api_route("/health/queue", methods=["GET", "HEAD"])
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
@app.exception_handler(401)
async def auth_exception_handler(request: Request, exc):
    return RedirectResponse(url="/login")


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

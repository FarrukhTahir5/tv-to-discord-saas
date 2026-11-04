from fastapi.templating import Jinja2Templates

from app.config import settings

templates = Jinja2Templates(directory="app/templates")

# Plan numbers for every page, so prices and limits are only defined in config
templates.env.globals["plans"] = {
    "free_alerts": settings.free_alerts_per_day,
    "pro_alerts": settings.pro_alerts_per_day,
    "free_channels": settings.free_max_channels,
    "trial_days": settings.trial_days,
    "pro_monthly": settings.pro_price_monthly,
    "pro_yearly_monthly": settings.pro_price_yearly_per_month,
    "pro_yearly_total": settings.pro_price_yearly_per_month * 12,
    "yearly_saving_pct": round(
        100 * (1 - settings.pro_price_yearly_per_month / settings.pro_price_monthly)
    ),
}

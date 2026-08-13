from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from app.web.shared.templating import templates
from app.web.shared.session import get_current_auth_user

from app.web.shared.user_repository import (
    get_or_create_user_record,
    set_user_tenant
)

from app.repositories.tenant_repository import (
    create_tenant,
    get_tenant,
    get_whatsapp_account_by_tenant,
    upsert_whatsapp_account
)

from app.repositories.working_hours_repository import (
    get_working_hours,
    upsert_working_hours,
    WEEKDAYS
)

from app.repositories.service_repository import (
    get_active_services,
    create_service,
    delete_service
)

from app.repositories.faq_repository import (
    get_faq,
    create_faq,
    delete_faq
)


router = APIRouter()

DAY_LABELS = {
    "monday": "Lunedì", "tuesday": "Martedì", "wednesday": "Mercoledì",
    "thursday": "Giovedì", "friday": "Venerdì",
    "saturday": "Sabato", "sunday": "Domenica"
}


def _require_tenant(request: Request):
    """
    Ritorna (auth_user, user_record, tenant) oppure None se manca
    l'autenticazione o il tenant non e' ancora stato creato (step 1).
    """
    auth_user = get_current_auth_user(request)
    if not auth_user:
        return None

    user_record = get_or_create_user_record(auth_user.get("id"))
    if not user_record.get("tenant_id"):
        return None

    tenant = get_tenant(user_record["tenant_id"])
    return auth_user, user_record, tenant


# ==================================================
# DASHBOARD
# ==================================================

@router.get("/onboarding")
def onboarding_dashboard(request: Request):

    auth_user = get_current_auth_user(request)
    if not auth_user:
        return RedirectResponse(url="/login", status_code=302)

    user_record = get_or_create_user_record(auth_user.get("id"))

    tenant = None
    whatsapp_account = None
    working_hours = []
    services = []

    if user_record.get("tenant_id"):
        tenant = get_tenant(user_record["tenant_id"])
        whatsapp_account = get_whatsapp_account_by_tenant(tenant["id"])
        working_hours = get_working_hours(tenant["id"])
        services = get_active_services(tenant["id"])

    has_tenant = bool(tenant)
    has_whatsapp = bool(whatsapp_account and whatsapp_account.get("access_token"))
    has_hours = len(working_hours) > 0
    has_services = len(services) > 0

    is_live = has_whatsapp and has_hours and has_services

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "email": auth_user.get("email"),
            "has_tenant": has_tenant,
            "tenant": tenant,
            "steps_unlocked": has_tenant,
            "whatsapp_missing": has_tenant and not has_whatsapp,
            "is_live": is_live,
            "has_whatsapp": has_whatsapp,
            "has_hours": has_hours,
            "has_services": has_services,
            "error": None
        }
    )


@router.post("/onboarding/business")
def onboarding_business_submit(
    request: Request,
    business_name: str = Form(...),
    timezone: str = Form(...),
    language: str = Form(...),
    assistant_name: str = Form(None)
):
    auth_user = get_current_auth_user(request)
    if not auth_user:
        return RedirectResponse(url="/login", status_code=302)

    user_record = get_or_create_user_record(auth_user.get("id"))

    tenant = create_tenant(
        business_name=business_name,
        timezone=timezone,
        language=language,
        assistant_name=assistant_name or None
    )

    set_user_tenant(user_record["id"], tenant["id"])

    return RedirectResponse(url="/onboarding", status_code=302)


# ==================================================
# WHATSAPP
# ==================================================

@router.get("/onboarding/whatsapp")
def whatsapp_page(request: Request):
    result = _require_tenant(request)
    if not result:
        return RedirectResponse(url="/onboarding", status_code=302)

    _, _, tenant = result
    account = get_whatsapp_account_by_tenant(tenant["id"])

    return templates.TemplateResponse(
        request,
        "whatsapp.html",
        {"account": account, "error": None}
    )


@router.post("/onboarding/whatsapp")
def whatsapp_submit(
    request: Request,
    phone_number: str = Form(...),
    phone_number_id: str = Form(...),
    access_token: str = Form(...)
):
    result = _require_tenant(request)
    if not result:
        return RedirectResponse(url="/onboarding", status_code=302)

    _, _, tenant = result

    upsert_whatsapp_account(
        tenant_id=tenant["id"],
        phone_number=phone_number,
        access_token=access_token,
        phone_number_id=phone_number_id
    )

    return RedirectResponse(url="/onboarding", status_code=302)


# ==================================================
# ORARI
# ==================================================

@router.get("/onboarding/hours")
def hours_page(request: Request):
    result = _require_tenant(request)
    if not result:
        return RedirectResponse(url="/onboarding", status_code=302)

    _, _, tenant = result
    existing = {row["day_of_week"]: row for row in get_working_hours(tenant["id"])}

    days = [
        {
            "key": key,
            "label": DAY_LABELS[key],
            "open_time": existing.get(key, {}).get("open_time"),
            "close_time": existing.get(key, {}).get("close_time"),
            "closed": existing.get(key, {}).get("closed", False)
        }
        for key in WEEKDAYS
    ]

    return templates.TemplateResponse(
        request,
        "hours.html",
        {"days": days}
    )


@router.post("/onboarding/hours")
async def hours_submit(request: Request):
    result = _require_tenant(request)
    if not result:
        return RedirectResponse(url="/onboarding", status_code=302)

    _, _, tenant = result

    form = await request.form()

    for day in WEEKDAYS:
        closed = form.get(f"closed_{day}") == "on"
        open_time = form.get(f"open_{day}")
        close_time = form.get(f"close_{day}")

        upsert_working_hours(
            tenant_id=tenant["id"],
            day=day,
            open_time=open_time,
            close_time=close_time,
            closed=closed
        )

    return RedirectResponse(url="/onboarding", status_code=302)


# ==================================================
# SERVIZI
# ==================================================

@router.get("/onboarding/services")
def services_page(request: Request):
    result = _require_tenant(request)
    if not result:
        return RedirectResponse(url="/onboarding", status_code=302)

    _, _, tenant = result
    services = get_active_services(tenant["id"])

    return templates.TemplateResponse(
        request,
        "services.html",
        {"services": services, "error": None}
    )


@router.post("/onboarding/services")
def services_submit(
    request: Request,
    name: str = Form(...),
    duration_minutes: int = Form(...),
    price: float = Form(None)
):
    result = _require_tenant(request)
    if not result:
        return RedirectResponse(url="/onboarding", status_code=302)

    _, _, tenant = result

    create_service(
        tenant_id=tenant["id"],
        name=name,
        duration_minutes=duration_minutes,
        price=price
    )

    return RedirectResponse(url="/onboarding/services", status_code=302)


@router.post("/onboarding/services/delete/{service_id}")
def services_delete(request: Request, service_id: str):
    result = _require_tenant(request)
    if not result:
        return RedirectResponse(url="/onboarding", status_code=302)

    _, _, tenant = result
    delete_service(tenant["id"], service_id)

    return RedirectResponse(url="/onboarding/services", status_code=302)


# ==================================================
# FAQ
# ==================================================

@router.get("/onboarding/faq")
def faq_page(request: Request):
    result = _require_tenant(request)
    if not result:
        return RedirectResponse(url="/onboarding", status_code=302)

    _, _, tenant = result
    faqs = get_faq(tenant["id"])

    return templates.TemplateResponse(
        request,
        "faq.html",
        {"faqs": faqs}
    )


@router.post("/onboarding/faq")
def faq_submit(
    request: Request,
    question: str = Form(...),
    answer: str = Form(...)
):
    result = _require_tenant(request)
    if not result:
        return RedirectResponse(url="/onboarding", status_code=302)

    _, _, tenant = result
    create_faq(tenant["id"], question, answer)

    return RedirectResponse(url="/onboarding/faq", status_code=302)


@router.post("/onboarding/faq/delete/{faq_id}")
def faq_delete(request: Request, faq_id: str):
    result = _require_tenant(request)
    if not result:
        return RedirectResponse(url="/onboarding", status_code=302)

    _, _, tenant = result
    delete_faq(tenant["id"], faq_id)

    return RedirectResponse(url="/onboarding/faq", status_code=302)

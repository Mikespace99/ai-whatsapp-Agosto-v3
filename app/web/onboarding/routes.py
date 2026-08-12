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
    get_tenant
)


router = APIRouter()


@router.get("/onboarding")
def onboarding_dashboard(request: Request):

    auth_user = get_current_auth_user(request)

    if not auth_user:
        return RedirectResponse(url="/login", status_code=302)

    user_record = get_or_create_user_record(auth_user.get("id"))

    tenant = None
    if user_record.get("tenant_id"):
        tenant = get_tenant(user_record["tenant_id"])

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "email": auth_user.get("email"),
            "has_tenant": bool(tenant),
            "tenant": tenant,
            # Gli step 2-5 si sbloccano tutti insieme appena esiste il
            # tenant, non in sequenza rigida (nessuna dipendenza tecnica
            # reale tra Orari/Servizi/WhatsApp/FAQ).
            "steps_unlocked": bool(tenant),
            # WhatsApp non collegato = il bot non risponde ai clienti.
            # Avviso permanente, indipendente da cos'altro e' stato
            # completato.
            "whatsapp_missing": bool(tenant),  # True finche' non costruiamo lo step 4
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

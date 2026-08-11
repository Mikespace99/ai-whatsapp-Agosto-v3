from pathlib import Path

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.web.supabase_auth import (
    signup_user,
    login_user,
    get_user_from_token
)

from app.web.user_repository import (
    get_or_create_user_record,
    set_user_tenant
)

from app.repositories.tenant_repository import (
    create_tenant
)


router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

SESSION_COOKIE_NAME = "sb_access_token"


def get_current_auth_user(request: Request):
    """
    Legge il cookie di sessione e verifica il token con Supabase Auth.
    Ritorna il dict utente Supabase Auth, o None se non autenticato.
    """
    access_token = request.cookies.get(SESSION_COOKIE_NAME)
    return get_user_from_token(access_token)


# ==================================================
# SIGNUP
# ==================================================

@router.get("/signup")
def signup_page(request: Request):
    return templates.TemplateResponse(
        request,
        "signup.html",
        {"error": None}
    )


@router.post("/signup")
def signup_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    success, result = signup_user(email, password)

    if not success:
        return templates.TemplateResponse(
            request,
            "signup.html",
            {"error": result},
            status_code=400
        )

    # Con la conferma email disattivata, la risposta di signup
    # contiene gia' un access_token utilizzabile per il login diretto.
    access_token = result.get("access_token")

    if not access_token:
        # Conferma email ancora attiva sul progetto Supabase:
        # l'utente deve prima confermare via email prima di poter accedere.
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": (
                    "Registrazione avvenuta. Controlla la tua email "
                    "per confermare l'account prima di accedere."
                )
            }
        )

    auth_user = result.get("user", {})
    get_or_create_user_record(auth_user.get("id"))

    response = RedirectResponse(url="/onboarding", status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=access_token,
        httponly=True,
        samesite="lax",
        max_age=3600
    )
    return response


# ==================================================
# LOGIN
# ==================================================

@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": None}
    )


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    success, result = login_user(email, password)

    if not success:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": result},
            status_code=401
        )

    access_token = result.get("access_token")

    response = RedirectResponse(url="/onboarding", status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=access_token,
        httponly=True,
        samesite="lax",
        max_age=3600
    )
    return response


# ==================================================
# LOGOUT
# ==================================================

@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


# ==================================================
# ONBOARDING (placeholder per ora — solo verifica auth)
# ==================================================

@router.get("/onboarding")
def onboarding_placeholder(request: Request):

    auth_user = get_current_auth_user(request)

    if not auth_user:
        return RedirectResponse(url="/login", status_code=302)

    user_record = get_or_create_user_record(auth_user.get("id"))

    if not user_record.get("tenant_id"):
        return templates.TemplateResponse(
            request,
            "onboarding_business.html",
            {"error": None}
        )

    return templates.TemplateResponse(
        request,
        "onboarding_placeholder.html",
        {
            "email": auth_user.get("email"),
            "has_tenant": True,
            "tenant_id": user_record.get("tenant_id")
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

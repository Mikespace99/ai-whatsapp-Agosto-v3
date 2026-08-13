from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from app.web.shared.templating import templates
from app.web.shared.session import (
    SESSION_COOKIE_NAME,
    set_session_cookie
)

from app.web.auth.supabase_auth import (
    signup_user,
    login_user
)

from app.web.shared.user_repository import (
    get_or_create_user_record
)


router = APIRouter()


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
    return set_session_cookie(response, access_token)


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
    return set_session_cookie(response, access_token)


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response

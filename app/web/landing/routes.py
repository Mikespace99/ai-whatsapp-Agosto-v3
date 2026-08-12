from fastapi import APIRouter, Request

from app.web.shared.templating import templates


router = APIRouter()


@router.get("/")
def landing_page(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {}
    )

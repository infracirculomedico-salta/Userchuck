"""
Punto de Entrada del Portal Web de WhatsApp - Círculo Médico de Salta.
"""

import sys
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Asegurar rutas en sys.path
PORTAL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PORTAL_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "sender") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "sender"))

from portal.auth import verificar_token
from portal.config import SESSION_COOKIE_NAME
from portal.routes.auth_routes import router as auth_router
from portal.routes.campanas_routes import router as campanas_router
from portal.routes.contactos_routes import router as contactos_router
from portal.routes.dashboard_routes import router as dashboard_router
from portal.routes.mensajes_routes import router as mensajes_router
from portal.routes.plantillas_routes import router as plantillas_router
from portal.routes.usuarios_routes import router as usuarios_router

app = FastAPI(
    title="Portal WhatsApp — Círculo Médico de Salta",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
)

# Servir archivos estáticos (CSS, JS)
app.mount("/static", StaticFiles(directory=str(PORTAL_DIR / "static")), name="static")

# Templates Jinja2
templates = Jinja2Templates(directory=str(PORTAL_DIR / "templates"))

# Incluir routers de la API
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(mensajes_router)
app.include_router(contactos_router)
app.include_router(plantillas_router)
app.include_router(campanas_router)
app.include_router(usuarios_router)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Página principal del portal (Dashboard SPA)."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token or not verificar_token(token):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Página de inicio de sesión."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token and verificar_token(token):
        return RedirectResponse(url="/")
    return templates.TemplateResponse(request=request, name="login.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("portal.main:app", host="0.0.0.0", port=8007, reload=True)

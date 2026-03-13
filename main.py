from fastapi import FastAPI, HTTPException, Request, Form, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from scrap_orcess import scrap_40_reviews_tokopedia
from converter import validate_tokopedia_url
import uvicorn
import re
import httpx
import time
import logging

# ===============================
# LOGGING
# ===============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ===============================
# RATE LIMITER SETUP
# ===============================
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


# ===============================
# APP INIT
# ===============================
app = FastAPI(
    docs_url=None,    # matikan /docs
    redoc_url=None,   # matikan /redoc
    openapi_url=None, # matikan /openapi.json
)

# ===============================
# SECURITY: RATE LIMIT HANDLER
# ===============================
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


# ===============================
# SECURITY: CORS
# Ganti origins sesuai domain frontend kamu.
# Jangan gunakan ["*"] di production!
# ===============================
ALLOWED_ORIGINS = [
    "http://localhost:8001",
    "http://localhost:3000",
    "54.255.188.16",    
    # "https://yourdomain.com",  # ← tambahkan domain production kamu di sini/IP disini
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],       # hanya izinkan method yang diperlukan
    allow_headers=["Content-Type"],      # batasi header yang diizinkan
    max_age=600,                         # cache preflight 10 menit
)


# ===============================
# SECURITY: TRUSTED HOST
# Tolak request dengan Host header yang tidak dikenal (mencegah Host header injection)
# ===============================
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "localhost",
        "127.0.0.1",
        "54.255.188.16",   
        # "yourdomain.com",   # ← tambahkan domain production kamu
    ],
)


# ===============================
# SECURITY: REQUEST SIZE LIMIT
# Tolak body lebih dari 64KB untuk cegah payload flooding
# ===============================
MAX_BODY_SIZE = 64 * 1024  # 64 KB

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_SIZE:
            logger.warning(f"[BLOCKED] Oversized request from {request.client.host} — {content_length} bytes")
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"detail": "Request body terlalu besar."},
            )
        return await call_next(request)

app.add_middleware(RequestSizeLimitMiddleware)


# ===============================
# SECURITY: SECURITY HEADERS
# Tambahkan HTTP security headers standar di setiap response
# ===============================
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline';"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)


# ===============================
# SECURITY: REQUEST LOGGING
# Log semua request masuk untuk monitoring
# ===============================
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        duration = round((time.time() - start_time) * 1000, 2)
        logger.info(
            f"{request.method} {request.url.path} "
            f"— IP: {request.client.host} "
            f"— Status: {response.status_code} "
            f"— {duration}ms"
        )
        return response

app.add_middleware(RequestLoggingMiddleware)


# ===============================
# TEMPLATES & STATIC
# ===============================
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

MODEL_API_URL = "http://13.215.251.64:8000/summarize"


# ===============================
# ROUTES
# ===============================
@app.get("/", response_class=HTMLResponse)
@limiter.limit("30/minute")  # batas lebih ketat untuk GET homepage
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "summary": None,
            "error": None,
        },
    )


@app.post("/summarize", response_class=HTMLResponse)
@limiter.limit("10/minute")  # endpoint berat → batasi lebih ketat
async def summarize(
    request: Request,
    product_url: str = Form(...),
):
    try:
        # ===============================
        # 1. SCRAPING
        # ===============================
        url = validate_tokopedia_url(product_url)
        if not url:
            raise HTTPException(
                status_code=400,
                detail="URL yang anda masukan salah, silakan coba lagi",
            )

        scrapped_data = await scrap_40_reviews_tokopedia(url=url)
        if not scrapped_data:
            raise HTTPException(
                status_code=400,
                detail="⚠️ Gagal melakukan scraping ulasan. Periksa kembali URL produk atau pastikan produk memiliki ulasan",
            )
        if scrapped_data["total_reviews"] < 5:
            raise HTTPException(
                status_code=400,
                detail="Produk memiliki terlalu sedikit ulasan, minimal 5 ulasan untuk dirangkum",
            )

        joined_text = scrapped_data["joined_text"].strip()

        cleaned_text = joined_text.replace(".", "").strip()
        if not cleaned_text:
            raise HTTPException(status_code=404, detail="Ulasan kosong")

        logger.info(f"Scraping berhasil — {scrapped_data['total_reviews']} ulasan")

        # ===============================
        # 2. HIT MODEL SERVER
        # ===============================
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                MODEL_API_URL,
                json={"text": joined_text},
            )

        if response.status_code != 200:
            raise Exception(f"Model error: {response.text}")

        raw_summary = response.json()["summary"].strip()

        # ===============================
        # 3. PARSING BULLET → UL LI
        # ===============================
        parts = re.split(r"\s*•\s*", raw_summary)
        intro_text = parts[0].strip()
        bullet_parts = parts[1:] if len(parts) > 1 else []

        html_summary = ""

        if intro_text:
            intro_text = intro_text[0].upper() + intro_text[1:]
            html_summary += f"<p>{intro_text}</p>"

        if bullet_parts:
            html_summary += "<ul>"
            for item in bullet_parts:
                match = re.match(r"([^:]+):(.*)", item, re.DOTALL)
                if match:
                    title = match.group(1).strip().capitalize()
                    content = match.group(2).strip()
                    html_summary += f"<li><b>{title}:</b> {content}</li>"
                else:
                    html_summary += f"<li>{item.strip()}</li>"
            html_summary += "</ul>"

        # ===============================
        # 4. RENDER HTML
        # ===============================
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "original_review": joined_text,
                "summary": html_summary,
                "jumlah_ulasan": scrapped_data["total_reviews"],
                "error": None,
                "product_url": product_url,
            },
        )

    except HTTPException as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "summary": None,
                "error": e.detail,
                "product_url": product_url,
            },
        )
    except Exception as e:
        logger.error(f"Unhandled error: {e}")
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "summary": None,
                "error": "Terjadi kesalahan internal. Silakan coba lagi.",
                "product_url": product_url,
            },
        )


# ===============================
# RUN LOCAL
# ===============================
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        # workers=2,  # aktifkan ini untuk production (bukan reload mode)
    )
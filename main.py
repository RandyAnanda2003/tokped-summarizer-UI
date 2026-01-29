from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from scrapper import scrape_tokopedia_reviews
import uvicorn


# # ===============================
# # LIFESPAN (STARTUP & SHUTDOWN)
# # ===============================
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     # STARTUP     
#     load_model()
#     yield
#     # SHUTDOWN (optional cleanup)


# ===============================
# APP INIT
# ===============================
app = FastAPI()

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

templates = Jinja2Templates(directory="templates")


# ===============================
# ROUTES
# ===============================
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Homepage - menampilkan form input URL Tokopedia"""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "summary": None,
            "error": None
        }
    )


from fastapi import Request, Form, HTTPException
from fastapi.responses import HTMLResponse
import httpx

MODEL_API_URL = "http://127.0.0.1:8000/summarize"

@app.post("/summarize", response_class=HTMLResponse)
async def summarize(
    request: Request,
    product_url: str = Form(...)
):
    """
    Endpoint scraping + hit model server
    """
    try:
        # ===============================
        # 1. SCRAPING
        # ===============================
        scrapped_data = await scrape_tokopedia_reviews(product_url)

        if not scrapped_data:
            raise HTTPException(
                status_code=404,
                detail="Gagal melakukan scraping ulasan"
            )

        print(f"📝 Total ulasan: {scrapped_data['total_reviews']}")

        # ===============================
        # 2. HIT MODEL SERVER
        # ===============================
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                MODEL_API_URL,
                json={
                    "text": scrapped_data["joined_text"]
                }
            )

        if response.status_code != 200:
            raise Exception(f"Model error: {response.text}")

        summary = response.json()["summary"]

        # ===============================
        # 3. RENDER HTML
        # ===============================
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "summary": summary,
                "jumlah_ulasan": scrapped_data["total_reviews"],
                "error": None,
                "product_url": product_url
            }
        )

    except Exception as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "summary": None,
                "error": str(e),
                "product_url": product_url
            }
        )


# ===============================
# RUN LOCAL
# ===============================
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000
    )

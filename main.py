from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from scrapper import scrape_tokopedia_reviews
import uvicorn
import re
import httpx


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

MODEL_API_URL = "http://13.48.58.127:8000/summarize"


# ===============================
# ROUTES
# ===============================
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "summary": None,
            "error": None
        }
    )


@app.post("/summarize", response_class=HTMLResponse)
async def summarize(
    request: Request,
    product_url: str = Form(...)
):
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
        
        joined_text = scrapped_data["joined_text"].strip()
        
        # Validasi teks kosong / hanya titik
        cleaned_text = joined_text.replace(".", "").strip()
        if not cleaned_text:
            raise HTTPException(
                status_code=404,
                detail="Ulasan kosong"
            )
        
        print(f"Total ulasan: {scrapped_data['total_reviews']}")
        
        # ===============================
        # 2. HIT MODEL SERVER
        # ===============================
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                MODEL_API_URL,
                json={
                    "text": joined_text
                }
            )
        
        if response.status_code != 200:
            raise Exception(f"Model error: {response.text}")
        
        raw_summary = response.json()["summary"].strip()
        

        # ===============================
        # 3. PARSING BULLET → UL LI
        # ===============================

        # Pisahkan bagian sebelum bullet pertama
        parts = re.split(r"\s*•\s*", raw_summary)

        intro_text = parts[0].strip()
        bullet_parts = parts[1:] if len(parts) > 1 else []

        html_summary = ""

        # Tambahkan paragraf awal
        if intro_text:
            intro_text = intro_text[0].upper() + intro_text[1:]
            html_summary += f"<p>{intro_text}</p>"

        # Kalau ada bullet
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
                "summary": html_summary,
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
        port=8001
    )


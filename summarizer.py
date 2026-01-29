from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

# ===============================
# FASTAPI APP
# ===============================
app = FastAPI(
    title="IndoT5 Summarization API",
    description="API untuk ringkasan teks menggunakan IndoT5",
    version="1.0"
)

# ===============================
# LOAD MODEL (HANYA SEKALI)
# ===============================
MODEL_NAME = "siRendy/model_skripsi_ringkasan_ulasan_ecom_final"

print("🚀 Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

print("🚀 Loading model...")
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
model.eval()

print(f"✅ Model loaded on device: {device}")

# ===============================
# REQUEST SCHEMA
# ===============================
class SummarizeRequest(BaseModel):
    text: str

# ===============================
# CORE LOGIC
# ===============================
def summarize_text(text: str) -> str:
    inputs = tokenizer.encode(
        f"ringkaslah: {text}",
        return_tensors="pt",
        max_length=4000,
        truncation=True
    ).to(device)

    with torch.no_grad():
        summary_ids = model.generate(
            inputs,
            max_length=300,
            min_length=60,
            num_beams=25,
            do_sample=False,
            repetition_penalty=1.2,
            length_penalty=1.2,
            early_stopping=True
        )

    return tokenizer.decode(
        summary_ids[0],
        skip_special_tokens=True
    )

# ===============================
# API ENDPOINT
# ===============================
@app.post("/summarize")
def summarize(req: SummarizeRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text tidak boleh kosong")

    summary = summarize_text(req.text)
    return {
        "summary": summary
    }

# ===============================
# OPTIONAL: HEALTH CHECK
# ===============================
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "device": str(device)
    }

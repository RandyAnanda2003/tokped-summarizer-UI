from fastapi import HTTPException
from playwright.async_api import async_playwright
import asyncio
import emoji
import re

TARGET_REVIEWS = 60
REVIEWS_PER_PAGE = 10
MAX_PAGE = TARGET_REVIEWS // REVIEWS_PER_PAGE

from urllib.parse import urlparse

def to_review_url(url: str) -> str:
    parsed = urlparse(url)
    clean_path = parsed.path.rstrip("/")

    if not clean_path.endswith("/review"):
        clean_path += "/review"

    return f"{parsed.scheme}://{parsed.netloc}{clean_path}"

def validate_tokopedia_url(url: str):
    if "tokopedia.com" not in url:
        raise HTTPException(
            status_code=400,
            detail="URL harus dari Tokopedia"
        )
def remove_repeated_phrases(text, min_phrase_len=2):
    words = text.split()
    n = len(words)

    result = []
    i = 0

    while i < n:
        found = False

        for size in range(min_phrase_len, (n - i) // 2 + 1):
            phrase = words[i:i + size]

            repeat = 1
            while words[i + size * repeat:i + size * (repeat + 1)] == phrase:
                repeat += 1

            if repeat > 1:
                result.extend(phrase)
                i += size * repeat
                found = True
                break

        if not found:
            result.append(words[i])
            i += 1

    return " ".join(result)


def clean_review_text(text):
    if not isinstance(text, str):
        return ""

    # 1. lowercase
    text = text.lower()

    # 2. hapus emoji
    text = emoji.replace_emoji(text, replace="")

    # 3. hapus emoticon
    emot_pattern = r"""
        (?:
            [:=;][oO\-]?[D\)\]\(\]/\\OpP] |
            [D\)\]\(\]/\\OpP][oO\-]?[=:;] |
            <3 |
            t_t |
            x_x |
            xd
        )
    """
    text = re.sub(emot_pattern, "", text, flags=re.VERBOSE | re.IGNORECASE)

    # 4. hapus ketawa
    laughter_pattern = r'\b(?:ha|he|hi|ho|hu|wk|kw){2,}\b'
    text = re.sub(laughter_pattern, ' ', text)

    # 5. keyboard smash
    random_word_pattern = r'\b[bcdfghjklmnpqrstvwxyz]{6,}\b'
    text = re.sub(random_word_pattern, ' ', text)

    # 6. karakter berlebih
    text = re.sub(r'(.)\1{2,}', r'\1', text)

    # 7. kata nempel
    text = re.sub(r'\b(\w{2,})\1+\b', r'\1', text)

    # 8. hapus titik
    text = text.replace('.', ' ')

    # 9. simbol
    text = re.sub(r'[^a-z\s]', ' ', text)

    # 10. karakter tunggal
    text = re.sub(r'\b[a-z]\b', ' ', text)

    # 11. kata berulang
    text = re.sub(r'\b(\w+)\b(\s+\1){2,}', r'\1', text)

    # 11a. frasa berulang
    text = remove_repeated_phrases(text)

    # 12. rapikan spasi
    text = re.sub(r'\s+', ' ', text).strip()

    return text

# ===============================
# MAIN SCRAPER
# ===============================
async def scrape_tokopedia_reviews(url: str):
    validate_tokopedia_url(url)

    raw_reviews = []
    review_url = to_review_url(url)

    print(f"🔗 Buka URL: {review_url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,   # ❗ jangan headless (anti detect)
            slow_mo=80
        )

        page = await browser.new_page()
        await page.goto(review_url, timeout=60000)

        # ===============================
        # 1. Pastikan review muncul
        # ===============================
        try:
            await page.wait_for_selector("#review-feed", timeout=20000)
            print("✅ Halaman review siap")
        except:
            await browser.close()
            return []

        # ===============================
        # 2. Sorting TERBARU
        # ===============================
        try:
            await page.click('button[data-testid="reviewSorting"]')
            await asyncio.sleep(1)

            await page.get_by_text("Terbaru", exact=True).click()
            await asyncio.sleep(3)
            print("✅ Sorting TERBARU")
        except:
            print("⚠️ Gagal set sorting")

        # ===============================
        # 3. Pagination & Scraping
        # ===============================
        for laman in range(1, MAX_PAGE + 1):
            print(f"📄 Ambil laman {laman}")

            if laman > 1:
                try:
                    selector = f'button[aria-label="Laman {laman}"]'
                    await page.wait_for_selector(selector, timeout=25000)
                    await page.eval_on_selector(
                        selector,
                        "el => el.scrollIntoView({block: 'center'})"
                    )
                    await asyncio.sleep(1)
                    await page.eval_on_selector(selector, "el => el.click()")
                    await asyncio.sleep(3)
                except:
                    print(f"⛔ Gagal klik laman {laman}")
                    break

            nodes = await page.query_selector_all(
                '#review-feed span[data-testid="lblItemUlasan"]'
            )

            for node in nodes:
                try:
                    parent = await node.evaluate_handle(
                        "el => el.closest('p')"
                    )

                    btn = await parent.query_selector("button")
                    if btn:
                        txt = (await btn.inner_text()).lower()
                        if "selengkapnya" in txt:
                            await btn.click()
                            await asyncio.sleep(0.4)

                    text = (await node.inner_text()).strip()

                    if text:
                        raw_reviews.append(text)

                    if len(raw_reviews) >= TARGET_REVIEWS:
                        break

                except Exception as e:
                    print("⚠️ Skip ulasan:", e)

            if len(raw_reviews) >= TARGET_REVIEWS:
                break

        await browser.close()
        # return raw_reviews[:TARGET_REVIEWS]

    # ===============================
    # 4. CLEANING + DEDUP
    # ===============================
    cleaned_reviews = []
    seen = set()

    for review in raw_reviews:
        cleaned = clean_review_text(review)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            cleaned_reviews.append(cleaned)

    # ===============================
    # 5. JOIN DENGAN TITIK
    # ===============================
    if cleaned_reviews : 
        joined_text = ". ".join(cleaned_reviews) + "."
    else :
        joined_text = ""

    print(f"✅ Total review bersih: {len(cleaned_reviews)}")

    return {
        "total_reviews": len(cleaned_reviews),
        "joined_text": joined_text
    }



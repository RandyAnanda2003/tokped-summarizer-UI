import requests
import json
import csv
import time
import os


# ─────────────────────────────────────────────
#  KONFIGURASI
# ─────────────────────────────────────────────
PRODUCT_ID   = "100227626831"   # ← ganti sesuai produk yang ingin di-scrape
LIMIT        = 10               # jumlah review per halaman (maks 10)
SORT_BY      = "time desc"
FILTER_BY    = ""
OUTPUT_FILE  = "reviews_output.csv"
DELAY_SEC    = 1.0              # jeda antar request (detik) – jangan terlalu cepat


# ─────────────────────────────────────────────
#  HEADERS HTTP
# ─────────────────────────────────────────────
HEADERS = {
    "accept": "*/*",
    "bd-device-id": "7599816693359330817",
    "content-type": "application/json",
    "referer": "https://www.tokopedia.com/",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": '"Android"',
    "user-agent": (
        "Mozilla/5.0 (Linux; Android 8.0.0; SM-G955U Build/R16NW) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Mobile Safari/537.36"
    ),
    "x-device": "desktop",
    "x-price-center": "true",
    "x-source": "tokopedia-lite",
    "x-tkpd-lite-service": "zeus",
    "x-tkpd-pdpb": "0",
    "x-version": "a6610c6",
}


# ─────────────────────────────────────────────
#  GRAPHQL QUERY
# ─────────────────────────────────────────────
GQL_QUERY = """
query productReviewList($productID: String!, $page: Int!, $limit: Int!, $sortBy: String, $filterBy: String) {
  productrevGetProductReviewList(productID: $productID, page: $page, limit: $limit, sortBy: $sortBy, filterBy: $filterBy) {
    productID
    list {
      id: feedbackID
      variantName
      message
      productRating
      reviewCreateTime
      reviewCreateTimestamp
      isAnonymous
      user {
        userID
        fullName
        __typename
      }
      __typename
    }
    hasNext
    totalReviews
    __typename
  }
}
"""


# ─────────────────────────────────────────────
#  FUNGSI FETCH SATU HALAMAN
# ─────────────────────────────────────────────
def fetch_reviews(product_id: str, page: int, limit: int = 10) -> dict | None:
    payload = [
        {
            "operationName": "productReviewList",
            "variables": {
                "productID": product_id,
                "page": page,
                "limit": limit,
                "sortBy": SORT_BY,
                "filterBy": FILTER_BY,
            },
            "query": GQL_QUERY,
        }
    ]

    try:
        response = requests.post(
            "https://gql.tokopedia.com/graphql/productReviewList",
            headers=HEADERS,
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        return data[0]["data"]["productrevGetProductReviewList"]

    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] Request gagal pada halaman {page}: {e}")
        return None
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"  [ERROR] Parsing respons gagal pada halaman {page}: {e}")
        return None


# ─────────────────────────────────────────────
#  FUNGSI SCRAPE SEMUA HALAMAN
# ─────────────────────────────────────────────
def scrape_all_reviews(product_id: str, limit: int = 10, max_reviews: int = None) -> list[dict]:
    all_messages = []
    page = 1

    print(f"\n{'='*50}")
    print(f"  Mulai scraping Product ID: {product_id}")
    if max_reviews:
        print(f"  Target       : {max_reviews} review terbaru")
    print(f"{'='*50}\n")

    while True:
        print(f"  Mengambil halaman {page} ...", end=" ")
        result = fetch_reviews(product_id, page, limit)

        if result is None:
            print("SKIP (error)")
            break

        reviews = result.get("list", [])
        has_next = result.get("hasNext", False)
        total    = result.get("totalReviews", "?")

        if not reviews:
            print("tidak ada data.")
            break

        for r in reviews:
            all_messages.append({
                "feedback_id"       : r.get("id", ""),
                "variant"           : r.get("variantName", ""),
                "message"           : r.get("message", "").replace("\n", " "),
                "rating"            : r.get("productRating", ""),
                "created_timestamp" : r.get("reviewCreateTimestamp", ""),
                "user_name"         : r.get("user", {}).get("fullName", ""),
                "is_anonymous"      : r.get("isAnonymous", False),
            })

            # ── Berhenti jika sudah capai target ──
            if max_reviews and len(all_messages) >= max_reviews:
                all_messages = all_messages[:max_reviews]  # trim jika kelebihan
                print(f"OK  ({len(reviews)} ulasan | total: {len(all_messages)}/{total})")
                print(f"\n  ✅ Target {max_reviews} review tercapai.")
                return all_messages

        print(f"OK  ({len(reviews)} ulasan | total sejauh ini: {len(all_messages)}/{total})")

        if not has_next:
            print("\n  Semua halaman sudah diambil.")
            break

        page += 1
        time.sleep(DELAY_SEC)

    return all_messages


# ─────────────────────────────────────────────
#  SIMPAN KE CSV
# ─────────────────────────────────────────────
def save_to_csv(reviews: list[dict], filename: str) -> None:
    if not reviews:
        print("  Tidak ada data untuk disimpan.")
        return

    fieldnames = ["feedback_id", "variant", "message", "rating",
                  "created_timestamp", "user_name", "is_anonymous"]

    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(reviews)

    print(f"\n  ✅  Data tersimpan di: {os.path.abspath(filename)}")
    print(f"  Total baris        : {len(reviews)}")


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    reviews = scrape_all_reviews(PRODUCT_ID, LIMIT)
    save_to_csv(reviews, OUTPUT_FILE)

    # Tampilkan 3 contoh pesan
    if reviews:
        print("\n--- Contoh 3 pesan pertama ---")
        for i, r in enumerate(reviews[:3], 1):
            print(f"\n[{i}] Rating : {r['rating']} ⭐")
            print(f"    Varian : {r['variant']}")
            print(f"    Pesan  : {r['message']}")
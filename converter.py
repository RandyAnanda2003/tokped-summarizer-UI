import requests
import json
import re
from urllib.parse import urlparse


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
    "x-tkpd-akamai": "pdpMainInfo",
    "x-tkpd-lite-service": "zeus",
    "x-tkpd-pdpb": "0",
    "x-version": "a6610c6",
}


# ─────────────────────────────────────────────
#  GRAPHQL QUERY (hanya ambil basicInfo)
# ─────────────────────────────────────────────
GQL_QUERY = """
query PDPMainInfo($productKey: String, $shopDomain: String, $layoutID: String,
                  $extraPayload: String, $queryParam: String, $source: String,
                  $userLocation: pdpUserLocation) {
  pdpMainInfo(shopDomain: $shopDomain, productKey: $productKey,
              layoutID: $layoutID, extraPayload: $extraPayload,
              queryParam: $queryParam, source: $source, userLocation: $userLocation) {
    data {
      basicInfo {
        alias
        id: productID
        shopID
        shopName
        status
        url
        __typename
      }
      __typename
    }
    __typename
  }
}
"""


# ─────────────────────────────────────────────
#  PARSE URL → (shop_domain, product_key)
# ─────────────────────────────────────────────
def parse_tokopedia_url(url: str) -> tuple[str, str] | tuple[None, None]:
    """
    Contoh URL yang didukung:
      https://www.tokopedia.com/co-cloth-852/celana-pendek-pria-...
      https://tokopedia.com/co-cloth-852/celana-pendek-pria-...
    
    Return: (shop_domain, product_key)
    """
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]

    if len(path_parts) < 2:
        return None, None

    shop_domain = path_parts[0]
    # Ambil product_key — buang query string di bagian akhir jika ada
    product_key = path_parts[1].split("?")[0]

    return shop_domain, product_key


# ─────────────────────────────────────────────
#  FETCH PRODUCT ID DARI API
# ─────────────────────────────────────────────
def get_product_id(url: str) -> dict | None:
    """
    Menerima URL produk Tokopedia, mengembalikan dict berisi:
      - product_id
      - shop_id
      - shop_name
      - alias
      - status
      - product_url
    """
    shop_domain, product_key = parse_tokopedia_url(url)

    if not shop_domain or not product_key:
        print(f"  [ERROR] URL tidak valid: {url}")
        return None

    print(f"  Shop Domain : {shop_domain}")
    print(f"  Product Key : {product_key}")

    payload = [
        {
            "operationName": "PDPMainInfo",
            "variables": {
                "productKey": product_key,
                "shopDomain": shop_domain,
                "layoutID": "",
                "extraPayload": "",
                "queryParam": "",
                "source": "P1",
                "userLocation": {
                    "addressID": "",
                    "districtID": "2274",
                    "postalCode": "",
                    "latlon": "",
                    "cityID": "176",
                },
            },
            "query": GQL_QUERY,
        }
    ]

    try:
        response = requests.post(
            "https://gql.tokopedia.com/graphql/PDPMainInfo",
            headers=HEADERS,
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        basic_info = (
            data[0]["data"]["pdpMainInfo"]["data"]["basicInfo"]
        )

        return {
            "product_id" : basic_info.get("id", ""),
            "shop_id"    : basic_info.get("shopID", ""),
            "shop_name"  : basic_info.get("shopName", ""),
            "alias"      : basic_info.get("alias", ""),
            "status"     : basic_info.get("status", ""),
            "product_url": basic_info.get("url", ""),
        }

    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] Request gagal: {e}")
        return None
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"  [ERROR] Parsing respons gagal: {e}")
        return None


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    # ── Contoh penggunaan ──────────────────────
    test_urls = [
        "https://www.tokopedia.com/co-cloth-852/celana-pendek-pria-wanita-dewasa-corduroy-real-pict-santai-premium-tebal-nyaman-board-shorts-distro-surfing-casual-keren-1729885911389210964?t_id=1772561838224&t_st=1&t_pp=homepage&t_efo=pure_goods_card&t_ef=homepage&t_sm=rec_homepage_outer_flow&t_spt=homepage",
        # Tambahkan URL lain di sini:
        # "https://www.tokopedia.com/nama-toko/nama-produk",
    ]

    print("\n" + "=" * 60)
    print("  Tokopedia URL → Product ID Converter")
    print("=" * 60)

    for url in test_urls:
        print(f"\n🔗 URL  : {url[:80]}...")
        result = get_product_id(url)

        if result:
            print(f"\n  ✅ Berhasil!")
            print(f"  Product ID  : {result['product_id']}")
            print(f"  Shop ID     : {result['shop_id']}")
            print(f"  Shop Name   : {result['shop_name']}")
            print(f"  Status      : {result['status']}")
            print(f"  Alias       : {result['alias'][:60]}...")
        else:
            print("  ❌ Gagal mendapatkan Product ID.")

    print("\n" + "=" * 60)

    # ── Mode interaktif ────────────────────────
    print("\n[Mode Interaktif] Masukkan URL produk Tokopedia.")
    print("Ketik 'exit' untuk keluar.\n")

    while True:
        url_input = input("URL: ").strip()
        if url_input.lower() in ("exit", "quit", "q"):
            break
        if not url_input:
            continue

        result = get_product_id(url_input)
        if result:
            print(f"\n  ✅ Product ID  : {result['product_id']}")
            print(f"     Shop Name   : {result['shop_name']}")
            print(f"     Status      : {result['status']}\n")
        else:
            print("  ❌ Gagal. Pastikan URL valid.\n")
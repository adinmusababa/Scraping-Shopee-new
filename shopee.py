import requests
import csv
from datetime import datetime
import json


def load_cookie(cookies_json) -> str:
    """Load cookies from a JSON file.

    Supports two formats:
    1. A list of cookie objects, each with 'name' and 'value' keys.
    2. A dict (e.g., exported from a browser extension) containing a 'data' field.
       In the latter case we attempt to extract the cookie string from the 'data'
       field; if not possible we return an empty string and warn the caller.
    """
    with open(cookies_json) as f:
        cookies_data = json.load(f)

    # If the JSON is a dict with a 'data' key, treat it as already‑formatted cookie string.
    if isinstance(cookies_data, dict):
        # The 'data' field may contain the raw cookie header.
        raw = cookies_data.get("data")
        if isinstance(raw, str):
            return raw
        # Fallback: nothing usable.
        return ""

    # Expect a list of cookie dicts.
    if not isinstance(cookies_data, list):
        return ""

    cookie_parts = []
    for entry in cookies_data:
        name = entry.get("name")
        value = entry.get("value")
        if name is None or value is None:
            continue
        cookie_parts.append(f"{name}={value}")

    return ";".join(cookie_parts)


def shopee(url, cookies_json):
    """Fetch Shopee shop ratings and write them to a CSV file.

    This version adds:
    • Proper **browser‑like headers** (User‑Agent, Accept, etc.)
    • A **10‑second timeout** for each HTTP call to avoid hanging
    • **Retry logic** (3 attempts with exponential back‑off) via a
      ``requests.Session`` and ``urllib3`` ``Retry``
    • Basic **logging** to both console and a file ``scrape.log`` so you
      can inspect what happened after the script finishes.
    """
    import logging
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    # Logging configuration (writes to console and to scrape.log in the cwd)
    logger = logging.getLogger("shopee_scraper")
    logger.setLevel(logging.INFO)
    # Avoid adding duplicate handlers if function is called multiple times
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        # Console handler
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)
        # File handler
        fh = logging.FileHandler("scrape.log", encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    shop_url = url.split("/")
    cookies = load_cookie(cookies_json)

    if not cookies:
        logger.error("Cookies not valid – aborting.")
        return

    # Browser‑like headers – many sites ignore plain ``requests`` headers.
    headers = {
        "content-type": "application/json",
        "cookie": cookies,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://shopee.co.id/",
    }

    # Session with retry logic (3 retries, exponential back‑off)
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)

    user_id = shop_url[4]
    shop_id = shop_url[5].replace("rating?shop_id=", "")
    count = 0
    result = []
    while True:
        try:
            count += 6
            api_url = (
                "https://shopee.co.id/api/v4/seller_operation/get_shop_ratings_new"
                f"?limit=6&offset={count}&replied=false&shopid={shop_id}&userid={user_id}"
            )
            logger.info(f"Requesting offset {count} …")
            resp = session.get(api_url, headers=headers, timeout=10)
            data_req = resp.json()
            # Safely get the list of reviews; break if empty
            data_review = data_req.get("data", {}).get("items", [])
            if not data_review:
                logger.info("No more review items – terminating loop.")
                break

            for value in data_review:
                data_result = {
                    "nama pengguna": value.get("author_username", ""),
                    "produk": value.get("product_items", [{}])[0].get("name", ""),
                    "review": value.get("comment", ""),
                    "rating": value.get("rating_star", ""),
                    "waktu transaksi": datetime.fromtimestamp(
                        value.get("ctime", 0)
                    ).strftime("%Y-%m-%d %H:%M"),
                }
                result.append(data_result)
                logger.info(f"Getting review from {data_result['nama pengguna']}")
        except (requests.exceptions.RequestException, KeyError) as e:
            logger.error(f"Request failed ({e}); stopping.")
            break

    if not result:
        logger.warning("No reviews were retrieved – check cookies or network.")
        return

    # Write CSV – file name includes shop id to avoid collisions.
    csv_name = f"shoope_rating_ptp_{shop_id}.csv"
    keys = result[0].keys()
    with open(csv_name, "w", newline="", encoding="utf-8") as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(result)
    logger.info(f"Data saved at {csv_name}")
    print(f"Data saved at {csv_name}")


if __name__ == '__main__':    
    # silakan ganti page rating toko jika ingin mengambil data review dan rating dari toko lain
    url_shop = "https://shopee.co.id/buyer/52636424/rating?shop_id=52635036"
    cookies_json = "cookies.json"
    shopee(url_shop, cookies_json)

import json
import os
from datetime import datetime
import requests

OUTPUT_FILE = "cagrilar.json"
MANUAL_FILE = "manuel_cagrilar.json"


def format_eu_date(date_str):
    """AB API'sinden gelen ISO tarihini YYYY-MM-DD formatına çevirir."""
    if not date_str:
        return None
    try:
        return date_str[:10]
    except Exception:
        return None


def fetch_eu_calls(limit=25):
    """AB Funding & Tenders (SEDIA) API'sinden açık ve yaklaşan Horizon Europe çağrılarını çeker."""
    url = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
    params = {
        "apiKey": "SEDIA",
        "text": "HORIZON",
        "pageSize": limit,
        "pageNumber": 1,
    }
    # 31094501: Forthcoming (Yaklaşan), 31094502: Open (Açık)
    payload = {
        "bool": {
            "must": [
                {"terms": {"type": ["1", "2"]}},
                {"terms": {"status": ["31094501", "31094502"]}},
            ]
        }
    }

    calls = []
    try:
        response = requests.post(
            url,
            params=params,
            files={"query": (None, json.dumps(payload), "application/json")},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        for item in data.get("results", []):
            meta = item.get("metadata", {})
            identifier = (meta.get("identifier") or [""])[0]
            title = (meta.get("title") or [identifier])[0]
            start_date = format_eu_date((meta.get("startDate") or [None])[0])
            deadline = format_eu_date((meta.get("deadlineDate") or [None])[0])

            if not start_date or not deadline:
                continue

            calls.append({
                "id": f"ab-{identifier}",
                "kurum": "AB",
                "baslik": f"{identifier} - {title[:80]}",
                "baslangic": start_date,
                "bitis": deadline,
                "url": f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{identifier.lower()}",
            })
    except Exception as e:
        print(f"AB API hatası: {e}")

    return calls


def load_manual_calls():
    """manuel_cagrilar.json dosyasındaki elle girilen çağrıları okur."""
    if not os.path.exists(MANUAL_FILE):
        return []
    try:
        with open(MANUAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Manuel dosya okuma hatası: {e}")
        return []


def main():
    manual_calls = load_manual_calls()
    eu_calls = fetch_eu_calls(limit=20)

    # Tekrar eden ID'leri önleyerek birleştir
    merged = {}
    for call in eu_calls + manual_calls:
        merged[call["id"]] = call

    final_list = list(merged.values())

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"Toplam {len(final_list)} çağrı {OUTPUT_FILE} dosyasına kaydedildi.")


if __name__ == "__main__":
    main()

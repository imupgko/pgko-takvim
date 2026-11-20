import json
import os
import re
from datetime import datetime
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

OUTPUT_FILE = "cagrilar.json"
MANUAL_FILE = "manuel_cagrilar.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def format_eu_date(date_str):
    if not date_str:
        return None
    try:
        return date_str[:10]
    except Exception:
        return None


def parse_tr_dates(text):
    matches = re.findall(r"\b(\d{2})[./](\d{2})[./](\d{4})\b", text)
    dates = []
    for day, month, year in matches:
        try:
            dt = datetime(int(year), int(month), int(day))
            dates.append(dt.strftime("%Y-%m-%d"))
        except ValueError:
            continue
    return sorted(set(dates))


def parse_single_date(date_str):
    if not date_str or date_str.strip() == "-":
        return None
    dates = parse_tr_dates(date_str)
    if dates:
        return dates[0]
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", date_str)
    if m:
        return m.group(0)
    return None


def fetch_eu_calls(limit=50):
    """AB Funding & Tenders API'sinden tekrarsız, açık ve yaklaşan Horizon çağrılarını çeker."""
    url = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
    params = {
        "apiKey": "SEDIA",
        "text": "HORIZON",
        "pageSize": limit,
        "pageNumber": 1,
    }
    payload = {
        "bool": {
            "must": [
                {"terms": {"type": ["1", "2"]}},
                {"terms": {"status": ["31094501", "31094502"]}},
                {"terms": {"language": ["en"]}},
            ]
        }
    }

    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    seen_ids = set()
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
            identifier = (meta.get("identifier") or [""])[0].strip()
            if not identifier or identifier in seen_ids:
                continue

            title = (meta.get("title") or [identifier])[0]
            start_dates = [format_eu_date(d) for d in (meta.get("startDate") or []) if format_eu_date(d)]
            deadlines = [format_eu_date(d) for d in (meta.get("deadlineDate") or []) if format_eu_date(d)]

            if not start_dates or not deadlines:
                continue

            start_date = min(start_dates)
            deadline = max(deadlines)

            # Süresi geçmiş çağrıları atla
            if deadline < today_str:
                continue

            seen_ids.add(identifier)
            calls.append({
                "id": f"ab-{identifier}",
                "kurum": "AB",
                "baslik": identifier,
                "program_adi": title,
                "baslangic": start_date,
                "bitis": deadline,
                "url": f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{identifier.lower()}",
            })
    except Exception as e:
        print(f"AB API hatası: {e}")

    print(f"AB: {len(calls)} benzersiz açık çağrı çekildi.")
    return calls


def fetch_tubitak_calls():
    """ardeb-pbs.tubitak.gov.tr tablosundan hem dönemlik hem sürekli açık çağrıları çeker."""
    target_url = "https://ardeb-pbs.tubitak.gov.tr/"
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    calls = []

    try:
        resp = requests.get(target_url, headers=HEADERS, timeout=25, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        rows = soup.find_all("tr", attrs={"data-program-cagri-id": True})
        print(f"TÜBİTAK teşhis: Tabloda {len(rows)} satır bulundu.")

        for row in rows:
            cagri_id = row.get("data-program-cagri-id", "").strip()
            program_adi = row.get("data-program-adi", "").strip()
            cagri_adi = row.get("data-cagri-adi", "").strip()
            cagri_turu = row.get("data-cagri-turu", "").strip()
            baslangic_raw = row.get("data-baslangic", "").strip()
            bitis_raw = row.get("data-bitis", "").strip()
            detay_url = row.get("data-bilgi-notu-url", "").strip() or target_url

            start_date = parse_single_date(baslangic_raw)
            end_date = parse_single_date(bitis_raw)
            baslik = cagri_adi if cagri_adi and cagri_adi != "-" else program_adi

            # Tarihi olmayan veya "Sürekli" etiketli çağrılar
            if not end_date or "sürekli" in cagri_turu.lower():
                calls.append({
                    "id": f"tubitak-{cagri_id}",
                    "kurum": "TÜBİTAK",
                    "baslik": baslik,
                    "program_adi": program_adi,
                    "surekli_acik": True,
                    "baslangic": today_str,
                    "bitis": today_str,
                    "url": detay_url,
                })
            else:
                calls.append({
                    "id": f"tubitak-{cagri_id}",
                    "kurum": "TÜBİTAK",
                    "baslik": baslik,
                    "program_adi": program_adi,
                    "surekli_acik": False,
                    "baslangic": start_date or today_str,
                    "bitis": end_date,
                    "url": detay_url,
                })
    except Exception as e:
        print(f"TÜBİTAK ARDEB-PBS tarama hatası: {e}")

    print(f"TÜBİTAK: {len(calls)} çağrı çekildi.")
    return calls


def fetch_tuseb_calls():
    """TÜSEB TBYS BFF API'sinden (AktifCagrilar) doğrudan aktif çağrıları çeker."""
    api_url = "https://tbysbff.tuseb.gov.tr/api/Cagri/AktifCagrilar"
    portal_url = "https://tbys.tuseb.gov.tr/"
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    calls = []

    headers = {
        **HEADERS,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://tbys.tuseb.gov.tr",
        "Referer": "https://tbys.tuseb.gov.tr/",
    }

    try:
        resp = requests.post(api_url, headers=headers, json={}, timeout=25, verify=False)
        resp.raise_for_status()
        payload = resp.json()

        items = (payload.get("value") or {}).get("data") or []
        print(f"TÜSEB API teşhis: {len(items)} aktif çağrı döndü.")

        for item in items:
            cagri_id = item.get("id") or ""
            kodu = (item.get("kodu") or "").strip()
            konu = (item.get("konu") or "").strip()
            start_raw = item.get("baslangicTarihi")
            end_raw = item.get("bitisTarihi")

            start_date = format_eu_date(start_raw)
            end_date = format_eu_date(end_raw)
            is_always_open = not bool(end_date)

            calls.append({
                "id": f"tuseb-{cagri_id or kodu}",
                "kurum": "TÜSEB",
                "baslik": kodu if kodu else (konu[:60] + ("..." if len(konu) > 60 else "")),
                "program_adi": konu,
                "surekli_acik": is_always_open,
                "baslangic": start_date or today_str,
                "bitis": end_date or today_str,
                "url": portal_url,
            })
    except Exception as e:
        print(f"TÜSEB API hatası: {e}")

    print(f"TÜSEB: {len(calls)} çağrı çekildi.")
    return calls


def load_manual_calls():
    if not os.path.exists(MANUAL_FILE):
        return []
    try:
        with open(MANUAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Manuel dosya okuma hatası: {e}")
        return []


def main():
    eu_calls = fetch_eu_calls(limit=50)
    tubitak_calls = fetch_tubitak_calls()
    tuseb_calls = fetch_tuseb_calls()
    manual_calls = load_manual_calls()

    merged = {}
    for call in eu_calls + tubitak_calls + tuseb_calls + manual_calls:
        merged[call["id"]] = call

    final_list = list(merged.values())

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"Toplam {len(final_list)} çağrı {OUTPUT_FILE} dosyasına kaydedildi.")

if __name__ == "__main__":
    main()

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
    """tbys.tuseb.gov.tr üzerinden açık çağrıları tarar."""
    target_url = "https://tbys.tuseb.gov.tr/"
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    calls = []

    try:
        resp = requests.get(target_url, headers=HEADERS, timeout=25, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Tablo satırları veya duyuru linklerini tara
        rows = soup.find_all("tr")
        print(f"TÜSEB TBYS teşhis: Sayfa yüklendi ({len(resp.text)} bayt), {len(rows)} tablo satırı bulundu.")

        for idx, row in enumerate(rows):
            text = " ".join(row.get_text(" ", strip=True).split())
            if len(text) < 15 or not any(k in text.lower() for k in ["çağrı", "proje", "destek", "ar-ge", "grubu"]):
                continue

            dates = parse_tr_dates(text)
            a_tag = row.find("a", href=True)
            link = a_tag["href"] if a_tag and a_tag["href"].startswith("http") else target_url

            is_always_open = len(dates) == 0
            calls.append({
                "id": f"tuseb-tbys-{idx}",
                "kurum": "TÜSEB",
                "baslik": text[:60] + ("..." if len(text) > 60 else ""),
                "program_adi": text,
                "surekli_acik": is_always_open,
                "baslangic": dates[0] if len(dates) >= 1 else today_str,
                "bitis": dates[-1] if len(dates) >= 1 else today_str,
                "url": link,
            })
    except Exception as e:
        print(f"TÜSEB TBYS tarama hatası: {e}")

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

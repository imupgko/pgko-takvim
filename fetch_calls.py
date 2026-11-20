import json
import os
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

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
    """Metin içindeki GG.AA.YYYY veya GG/AA/YYYY formatındaki tarihleri yakalar."""
    matches = re.findall(r"\b(\d{2})[./](\d{2})[./](\d{4})\b", text)
    dates = []
    for day, month, year in matches:
        try:
            dt = datetime(int(year), int(month), int(day))
            dates.append(dt.strftime("%Y-%m-%d"))
        except ValueError:
            continue
    return sorted(set(dates))


def fetch_eu_calls(limit=20):
    """AB Funding & Tenders (SEDIA) API'sinden açık ve yaklaşan Horizon Europe çağrılarını çeker."""
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
                "baslik": identifier,
                "program_adi": title,
                "baslangic": start_date,
                "bitis": deadline,
                "url": f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{identifier.lower()}",
            })
    except Exception as e:
        print(f"AB API hatası: {e}")

    print(f"AB: {len(calls)} çağrı çekildi.")
    return calls


def parse_single_date(date_str):
    """GG.AA.YYYY veya YYYY-MM-DD formatındaki tek bir tarihi YYYY-MM-DD'ye çevirir."""
    if not date_str or date_str.strip() == "-":
        return None
    # Önce GG.AA.YYYY veya GG/AA/YYYY ara
    dates = parse_tr_dates(date_str)
    if dates:
        return dates[0]
    # Alternatif olarak YYYY-MM-DD ara
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", date_str)
    if m:
        return m.group(0)
    return None


def fetch_tubitak_calls():
    """ardeb-pbs.tubitak.gov.tr tablosundaki data-* etiketlerinden aktif çağrıları çeker."""
    target_url = "https://ardeb-pbs.tubitak.gov.tr/"
    calls = []

    try:
        resp = requests.get(target_url, headers=HEADERS, timeout=25)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        rows = soup.find_all("tr", attrs={"data-program-cagri-id": True})
        for row in rows:
            cagri_id = row.get("data-program-cagri-id", "").strip()
            program_adi = row.get("data-program-adi", "").strip()
            cagri_adi = row.get("data-cagri-adi", "").strip()
            baslangic_raw = row.get("data-baslangic", "").strip()
            bitis_raw = row.get("data-bitis", "").strip()
            detay_url = row.get("data-bilgi-notu-url", "").strip() or target_url

            start_date = parse_single_date(baslangic_raw)
            end_date = parse_single_date(bitis_raw)

            # Sürekli açık ("-") veya tarihi olmayan çağrıları şeride ekleme
            if not start_date or not end_date:
                continue

            # Çubukta görünecek kısa başlık (çağrı adı boşsa program adını kullan)
            baslik = cagri_adi if cagri_adi and cagri_adi != "-" else program_adi

            calls.append({
                "id": f"tubitak-{cagri_id}",
                "kurum": "TÜBİTAK",
                "baslik": baslik,
                "program_adi": program_adi,
                "baslangic": start_date,
                "bitis": end_date,
                "url": detay_url,
            })
    except Exception as e:
        print(f"TÜBİTAK ARDEB-PBS tarama hatası: {e}")

    print(f"TÜBİTAK: {len(calls)} çağrı çekildi.")
    return calls


def fetch_tuseb_calls():
    """TÜSEB proje çağrıları/duyurular sayfasından tarih içeren çağrıları tarar."""
    base_url = "https://www.tuseb.gov.tr"
    target_url = "https://www.tuseb.gov.tr/duyurular"
    calls = []

    try:
        resp = requests.get(target_url, headers=HEADERS, timeout=25)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        seen_links = set()
        for a_tag in soup.find_all("a", href=True):
            text = " ".join(a_tag.get_text(" ", strip=True).split())
            href = a_tag["href"]

            if len(text) < 15 or not any(k in text.lower() for k in ["çağrı", "proje", "destek", "ar-ge", "başvuru", "grubu"]):
                continue

            full_url = urljoin(base_url, href)
            if full_url in seen_links:
                continue
            seen_links.add(full_url)

            parent_text = a_tag.parent.get_text(" ", strip=True) if a_tag.parent else text
            dates = parse_tr_dates(parent_text)

            if len(dates) >= 2:
                start_date, end_date = dates[0], dates[-1]
            elif len(dates) == 1:
                start_date = dates[0]
                end_date = (datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")
            else:
                continue

            slug = re.sub(r"[^a-zA-Z0-9]+", "-", href.strip("/"))[-40:]
            calls.append({
                "id": f"tuseb-{slug}",
                "kurum": "TÜSEB",
                "baslik": text[:65] + ("..." if len(text) > 65 else ""),
                "program_adi": text,
                "baslangic": start_date,
                "bitis": end_date,
                "url": full_url,
            })

            if len(calls) >= 15:
                break
    except Exception as e:
        print(f"TÜSEB tarama hatası: {e}")

    print(f"TÜSEB: {len(calls)} çağrı çekildi.")
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
    eu_calls = fetch_eu_calls(limit=20)
    tubitak_calls = fetch_tubitak_calls()
    tuseb_calls = fetch_tuseb_calls()
    manual_calls = load_manual_calls()

    # Manuel kayıtlar en sona eklendiği için aynı ID varsa manuel olan öncelikli olur
    merged = {}
    for call in eu_calls + tubitak_calls + tuseb_calls + manual_calls:
        merged[call["id"]] = call

    final_list = list(merged.values())

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"Toplam {len(final_list)} çağrı {OUTPUT_FILE} dosyasına kaydedildi.")


if __name__ == "__main__":
    main()

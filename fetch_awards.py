from io import BytesIO
from pypdf import PdfReader
import time
import json
import os
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

OUTPUT_FILE = "oduller.json"
MANUAL_FILE = "manuel_oduller.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

MONTHS_MAP = {
    "ocak": "01", "şubat": "02", "mart": "03", "nisan": "04",
    "mayıs": "05", "haziran": "06", "temmuz": "07", "ağustos": "08",
    "eylül": "09", "ekim": "10", "kasım": "11", "aralık": "12",
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

# Takip edilecek tüm akademik ödül kaynakları
AWARD_SOURCES = [
    # TÜBA
    {"kurum": "TÜBA", "ad": "TÜBA Ödülleri", "url": "https://www.tuba.gov.tr/tr/tuba-odulleri", "hub": True},
    # TÜBİTAK
    {"kurum": "TÜBİTAK", "ad": "TÜBİTAK Kurumsal Ödüller", "url": "https://tubitak.gov.tr/tr/kurumsal/oduller", "hub": True},
    {"kurum": "TÜBİTAK", "ad": "TÜBİTAK Bilim ve Toplum Ödülleri", "url": "https://tubitak.gov.tr/tr/destekler/bilim-toplum", "hub": True, "keywords": ["ödül", "odul"]},
    # YÖK
    {"kurum": "YÖK", "ad": "YÖK Üstün Başarı Ödülleri", "url": "https://proje.yok.gov.tr/tr/page/621"},
    
    # BAGEP
    {"kurum": "BAGEP", "ad": "Bilim Akademisi BAGEP Ödülleri", "url": "https://bilimakademisi.org/bagep/"},
    # Diğer Vakıf ve Kurum Ödülleri
    {"kurum": "Diğer", "ad": "L'Oréal-UNESCO Türkiye Ulusal Programı", "url": "https://www.forwomeninscience.com/authority/turkey---national-program", "hub": True, "keywords": ["discover", "know more", "challenge", "apply"], "allow_domain": True},
    {"kurum": "Diğer", "ad": "L'Oréal-UNESCO Uluslararası Ödülleri", "url": "https://www.forwomeninscience.com/authority/international-awards", "hub": True, "keywords": ["discover", "know more", "challenge", "apply"], "allow_domain": True},
    {"kurum": "Diğer", "ad": "ODTÜ Parlar Vakfı Ödülleri", "url": "https://parlar.org.tr/sayfa-odul-basvurulari-10"},
    {"kurum": "Diğer", "ad": "ODTÜ Parlar Duyurular", "url": "https://parlar.org.tr/duyurular", "hub": True, "keywords": ["ödül", "odul", "başvuru", "basvuru"], "allow_domain": True},
    {"kurum": "Diğer", "ad": "Rahmi M. Koç Bilim Madalyası", "url": "https://bilimmadalyasi.ku.edu.tr/", "hub": True, "keywords": ["başvuru", "basvuru", "aday", "nomination", "apply", "takvim", "calendar"], "allow_domain": True},
    {"kurum": "Diğer", "ad": "İlim Yayma Ödülleri", "url": "https://www.ilimyaymaodulleri.org/", "hub": True, "keywords": ["başvuru", "basvuru", "takvim", "duyuru"], "allow_domain": True},
    {"kurum": "Diğer", "ad": "Elginkan Vakfı Ödülleri", "url": "https://www.elginkanvakfi.org.tr/", "hub": True, "keywords": ["ödül", "odul", "teknoloji", "başvuru", "basvuru"], "allow_domain": True},
    {"kurum": "Diğer", "ad": "TGC Sedat Simavi Ödülleri", "url": "https://www.tgc.org.tr/oduller/sedat-simavi-odulleri.html", "hub": True, "keywords": ["simavi"], "allow_domain": True},
    {"kurum": "Diğer", "ad": "EIC & EIT European Prize for Women Innovators", "url": "https://eic.ec.europa.eu/eic-prizes/european-prize-women-innovators-powered-eic-eit_en", "hub": True, "keywords": ["women-innovators", "apply", "rules", "contest", "edition"], "allow_domain": True},
    {"kurum": "Diğer", "ad": "TÜRKPATENT ISIF Uluslararası Buluş Ödülleri", "url": "https://isif.turkpatent.gov.tr/", "hub": True, "keywords": ["apply", "başvuru", "basvuru"], "allow_domain": True},
    {"kurum": "Diğer", "ad": "IEEE Türkiye Bilim Ödülleri", "url": "https://www.ieee.org.tr/ieee-turkiye-bilim-odulleri/", "hub": True, "keywords": ["ödül", "odul", "başvuru", "basvuru"], "allow_domain": True},
    {"kurum": "Diğer", "ad": "IEEE Türkiye Duyurular", "url": "https://www.ieee.org.tr/", "hub": True, "keywords": ["ödül", "odul"], "allow_domain": True},
    {"kurum": "Diğer", "ad": "Kadir Has Ödülleri", "url": "https://www.khas.edu.tr/kadir-has-odulleri/", "hub": True, "keywords": ["başvuru", "basvuru", "aday", "ödül", "odul", "takvim"], "allow_domain": True},
    {"kurum": "Diğer", "ad": "Kadir Has Ödülleri Portalı", "url": "https://odul.khas.edu.tr/"},
    {"kurum": "Diğer", "ad": "AMS Matematik Ödülleri", "url": "https://www.ams.org/prizes-awards/palist.cgi?deadline=yes&sort=keyword-asc"},
]


def parse_tr_dates(text):
    """GG.AA.YYYY, '15 Mayıs 2026', '15 May 2026' ve 'May 15, 2026' tarihlerini YYYY-AA-GG listesi döner."""
    found = set()

    for d, m, y in re.findall(r"\b(\d{1,2})[./](\d{1,2})[./](20\d{2})\b", text):
        try:
            found.add(datetime(int(y), int(m), int(d)).strftime("%Y-%m-%d"))
        except ValueError:
            continue

    lower_text = text.lower()
    month_pattern = "|".join(MONTHS_MAP.keys())

    # "15 Mayıs 2026" veya "15 May 2026"
    for d, m_name, y in re.findall(rf"\b(\d{{1,2}})\s+({month_pattern})\s+(20\d{{2}})\b", lower_text):
        try:
            found.add(datetime(int(y), int(MONTHS_MAP[m_name]), int(d)).strftime("%Y-%m-%d"))
        except ValueError:
            continue

    # "May 15, 2026"
    for m_name, d, y in re.findall(rf"\b({month_pattern})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b", lower_text):
        try:
            found.add(datetime(int(y), int(MONTHS_MAP[m_name]), int(d)).strftime("%Y-%m-%d"))
        except ValueError:
            continue

    return sorted(found)


def extract_dates_from_pdf(pdf_url):
    try:
        resp = requests.get(pdf_url, headers=HEADERS, timeout=25, verify=False)
        resp.raise_for_status()
        reader = PdfReader(BytesIO(resp.content))
        text = " ".join((page.extract_text() or "") for page in reader.pages[:2])
        return parse_tr_dates(text)
    except Exception as e:
        print(f"PDF okuma hatası ({pdf_url}): {e}")
        return []


def fetch_url_with_retry(url, timeout=30):
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, verify=False)
            resp.raise_for_status()
            return resp
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
            else:
                print(f"Bağlantı hatası ({url}): {e}")
    return None


def fetch_award_source(source):
    """Ana sayfayı ve varsa güncel/gelecek yıl alt linklerini tarayıp ödül çağrılarını çıkarır."""
    kurum = source["kurum"]
    ad = source["ad"]
    page_url = source["url"]

    current_year = datetime.utcnow().year
    target_years = [str(current_year), str(current_year + 1)]
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    results = []

    resp = fetch_url_with_retry(page_url)
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup.find_all(["header", "nav", "footer"]):
        tag.decompose()

    # 1. Aşama: Sayfa içinde güncel/gelecek yıl içeren alt linkleri keşfet
    yearly_links = []
    seen_urls = set()
    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text(" ", strip=True).split())
        href = a["href"]
        combined = f"{text} {href}".lower()

        if any(y in combined for y in target_years):
            full_url = urljoin(page_url, href)
            if full_url not in seen_urls and full_url.rstrip("/") != page_url.rstrip("/"):
                seen_urls.add(full_url)
                yearly_links.append((text or ad, full_url))

    # --- YENİ: Hariç tutma (exclude_keywords) kontrolü ---
    exclude_keywords = source.get("exclude_keywords")
    main_text = soup.get_text(" ", strip=True)
    if exclude_keywords and any(k in main_text.lower() for k in exclude_keywords):
        print(f"{ad}: Uluslararası başvuruya kapalı (filtreyle elendi).")
        return []
    
    # 2. Aşama: Alt link varsa içlerinden tarih çek
    for link_text, detail_url in yearly_links[:4]:
        if detail_url.lower().endswith(".pdf"):
            dates = extract_dates_from_pdf(detail_url)
        else:
            d_resp = fetch_url_with_retry(detail_url, timeout=20)
            if not d_resp:
                continue
            d_soup = BeautifulSoup(d_resp.text, "html.parser")
            for tag in d_soup.find_all(["header", "nav", "footer"]):
                tag.decompose()
            dates = parse_tr_dates(d_soup.get_text(" ", strip=True))

        dates = [d for d in dates if d[:4] in target_years]
        if not dates:
            continue

        end_date = dates[-1]
        start_date = dates[0] if len(dates) >= 2 else (today_str if today_str < end_date else end_date)
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", detail_url.strip("/"))[-30:]

        results.append({
            "id": f"odul-{kurum.lower()}-{slug}",
            "kurum": kurum,
            "baslik": ad if len(link_text) < 8 else f"{ad} ({link_text[:30]})",
            "program_adi": f"{ad} - {link_text}",
            "surekli_acik": False,
            "baslangic": start_date,
            "bitis": end_date,
            "url": detail_url,
        })

    # 3. Aşama: Alt linkten tarih çıkmadıysa doğrudan ana sayfanın kendi metnindeki tarihleri kontrol et
    if not results:
        main_dates = [d for d in parse_tr_dates(soup.get_text(" ", strip=True)) if d[:4] in target_years]
        if main_dates:
            end_date = main_dates[-1]
            start_date = main_dates[0] if len(main_dates) >= 2 else (today_str if today_str < end_date else end_date)
            slug = re.sub(r"[^a-zA-Z0-9]+", "-", ad.lower())[:35]
            results.append({
                "id": f"odul-{kurum.lower()}-{slug}",
                "kurum": kurum,
                "baslik": ad,
                "program_adi": ad,
                "surekli_acik": False,
                "baslangic": start_date,
                "bitis": end_date,
                "url": page_url,
            })

    print(f"{ad}: {len(results)} kayıt bulundu.")
    return results

def fetch_hub_awards(source):
    """Ana ödül sayfasını ve altındaki tüm ödül/program linklerini (3 katmanlı) tarar."""
    hub_url = source["url"].rstrip("/")
    kurum = source["kurum"]
    results = []

    resp = fetch_url_with_retry(hub_url)
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup.find_all(["header", "nav", "footer"]):
        tag.decompose()

    # Eğer URL .htm/.html ile bitiyorsa klasör yolunu baz al (örn. .../odulBasvurulari/)
    if hub_url.lower().endswith((".htm", ".html")):
        base_prefix = hub_url.rsplit("/", 1)[0] + "/"
    else:
        base_prefix = hub_url + "/"

    # 1. Katman: Alt ödül/program sayfalarını keşfet
    allow_domain = source.get("allow_domain", False)
    hub_domain = urlparse(hub_url).netloc
    keywords = source.get("keywords")
    sub_pages = []
    seen = {hub_url}
    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text(" ", strip=True).split())
        full_url = urljoin(base_prefix, a["href"]).split("#")[0].rstrip("/")

        if keywords and not any(k in f"{text} {full_url}".lower() for k in keywords):
            continue

        valid_path = (urlparse(full_url).netloc == hub_domain) if allow_domain else full_url.startswith(base_prefix)
        if valid_path and full_url not in seen and len(text) >= 4:
            seen.add(full_url)
            sub_pages.append({
                "kurum": kurum,
                "ad": f"{source['ad']} - {text[:25]}",
                "url": full_url,
                "exclude_keywords": source.get("exclude_keywords"),
            })

    print(f"{source['ad']} (Merkez): {len(sub_pages)} alt sayfa keşfedildi.")

    # 2. ve 3. Katman: Keşfedilen alt sayfaları tara
    for sub in sub_pages[:20]:
        results.extend(fetch_award_source(sub))

    # Eğer alt sayfalardan kayıt çıkmadıysa ana sayfanın kendi içindeki tarihleri de kontrol et
    if not results:
        results.extend(fetch_award_source(source))

    return results

def fetch_tubitak_odul_portal():
    """oduller.tubitak.gov.tr portalındaki aktif ödül tablosunu okur (ARDEB-PBS ile aynı şablon)."""
    portal_url = "https://oduller.tubitak.gov.tr/odulBasvurulari/odulBasvurulari.htm"
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    results = []

    resp = fetch_url_with_retry(portal_url)
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    panel = soup.find("div", class_="index-portal-panel-body-table")
    if not panel:
        print("TÜBİTAK Ödül Portalı: Tablo alanı bulunamadı.")
        return []

    # 1. Durum: ARDEB-PBS tarzı data-* satırları varsa
    rows = panel.find_all("tr", attrs={"data-program-cagri-id": True})
    if rows:
        for row in rows:
            cagri_id = row.get("data-program-cagri-id", "").strip()
            program_adi = row.get("data-program-adi", "").strip()
            cagri_adi = row.get("data-cagri-adi", "").strip()
            baslangic = parse_tr_dates(row.get("data-baslangic", ""))
            bitis = parse_tr_dates(row.get("data-bitis", ""))
            detay_url = row.get("data-bilgi-notu-url", "").strip() or portal_url

            if not bitis:
                continue

            results.append({
                "id": f"odul-tubitak-portal-{cagri_id}",
                "kurum": "TÜBİTAK",
                "baslik": cagri_adi if cagri_adi and cagri_adi != "-" else program_adi,
                "program_adi": program_adi,
                "surekli_acik": False,
                "baslangic": baslangic[0] if baslangic else today_str,
                "bitis": bitis[-1],
                "url": detay_url,
            })
    else:
        # 2. Durum: Standart <table> satırları varsa
        for idx, tr in enumerate(panel.select("table tbody tr")):
            cols = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            row_text = " ".join(cols)
            dates = parse_tr_dates(row_text)
            if not dates or not cols:
                continue

            end_date = dates[-1]
            start_date = dates[0] if len(dates) >= 2 else (today_str if today_str < end_date else end_date)
            title = cols[0] if len(cols[0]) > 5 else row_text[:60]

            results.append({
                "id": f"odul-tubitak-portal-row-{idx}",
                "kurum": "TÜBİTAK",
                "baslik": title,
                "program_adi": title,
                "surekli_acik": False,
                "baslangic": start_date,
                "bitis": end_date,
                "url": portal_url,
            })

    print(f"TÜBİTAK Ödül Portalı: {len(results)} aktif çağrı bulundu.")
    return results

def fetch_tuseb_awards():
    """TÜSEB TBYS API'sinden adında 'ödül' veya 'Aziz Sancar' geçen aktif/geçmiş ödül çağrılarını çeker."""
    endpoints = [
        "https://tbysbff.tuseb.gov.tr/api/Cagri/AktifCagrilar",
        "https://tbysbff.tuseb.gov.tr/api/Cagri/GecmisCagrilar",
    ]
    portal_url = "https://tbys.tuseb.gov.tr/"
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    results = []
    seen_ids = set()

    headers = {
        **HEADERS,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://tbys.tuseb.gov.tr",
        "Referer": "https://tbys.tuseb.gov.tr/",
    }

    for api_url in endpoints:
        try:
            resp = requests.post(api_url, headers=headers, json={}, timeout=25, verify=False)
            resp.raise_for_status()
            items = (resp.json().get("value") or {}).get("data") or []

            for item in items:
                kodu = (item.get("kodu") or "").strip()
                konu = (item.get("konu") or "").strip()
                combined = f"{kodu} {konu}".lower()

                # Sadece ödül çağrılarını filtrele
                if not any(k in combined for k in ["ödül", "odul", "aziz sancar"]):
                    continue

                uid = f"odul-tuseb-{item.get('id') or kodu}"
                if uid in seen_ids:
                    continue

                start_date = (item.get("baslangicTarihi") or "")[:10]
                end_date = (item.get("bitisTarihi") or "")[:10]
                if not end_date or end_date < "2025-01-01":
                    continue

                seen_ids.add(uid)
                results.append({
                    "id": uid,
                    "kurum": "TÜSEB",
                    "baslik": kodu if kodu else (konu[:60] + ("..." if len(konu) > 60 else "")),
                    "program_adi": konu,
                    "surekli_acik": False,
                    "baslangic": start_date or today_str,
                    "bitis": end_date,
                    "url": portal_url,
                })
        except Exception as e:
            print(f"TÜSEB Ödül API hatası ({api_url}): {e}")

    print(f"TÜSEB Ödülleri (TBYS): {len(results)} kayıt bulundu.")
    return results

def load_manual_awards():
    if not os.path.exists(MANUAL_FILE):
        return []
    try:
        with open(MANUAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Manuel ödül okuma hatası: {e}")
        return []


def load_archived_awards():
    """Mevcut oduller.json içindeki 2025 sonrası kayıtları arşiv/yedek olarak korur."""
    if not os.path.exists(OUTPUT_FILE):
        return []
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
        return [a for a in existing if (a.get("bitis") or "") >= "2025-01-01"]
    except Exception:
        return []


def main():
    archived = load_archived_awards()
    fetched = fetch_tubitak_odul_portal() + fetch_tuseb_awards()
    for source in AWARD_SOURCES:
        if source.get("hub"):
            fetched.extend(fetch_hub_awards(source))
        else:
            fetched.extend(fetch_award_source(source))

    manual = load_manual_awards()

    merged = {}
    for item in archived + fetched + manual:
        merged[item["id"]] = item

    final_list = list(merged.values())
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"Toplam {len(final_list)} akademik ödül {OUTPUT_FILE} dosyasına kaydedildi.")


if __name__ == "__main__":
    main()

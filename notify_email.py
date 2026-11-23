import json
import os
import smtplib
import subprocess
from datetime import datetime
from email.message import EmailMessage

FILES = [
    ("cagrilar.json", "Yeni Proje Çağrıları"),
    ("oduller.json", "Yeni Akademik Ödüller"),
]


def load_json_from_git_head(filename):
    """Bir önceki commit'teki (dünkü) JSON kaydını okur."""
    try:
        res = subprocess.run(
            ["git", "show", f"HEAD:{filename}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return json.loads(res.stdout)
    except Exception:
        return []


def load_json_from_disk(filename):
    """Yeni taranmış güncel JSON dosyasını okur."""
    if not os.path.exists(filename):
        return []
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def find_new_items(filename):
    old_items = load_json_from_git_head(filename)
    new_items = load_json_from_disk(filename)

    # Dosya ilk kez oluşuyorsa toplu mail atmamak için boş dön
    if not old_items:
        return []

    old_ids = {item.get("id") for item in old_items if item.get("id")}
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    added = []
    for item in new_items:
        item_id = item.get("id")
        if not item_id or item_id in old_ids:
            continue

        # Geçmiş tarihli arşiv kayıtları yanlışlıkla bildirim tetiklemesin
        is_always_open = bool(item.get("surekli_acik"))
        bitis = item.get("bitis") or ""
        if not is_always_open and bitis and bitis < today_str:
            continue

        added.append(item)

    return added


def build_email_content(sections):
    plain_lines = ["PGKO Takip Sisteminde yeni çağrı/ödül tespit edildi:\n"]
    html_parts = [
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#1f2937;'>",
        "<h2 style='color:#111827;'>PGKO – Yeni Çağrı ve Ödül Bildirimi</h2>",
    ]

    for section_title, items in sections:
        plain_lines.append(f"=== {section_title} ({len(items)}) ===")
        html_parts.append(f"<h3 style='color:#1d4ed8;margin-top:20px;'>{section_title} ({len(items)})</h3><ul>")

        for item in items:
            kurum = item.get("kurum", "")
            baslik = item.get("baslik", "İsimsiz")
            program = item.get("program_adi", "")
            url = item.get("url", "#")
            tarih = (
                "Sürekli Açık"
                if item.get("surekli_acik")
                else f"{item.get('baslangic', '-')} → {item.get('bitis', '-')}"
            )

            plain_lines.append(f"- [{kurum}] {baslik} ({tarih})\n  {url}")
            program_html = f"<br><small style='color:#4b5563;'>{program}</small>" if program and program != baslik else ""
            html_parts.append(
                f"<li style='margin-bottom:10px;'>"
                f"<strong>[{kurum}]</strong> <a href='{url}' target='_blank'>{baslik}</a>"
                f"{program_html}"
                f"<br><span style='font-size:12px;color:#6b7280;'>Tarih: {tarih}</span>"
                f"</li>"
            )

        plain_lines.append("")
        html_parts.append("</ul>")

    html_parts.append("</body></html>")
    return "\n".join(plain_lines), "".join(html_parts)


def main():
    sections = []
    total_new = 0

    for filename, label in FILES:
        new_items = find_new_items(filename)
        if new_items:
            sections.append((label, new_items))
            total_new += len(new_items)

    if total_new == 0:
        print("Yeni çağrı veya ödül yok, e-posta gönderilmedi.")
        return

    mail_user = os.environ.get("MAIL_USER")
    mail_pass = os.environ.get("MAIL_PASS")
    mail_to = os.environ.get("MAIL_TO")

    if not all([mail_user, mail_pass, mail_to]):
        print("Uyarı: MAIL_USER, MAIL_PASS veya MAIL_TO tanımlı değil; e-posta atlandı.")
        return

    recipients = [addr.strip() for addr in mail_to.split(",") if addr.strip()]
    plain_body, html_body = build_email_content(sections)

    msg = EmailMessage()
    msg["Subject"] = f"PGKO Bildirim: {total_new} Yeni Çağrı / Ödül Açıldı"
    msg["From"] = mail_user
    msg["To"] = ", ".join(recipients)
    msg.set_content(plain_body)
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(mail_user, mail_pass)
        smtp.send_message(msg)

    print(f"Toplam {total_new} yeni kayıt için bilgilendirme e-postası gönderildi.")


if __name__ == "__main__":
    main()

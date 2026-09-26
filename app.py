"""Bilingual website for Harith Firas — Mosul tourism and travel services.

All page content is stored in ``data/content.json`` and edited from the
dashboard at ``/admin`` (see admin.py). ``seed_content.json`` holds the
original content used to create the data file on first run.
"""

from __future__ import annotations

import os
import re
from datetime import timedelta
from urllib.parse import quote

from flask import Flask, jsonify, render_template, url_for

import store
from admin import bp as admin_bp

app = Flask(__name__)
app.config.update(
    SECRET_KEY=store.secret_key(),
    MAX_CONTENT_LENGTH=200 * 1024 * 1024,
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
app.register_blueprint(admin_bp)


def whatsapp(number: str, message: str = "") -> str:
    """Create a WhatsApp deep link with a pre-filled message."""
    digits = re.sub(r"\D", "", number or "")
    link = "https://wa.me/%s" % digits
    return link + ("?text=" + quote(message) if message else "")


@app.template_global()
def media(path: str) -> str:
    """URL for an image stored as a path under static/ (or a full URL)."""
    if not path:
        return ""
    if path.startswith(("http://", "https://")):
        return path
    return url_for("static", filename=path)


@app.template_global()
def pairs(ar_list, en_list):
    """Zip Arabic/English lists, tolerating different lengths."""
    ar_list, en_list = ar_list or [], en_list or []
    return [(ar_list[i] if i < len(ar_list) else en_list[i], en_list[i] if i < len(en_list) else ar_list[i])
            for i in range(max(len(ar_list), len(en_list)))]


def prepare(content: dict) -> dict:
    s = content["settings"]
    for item in content["services"] + content["hotels"] + [content["trip"]]:
        item["wa_ar"] = whatsapp(item.get("whatsapp", ""), item.get("wa_message_ar", ""))
        item["wa_en"] = whatsapp(item.get("whatsapp", ""), item.get("wa_message_en", ""))
    content["links"] = {
        "header_ar": whatsapp(s["header_whatsapp"], s["header_wa_message_ar"]),
        "header_en": whatsapp(s["header_whatsapp"], s["header_wa_message_en"]),
        "floating_ar": whatsapp(s["header_whatsapp"], s["floating_wa_message_ar"]),
        "floating_en": whatsapp(s["header_whatsapp"], s["floating_wa_message_en"]),
        "contact_ar": whatsapp(s["contact_whatsapp"], s["contact_wa_message_ar"]),
        "contact_en": whatsapp(s["contact_whatsapp"], s["contact_wa_message_en"]),
    }
    customs = {"custom:" + item["id"]: item for item in content["custom_sections"]}
    blocks = []
    for key in content["layout"]:
        if key in customs:
            if customs[key].get("visible", True):
                blocks.append({"type": "custom", "anchor": "section-" + customs[key]["id"], "data": customs[key]})
        elif key in content["sections"] and content["sections"][key].get("visible", True):
            blocks.append({"type": key, "anchor": key, "data": content["sections"][key]})
    for number, block in enumerate(blocks, 1):
        block["number"] = "%02d" % number
    content["blocks"] = blocks
    content["nav"] = [block for block in blocks if block["data"].get("in_nav")]
    return content


@app.get("/")
def home():
    return render_template("index.html", c=prepare(store.load_content()))


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=port, debug=debug)

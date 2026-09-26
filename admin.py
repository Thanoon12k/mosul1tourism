"""Password-protected dashboard for editing every part of the website."""

from __future__ import annotations

import io
import json
import os
import secrets
import time
from datetime import datetime
from functools import wraps

from flask import (
    Blueprint, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for,
)
from werkzeug.utils import secure_filename

import store

bp = Blueprint("admin", __name__, url_prefix="/admin")

STATIC_DIR = os.path.join(store.HERE, "static")
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "avif", "jfif", "bmp"}


# ----- field schema ------------------------------------------------------------

def F(name, label, kind="text", help="", **extra):
    """Describe one form field. ``i18n*`` kinds store ``name_ar`` and ``name_en``."""
    return {"name": name, "label": label, "kind": kind, "help": help, **extra}


def G(title, *fields):
    return {"title": title, "fields": list(fields)}


WA_HELP = "International format, digits only, e.g. 9647726443352"

SETTINGS_GROUPS = [
    G("Brand & SEO",
      F("brand_name", "Brand name", "i18n"),
      F("brand_tagline", "Tagline", "i18n"),
      F("logo_image", "Logo / profile picture (also the browser icon)", "image"),
      F("site_title", "Browser tab title", "i18n"),
      F("meta_description", "Search engine description", "i18n_area"),
      F("share_image", "Social sharing image", "image"),
      F("default_language", "Default language", "select", options=[("en", "English"), ("ar", "العربية")])),
    G("Header & floating WhatsApp",
      F("header_button", "Header button text", "i18n"),
      F("header_whatsapp", "Header WhatsApp number", help=WA_HELP),
      F("header_wa_message", "Header WhatsApp message", "i18n_area"),
      F("floating_whatsapp", "Show floating WhatsApp button", "bool"),
      F("floating_wa_message", "Floating button WhatsApp message", "i18n_area")),
    G("Hero (top banner)",
      F("hero_image", "Background image", "image"),
      F("hero_eyebrow", "Small line above the title", "i18n"),
      F("hero_title1", "Title — line 1", "i18n"),
      F("hero_title2", "Title — line 2 (highlighted)", "i18n"),
      F("hero_lead", "Intro paragraph", "i18n_area"),
      F("hero_button1", "Button 1 text", "i18n"),
      F("hero_button1_link", "Button 1 link", help="e.g. #landmarks or a full URL"),
      F("hero_button2", "Button 2 text", "i18n"),
      F("hero_button2_link", "Button 2 link"),
      F("hero_scroll", "Scroll hint text", "i18n")),
    G("Footer",
      F("footer_owner", "Copyright owner"),
      F("footer_location", "Location line", "i18n"),
      F("footer_rights", "Rights text", "i18n"),
      F("show_credits", "Show landmark image credits", "bool"),
      F("footer_credits", "Credits heading", "i18n")),
]

ABOUT_FIELDS = [
    F("about_cover", "Cover image", "image"),
    F("about_portrait", "Portrait image", "image"),
    F("about_signature", "Signature name"),
    F("about_role", "Role under signature", "i18n"),
]
CONTACT_FIELDS = [
    F("contact_button", "Button text", "i18n"),
    F("contact_whatsapp", "WhatsApp number", help=WA_HELP),
    F("contact_wa_message", "WhatsApp message", "i18n_area"),
    F("contact_phone", "Phone shown on page"),
    F("contact_email", "Email"),
]

SECTION_FIELDS = [
    F("visible", "Show this section", "bool"),
    F("in_nav", "Show in top menu", "bool"),
    F("nav", "Menu label", "i18n"),
    F("label", "Small label above the title", "i18n"),
    F("title", "Title", "i18n"),
    F("intro", "Intro text", "i18n_area"),
]
HOTELS_SECTION_EXTRA = [F("note", "Note under the hotels", "i18n_area")]

TRIP_FIELDS = [
    F("image", "Poster image", "image"),
    F("images", "More photos of this trip", "images"),
    F("caption", "Poster caption", "i18n"),
    F("status", "Status line", "i18n"),
    F("date", "Date line", "i18n"),
    F("detail1_value", "Detail 1 — number"),
    F("detail1", "Detail 1 — text", "i18n"),
    F("detail2_value", "Detail 2 — number"),
    F("detail2", "Detail 2 — text", "i18n"),
    F("bullets", "Bullet points (one per line)", "i18n_lines"),
    F("button", "Button text", "i18n"),
    F("whatsapp", "WhatsApp number", help=WA_HELP),
    F("wa_message", "WhatsApp message", "i18n_area"),
    F("note", "Small note under the button", "i18n"),
]

COLLECTIONS = {
    "services": {
        "label": "Services", "singular": "service", "title": "title", "image": "image",
        "fields": [
            F("title", "Title", "i18n"),
            F("image", "Main image", "image"),
            F("images", "More photos", "images"),
            F("summary", "Summary", "i18n_area"),
            F("features", "Features (one per line)", "i18n_lines"),
            F("phone", "Phone shown"),
            F("secondary_phone", "Second phone (optional)"),
            F("button", "Button text", "i18n"),
            F("link_url", "Button link (optional)", help="Leave empty to open WhatsApp, or e.g. #hotels"),
            F("whatsapp", "WhatsApp number", help=WA_HELP),
            F("wa_message", "WhatsApp message", "i18n_area"),
        ],
    },
    "hotels": {
        "label": "Hotels", "singular": "hotel", "title": "name", "image": "image",
        "fields": [
            F("name", "Hotel name", "i18n"),
            F("image", "Main image", "image"),
            F("images", "More photos (rooms, lobby…)", "images"),
            F("stars", "Stars (0–5)", "number", min=0, max=5),
            F("rating", "Category line", "i18n"),
            F("location", "Location", "i18n"),
            F("rate", "Approximate price", "i18n"),
            F("summary", "Description", "i18n_area"),
            F("amenities", "Amenities (one per line)", "i18n_lines"),
            F("source", "Hotel details link", "url"),
            F("whatsapp", "Booking WhatsApp number", help=WA_HELP),
            F("wa_message", "Booking WhatsApp message", "i18n_area"),
        ],
    },
    "landmarks": {
        "label": "Landmarks", "singular": "landmark", "title": "title", "image": "image",
        "fields": [
            F("title", "Title", "i18n"),
            F("image", "Main image", "image"),
            F("images", "More photos", "images"),
            F("kicker", "Small line above the title", "i18n"),
            F("description", "Description", "i18n_area"),
            F("credit", "Image credit"),
            F("source", "Image source link", "url"),
        ],
    },
    "gallery": {
        "label": "Gallery photos", "singular": "photo", "title": "alt", "image": "image",
        "fields": [
            F("image", "Photo", "image"),
            F("alt", "Caption", "i18n"),
            F("category", "Filter tags", datalist="filter-keys", help="Space separated keys from Gallery filters, e.g. iraq guests"),
        ],
    },
    "custom_sections": {
        "label": "Custom sections", "singular": "section", "title": "title", "image": "image",
        "fields": [
            F("visible", "Show this section", "bool"),
            F("style", "Style", "select", options=[("light", "Light"), ("dark", "Dark blue"), ("gold", "Gold")]),
            F("in_nav", "Show in top menu", "bool"),
            F("nav", "Menu label", "i18n"),
            F("label", "Small label above the title", "i18n"),
            F("title", "Title", "i18n"),
            F("body", "Text", "i18n_area"),
            F("image", "Main image (optional)", "image"),
            F("images", "Photo grid (bulk upload)", "images"),
            F("button", "Button text (optional)", "i18n"),
            F("button_link", "Button link", help="URL, #anchor or https://wa.me/964…"),
        ],
    },
    "hero_facts": {
        "label": "Hero facts", "singular": "fact", "title": "label",
        "fields": [F("value", "Big value"), F("label", "Label", "i18n")],
    },
    "gallery_filters": {
        "label": "Gallery filters", "singular": "filter", "title": "label",
        "fields": [F("key", "Tag key", help="Lowercase word used in photo tags, e.g. iraq"), F("label", "Button label", "i18n")],
    },
    "social_links": {
        "label": "Social links", "singular": "link", "title": "label",
        "fields": [F("label", "Name"), F("url", "Link", "url")],
    },
}

BUILTIN_SECTIONS = {
    "trip": "Latest trip", "services": "Services", "landmarks": "Landmarks", "hotels": "Hotels",
    "gallery": "Gallery", "about": "About", "contact": "Contact",
}


# ----- helpers -----------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


@bp.before_request
def check_csrf():
    if request.method == "POST":
        token = request.form.get("_csrf", "")
        if not token or not secrets.compare_digest(token, session.get("csrf", "")):
            abort(400, "Form expired — go back, refresh the page and try again.")


@bp.app_context_processor
def inject_admin_helpers():
    return {"csrf_token": csrf_token, "COLLECTIONS": COLLECTIONS, "BUILTIN_SECTIONS": BUILTIN_SECTIONS}


def is_image(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in IMAGE_EXTENSIONS


def save_upload(file) -> str | None:
    """Store an uploaded image under static/uploads and return its static path."""
    if not file or not file.filename or not is_image(file.filename):
        return None
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    base = secure_filename(file.filename) or "image"
    stem, ext = os.path.splitext(base)
    if not stem or stem == ext:
        stem = "image"
    name = "%s-%s-%s%s" % (datetime.now().strftime("%Y%m%d"), secrets.token_hex(3), stem[:50], ext.lower())
    file.save(os.path.join(UPLOAD_DIR, name))
    return "uploads/" + name


def clean_path(value: str) -> str:
    value = (value or "").strip()
    if value.startswith(("http://", "https://")):
        return value
    value = value.lstrip("/")
    if value.startswith("static/"):
        value = value[len("static/"):]
    if ".." in value.split("/"):
        return ""
    return value


def title_from_filename(filename: str) -> str:
    stem = os.path.splitext(os.path.basename(filename))[0]
    return stem.replace("-", " ").replace("_", " ").strip()


def parse_fields(fields: list[dict], target: dict, prefix: str = "") -> None:
    form, files = request.form, request.files
    for field in fields:
        name, kind = prefix + field["name"], field["kind"]
        key = field["name"]
        if kind.startswith("i18n"):
            for lang in ("ar", "en"):
                raw = form.get("%s_%s" % (name, lang), "")
                if kind == "i18n_lines":
                    target["%s_%s" % (key, lang)] = [line.strip() for line in raw.splitlines() if line.strip()]
                elif kind == "i18n_area":
                    target["%s_%s" % (key, lang)] = raw.replace("\r\n", "\n").strip("\n")
                else:
                    target["%s_%s" % (key, lang)] = raw.strip()
        elif kind == "bool":
            target[key] = name in form
        elif kind == "number":
            try:
                number = int(form.get(name, "0"))
            except ValueError:
                number = 0
            target[key] = max(field.get("min", number), min(field.get("max", number), number))
        elif kind == "lines":
            target[key] = [line.strip() for line in form.get(name, "").splitlines() if line.strip()]
        elif kind == "image":
            uploaded = save_upload(files.get(name + "__file"))
            target[key] = uploaded or clean_path(form.get(name, ""))
        elif kind == "images":
            kept = [clean_path(path) for path in form.getlist(name + "__keep")]
            uploaded = [path for path in (save_upload(f) for f in files.getlist(name + "__files")) if path]
            target[key] = [path for path in kept + uploaded if path]
        elif kind == "textarea":
            target[key] = form.get(name, "").replace("\r\n", "\n").strip("\n")
        else:
            target[key] = form.get(name, "").strip()


def blank_item(fields: list[dict]) -> dict:
    item = {}
    for field in fields:
        kind, key = field["kind"], field["name"]
        if kind.startswith("i18n"):
            for lang in ("_ar", "_en"):
                item[key + lang] = [] if kind == "i18n_lines" else ""
        elif kind == "bool":
            item[key] = True
        elif kind == "number":
            item[key] = 0
        elif kind in ("lines", "images"):
            item[key] = []
        elif kind == "select":
            item[key] = field["options"][0][0]
        else:
            item[key] = ""
    return item


def item_title(coll: str, item: dict) -> str:
    base = COLLECTIONS[coll]["title"]
    return item.get(base + "_en") or item.get(base + "_ar") or item.get(base) or "(untitled)"


def media_files() -> list[dict]:
    """Every image under static/, newest uploads first."""
    found = []
    for folder in ("uploads", "images"):
        root = os.path.join(STATIC_DIR, folder)
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if not is_image(filename):
                    continue
                full = os.path.join(dirpath, filename)
                rel = os.path.relpath(full, STATIC_DIR).replace(os.sep, "/")
                found.append({"path": rel, "size": os.path.getsize(full), "mtime": os.path.getmtime(full),
                              "deletable": rel.startswith("uploads/")})
    found.sort(key=lambda entry: (not entry["deletable"], -entry["mtime"]))
    return found


# ----- auth --------------------------------------------------------------------

_failures: dict[str, list[float]] = {}


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = request.headers.get("X-Real-IP") or request.remote_addr or "?"
        recent = [stamp for stamp in _failures.get(ip, []) if time.time() - stamp < 900]
        if len(recent) >= 10:
            flash("Too many attempts. Try again in 15 minutes.", "error")
            return render_template("admin/login.html"), 429
        username = request.form.get("username", "").strip()
        if store.verify_user(username, request.form.get("password", "")):
            session.clear()
            session.permanent = True
            session["user"] = username
            target = request.args.get("next", "")
            return redirect(target if target.startswith("/admin") else url_for("admin.dashboard"))
        _failures[ip] = recent + [time.time()]
        flash("Wrong username or password.", "error")
    return render_template("admin/login.html")


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


# ----- dashboard ---------------------------------------------------------------

@bp.get("/")
@login_required
def dashboard():
    content = store.load_content()
    counts = {name: len(content.get(name, [])) for name in COLLECTIONS}
    return render_template("admin/dashboard.html", content=content, counts=counts,
                           media_count=len(media_files()))


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    content = store.load_content()
    if request.method == "POST":
        for group in SETTINGS_GROUPS:
            parse_fields(group["fields"], content["settings"])
        store.save_content(content)
        flash("Site settings saved.", "ok")
        return redirect(url_for("admin.settings"))
    return render_template("admin/settings.html", groups=SETTINGS_GROUPS, data=content["settings"])


# ----- sections ----------------------------------------------------------------

def section_blocks(key: str, content: dict) -> list[dict]:
    """Groups of (fields, data, prefix) that make up one section's edit page."""
    blocks = [{"title": "Heading & visibility", "fields": SECTION_FIELDS + (HOTELS_SECTION_EXTRA if key == "hotels" else []),
               "data": content["sections"][key], "prefix": "sec__"}]
    if key == "trip":
        blocks.append({"title": "Trip details", "fields": TRIP_FIELDS, "data": content["trip"], "prefix": "trip__"})
    elif key == "about":
        blocks.append({"title": "About images & signature", "fields": ABOUT_FIELDS, "data": content["settings"], "prefix": "set__"})
    elif key == "contact":
        blocks.append({"title": "Contact details", "fields": CONTACT_FIELDS, "data": content["settings"], "prefix": "set__"})
    return blocks


@bp.route("/sections", methods=["GET", "POST"])
@login_required
def sections():
    content = store.load_content()
    if request.method == "POST":
        key, action = request.form.get("key", ""), request.form.get("action", "")
        layout = content["layout"]
        if key in layout:
            index = layout.index(key)
            if action == "up" and index > 0:
                layout[index - 1], layout[index] = layout[index], layout[index - 1]
            elif action == "down" and index < len(layout) - 1:
                layout[index + 1], layout[index] = layout[index], layout[index + 1]
            elif action == "toggle":
                if key.startswith("custom:"):
                    for item in content["custom_sections"]:
                        if "custom:" + item["id"] == key:
                            item["visible"] = not item.get("visible", True)
                else:
                    content["sections"][key]["visible"] = not content["sections"][key].get("visible", True)
            store.save_content(content)
        return redirect(url_for("admin.sections"))
    customs = {"custom:" + item["id"]: item for item in content["custom_sections"]}
    rows = []
    for key in content["layout"]:
        if key in customs:
            item = customs[key]
            rows.append({"key": key, "name": item_title("custom_sections", item), "custom": True, "id": item["id"],
                         "visible": item.get("visible", True)})
        elif key in BUILTIN_SECTIONS:
            rows.append({"key": key, "name": BUILTIN_SECTIONS[key], "custom": False,
                         "title": content["sections"][key].get("title_en", ""),
                         "visible": content["sections"][key].get("visible", True)})
    return render_template("admin/sections.html", rows=rows)


@bp.route("/sections/<key>", methods=["GET", "POST"])
@login_required
def section_edit(key):
    if key not in BUILTIN_SECTIONS:
        abort(404)
    content = store.load_content()
    blocks = section_blocks(key, content)
    if request.method == "POST":
        for block in blocks:
            parse_fields(block["fields"], block["data"], block["prefix"])
        store.save_content(content)
        flash("%s section saved." % BUILTIN_SECTIONS[key], "ok")
        return redirect(url_for("admin.section_edit", key=key))
    related = {"services": "services", "landmarks": "landmarks", "hotels": "hotels", "gallery": "gallery",
               "about": "social_links"}.get(key)
    return render_template("admin/section_edit.html", key=key, name=BUILTIN_SECTIONS[key], blocks=blocks,
                           related=related)


# ----- collections -------------------------------------------------------------

def get_collection(coll: str):
    if coll not in COLLECTIONS:
        abort(404)
    return COLLECTIONS[coll]


@bp.get("/c/<coll>")
@login_required
def collection(coll):
    schema = get_collection(coll)
    content = store.load_content()
    items = content.get(coll, [])
    return render_template("admin/collection.html", coll=coll, schema=schema, items=items,
                           titles=[item_title(coll, item) for item in items],
                           filters=content.get("gallery_filters", []))


@bp.route("/c/<coll>/new", methods=["GET", "POST"])
@bp.route("/c/<coll>/<item_id>", methods=["GET", "POST"])
@login_required
def item_edit(coll, item_id=None):
    schema = get_collection(coll)
    content = store.load_content()
    items = content.setdefault(coll, [])
    if item_id:
        item = next((entry for entry in items if entry.get("id") == item_id), None)
        if item is None:
            abort(404)
    else:
        item = blank_item(schema["fields"])
    if request.method == "POST":
        parse_fields(schema["fields"], item)
        if not item_id:
            item["id"] = store.new_id()
            items.append(item)
            if coll == "custom_sections":
                layout = content["layout"]
                position = layout.index("about") if "about" in layout else len(layout)
                layout.insert(position, "custom:" + item["id"])
        store.save_content(content)
        flash("%s saved." % schema["singular"].capitalize(), "ok")
        if request.form.get("then") == "new":
            return redirect(url_for("admin.item_edit", coll=coll))
        return redirect(url_for("admin.item_edit", coll=coll, item_id=item["id"]))
    return render_template("admin/item_edit.html", coll=coll, schema=schema, item=item, is_new=not item_id,
                           filters=content.get("gallery_filters", []))


@bp.post("/c/<coll>/<item_id>/action")
@login_required
def item_action(coll, item_id):
    get_collection(coll)
    content = store.load_content()
    items = content.get(coll, [])
    index = next((i for i, entry in enumerate(items) if entry.get("id") == item_id), None)
    if index is None:
        abort(404)
    action = request.form.get("action")
    if action == "delete":
        items.pop(index)
        if coll == "custom_sections":
            content["layout"] = [key for key in content["layout"] if key != "custom:" + item_id]
        flash("Deleted.", "ok")
    elif action == "up" and index > 0:
        items[index - 1], items[index] = items[index], items[index - 1]
    elif action == "down" and index < len(items) - 1:
        items[index + 1], items[index] = items[index], items[index + 1]
    elif action == "top":
        items.insert(0, items.pop(index))
    elif action == "duplicate":
        clone = json.loads(json.dumps(items[index]))
        clone["id"] = store.new_id()
        items.insert(index + 1, clone)
        if coll == "custom_sections":
            layout = content["layout"]
            layout.insert(layout.index("custom:" + item_id) + 1, "custom:" + clone["id"])
        flash("Duplicated.", "ok")
    store.save_content(content)
    return redirect(url_for("admin.collection", coll=coll) + "#item-" + item_id)


@bp.post("/c/<coll>/bulk")
@login_required
def bulk_upload(coll):
    """Create one new item per uploaded image (e.g. many gallery photos at once)."""
    schema = get_collection(coll)
    if not schema.get("image"):
        abort(400)
    content = store.load_content()
    items = content.setdefault(coll, [])
    category = request.form.get("category", "").strip()
    added = 0
    new_items = []
    for file in request.files.getlist("files"):
        path = save_upload(file)
        if not path:
            continue
        item = blank_item(schema["fields"])
        item["id"] = store.new_id()
        item[schema["image"]] = path
        title = title_from_filename(file.filename)
        item[schema["title"] + "_ar"] = item[schema["title"] + "_en"] = title
        if coll == "gallery":
            item["category"] = category
        if coll == "custom_sections":
            content["layout"].insert(content["layout"].index("about") if "about" in content["layout"]
                                     else len(content["layout"]), "custom:" + item["id"])
        new_items.append(item)
        added += 1
    if request.form.get("position") == "end":
        items.extend(new_items)
    else:
        items[:0] = new_items
    store.save_content(content)
    flash("Added %d item(s). Click each one to write its captions." % added if added
          else "No images were uploaded (allowed: %s)." % ", ".join(sorted(IMAGE_EXTENSIONS)),
          "ok" if added else "error")
    return redirect(url_for("admin.collection", coll=coll))


@bp.post("/c/gallery/bulk-edit")
@login_required
def gallery_bulk_edit():
    """Edit captions and tags of all gallery photos on one page."""
    content = store.load_content()
    selected = set(request.form.getlist("selected"))
    delete = request.form.get("action") == "delete_selected"
    kept = []
    for item in content["gallery"]:
        prefix = "g_%s_" % item["id"]
        if delete and item["id"] in selected:
            continue
        if prefix + "alt_ar" in request.form:
            item["alt_ar"] = request.form.get(prefix + "alt_ar", "").strip()
            item["alt_en"] = request.form.get(prefix + "alt_en", "").strip()
            item["category"] = request.form.get(prefix + "category", "").strip()
        kept.append(item)
    removed = len(content["gallery"]) - len(kept)
    content["gallery"] = kept
    store.save_content(content)
    flash("Deleted %d photo(s)." % removed if delete else "Gallery captions saved.", "ok")
    return redirect(url_for("admin.collection", coll="gallery"))


# ----- media library -----------------------------------------------------------

@bp.route("/media", methods=["GET", "POST"])
@login_required
def media():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "upload":
            saved = [path for path in (save_upload(f) for f in request.files.getlist("files")) if path]
            flash("Uploaded %d image(s)." % len(saved), "ok" if saved else "error")
        elif action == "delete":
            path = clean_path(request.form.get("path", ""))
            used = json.dumps(store.load_content(), ensure_ascii=False)
            full = os.path.join(STATIC_DIR, path)
            if not path.startswith("uploads/") or not os.path.isfile(full):
                flash("Only uploaded images can be deleted.", "error")
            elif '"%s"' % path in used:
                flash("This image is still used on the site. Remove it from the page first.", "error")
            else:
                os.remove(full)
                flash("Image deleted.", "ok")
        return redirect(url_for("admin.media"))
    used = json.dumps(store.load_content(), ensure_ascii=False)
    files = media_files()
    for entry in files:
        entry["used"] = '"%s"' % entry["path"] in used
    return render_template("admin/media.html", files=files)


@bp.get("/media.json")
@login_required
def media_json():
    return jsonify([{"path": entry["path"], "url": url_for("static", filename=entry["path"])} for entry in media_files()])


# ----- users -------------------------------------------------------------------

@bp.route("/users", methods=["GET", "POST"])
@login_required
def users():
    if request.method == "POST":
        action = request.form.get("action")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        existing = [user["username"] for user in store.load_users()]
        if action == "save":
            if not username or not password:
                flash("Username and password are required.", "error")
            elif password != request.form.get("confirm", ""):
                flash("Passwords do not match.", "error")
            else:
                store.set_password(username, password)
                flash(("Password changed for %s." if username in existing else "User %s added.") % username, "ok")
        elif action == "delete":
            if len(existing) <= 1:
                flash("You cannot delete the last user.", "error")
            elif username == session.get("user"):
                flash("You cannot delete yourself while logged in.", "error")
            else:
                store.delete_user(username)
                flash("User %s deleted." % username, "ok")
        return redirect(url_for("admin.users"))
    return render_template("admin/users.html", users=store.load_users())


# ----- backup ------------------------------------------------------------------

@bp.route("/backup", methods=["GET", "POST"])
@login_required
def backup():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "restore":
            file = request.files.get("file")
            try:
                data = json.load(file)
                if not isinstance(data, dict) or "settings" not in data:
                    raise ValueError
            except Exception:
                flash("That file is not a valid site backup.", "error")
            else:
                store.save_content(data)
                flash("Backup restored.", "ok")
        elif action == "reset" and request.form.get("confirm") == "RESET":
            store.reset_content()
            flash("All content reset to the original defaults.", "ok")
        else:
            flash("Type RESET to confirm.", "error")
        return redirect(url_for("admin.backup"))
    return render_template("admin/backup.html")


@bp.get("/backup/download")
@login_required
def backup_download():
    data = json.dumps(store.load_content(), ensure_ascii=False, indent=2).encode("utf-8")
    name = "site-content-%s.json" % datetime.now().strftime("%Y%m%d-%H%M")
    return send_file(io.BytesIO(data), mimetype="application/json", as_attachment=True, download_name=name)

from __future__ import annotations

import cgi
import html
import io
import mimetypes
import os
import re
import secrets
from http import cookies
from pathlib import Path
from urllib.parse import parse_qs

from .defaults import PAGE_DEFINITIONS
from .generator import generate_all_pages, generate_page
from .importer import import_existing_site
from .storage import (
    authenticate,
    create_session,
    delete_session,
    get_page,
    get_session_user,
    initialize_database,
    list_pages,
    save_page,
)

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "assets" / "uploads"
SESSION_COOKIE = "ybm_cms_session"


def h(value: str) -> str:
    return html.escape(value, quote=True)


def slug_label(value: str) -> str:
    return value.replace("_", " ").replace(".", " / ").title()


DAY_SEQUENCE = [
    ("monday", "Lunes"),
    ("tuesday", "Martes"),
    ("wednesday", "Miércoles"),
    ("thursday", "Jueves"),
    ("friday", "Viernes"),
    ("saturday", "Sábado"),
    ("sunday", "Domingo"),
]

DAY_NAME_TO_KEY = {
    "lunes": "monday",
    "martes": "tuesday",
    "miercoles": "wednesday",
    "miércoles": "wednesday",
    "jueves": "thursday",
    "viernes": "friday",
    "sabado": "saturday",
    "sábado": "saturday",
    "domingo": "sunday",
}


def schedule_day_value(day: dict) -> str:
    if day.get("closed"):
        return "Cerrado"
    if day.get("afternoon_open") and day.get("afternoon_close"):
        return f"{day['morning_open']}-{day['morning_close']} / {day['afternoon_open']}-{day['afternoon_close']}h"
    return f"{day['morning_open']}-{day['morning_close']}h"


def build_schedule_summary(schedule: dict) -> str:
    lines = []
    start_key, start_label = DAY_SEQUENCE[0]
    current_value = schedule_day_value(schedule[start_key])
    current_start = start_label
    current_end = start_label

    for key, label in DAY_SEQUENCE[1:]:
        value = schedule_day_value(schedule[key])
        if value == current_value:
            current_end = label
            continue
        day_range = current_start if current_start == current_end else f"{current_start} - {current_end}"
        lines.append(f"{day_range}: {current_value}")
        current_start = label
        current_end = label
        current_value = value

    day_range = current_start if current_start == current_end else f"{current_start} - {current_end}"
    lines.append(f"{day_range}: {current_value}")
    return "\n".join(lines)


def normalize_day_name(value: str) -> str:
    return value.strip().lower().replace(".", "")


def parse_time_range(value: str) -> tuple[str, str, str, str, bool]:
    raw = value.strip().lower().rstrip(".")
    if raw in {"cerrado", "closed"}:
        return "", "", "", "", True

    cleaned = raw.replace(" ", "").replace("–", "-").replace("—", "-").replace("a", "-")
    cleaned = cleaned.replace("h", "")
    parts = [part for part in cleaned.split("/") if part]

    def split_range(chunk: str) -> tuple[str, str]:
        start, end = [item.strip() for item in chunk.split("-", 1)]
        return start, end

    morning_open, morning_close = split_range(parts[0])
    afternoon_open = ""
    afternoon_close = ""

    if len(parts) > 1:
        afternoon_open, afternoon_close = split_range(parts[1])

    return morning_open, morning_close, afternoon_open, afternoon_close, False


def apply_schedule_summary(schedule: dict, summary: str) -> None:
    for line in [item.strip() for item in summary.splitlines() if item.strip()]:
        if ":" not in line:
            continue
        day_part, value_part = [item.strip() for item in line.split(":", 1)]
        day_names = [item.strip() for item in day_part.split("-")]
        start_key = DAY_NAME_TO_KEY.get(normalize_day_name(day_names[0]))
        end_key = DAY_NAME_TO_KEY.get(normalize_day_name(day_names[-1]))
        if not start_key or not end_key:
            continue

        start_index = [key for key, _label in DAY_SEQUENCE].index(start_key)
        end_index = [key for key, _label in DAY_SEQUENCE].index(end_key)
        morning_open, morning_close, afternoon_open, afternoon_close, closed = parse_time_range(value_part)

        for day_key, label in DAY_SEQUENCE[start_index:end_index + 1]:
            schedule[day_key] = {
                "label": label,
                "closed": closed,
                "morning_open": morning_open,
                "morning_close": morning_close,
                "afternoon_open": afternoon_open,
                "afternoon_close": afternoon_close,
            }


def flatten_content(data, prefix=""):
    fields = []
    if isinstance(data, dict):
        for key, value in data.items():
            name = f"{prefix}.{key}" if prefix else key
            fields.extend(flatten_content(value, name))
        return fields
    if isinstance(data, list):
        for index, value in enumerate(data):
            name = f"{prefix}.{index}" if prefix else str(index)
            fields.extend(flatten_content(value, name))
        return fields
    fields.append((prefix, "" if data is None else str(data)))
    return fields


def set_nested(data, dotted_key: str, value: str):
    parts = dotted_key.split(".")
    cursor = data
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if part.isdigit():
            part_index = int(part)
            if last:
                cursor[part_index] = value
            else:
                cursor = cursor[part_index]
        else:
            if last:
                cursor[part] = value
            else:
                cursor = cursor[part]


def parse_post_data(environ):
    content_type = environ.get("CONTENT_TYPE", "")
    if content_type.startswith("multipart/form-data"):
        form = cgi.FieldStorage(fp=environ["wsgi.input"], environ=environ, keep_blank_values=True)
        text_fields = {}
        file_fields = {}
        for key in form.keys():
            field = form[key]
            if isinstance(field, list):
                field = field[0]
            if field.filename:
                file_fields[key] = field
            else:
                text_fields[key] = field.value
        return text_fields, file_fields

    length = int(environ.get("CONTENT_LENGTH", "0") or "0")
    raw = environ["wsgi.input"].read(length).decode("utf-8")
    parsed = parse_qs(raw, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}, {}


def save_uploaded_file(field_storage, slug: str, field_name: str) -> str | None:
    if not getattr(field_storage, "filename", ""):
        return None
    data = field_storage.file.read()
    if not data:
        return None

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(field_storage.filename).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ext = mimetypes.guess_extension(field_storage.type or "") or ".jpg"
    safe_field = re.sub(r"[^a-zA-Z0-9_-]+", "-", field_name)
    filename = f"{slug}-{safe_field}-{secrets.token_hex(4)}{ext}"
    target = UPLOAD_DIR / filename
    target.write_bytes(data)
    return f"/assets/uploads/{filename}"


def render_layout(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="es">
<head>
  <!-- Google Tag Manager -->
  <script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
  new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
  j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
  'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
  }})(window,document,'script','dataLayer','GTM-T68P3M9M');</script>
  <!-- End Google Tag Manager -->

  <!-- Google tag (gtag.js) -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-SNSXVJXFC6"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());

    gtag('config', 'G-SNSXVJXFC6');
  </script>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(title)}</title>
  <style>
    :root {{
      --bg: #f4f1ea;
      --panel: #fffdfa;
      --line: #d7cec0;
      --ink: #1a1a1a;
      --accent: #a53b16;
      --accent-2: #d26b34;
      --muted: #5f5a55;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Georgia, "Times New Roman", serif; background: linear-gradient(180deg, #efe7db 0%, #f7f4ef 100%); color: var(--ink); }}
    a {{ color: inherit; }}
    .shell {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 24px 0 40px; }}
    .top {{ display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 24px; }}
    .brand {{ font-size: 28px; font-weight: 700; text-decoration: none; }}
    .muted {{ color: var(--muted); }}
    .nav {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    .btn, button {{ border: 0; background: var(--accent); color: #fff; padding: 10px 16px; border-radius: 999px; cursor: pointer; text-decoration: none; font: inherit; }}
    .btn-secondary {{ background: #2d2d2d; }}
    .grid {{ display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: 20px; }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 22px; padding: 20px; box-shadow: 0 12px 40px rgba(80, 56, 20, 0.07); }}
    .menu a {{ display: block; padding: 12px 14px; margin-bottom: 8px; border-radius: 14px; text-decoration: none; border: 1px solid transparent; }}
    .menu a.active {{ background: #f7ede1; border-color: var(--line); }}
    .notice {{ padding: 12px 14px; border-radius: 14px; background: #e9f6ea; border: 1px solid #b8dbbb; margin-bottom: 16px; }}
    .warning {{ padding: 12px 14px; border-radius: 14px; background: #fff4df; border: 1px solid #f0c680; margin-bottom: 16px; }}
    form {{ display: grid; gap: 18px; }}
    fieldset {{ border: 1px solid var(--line); border-radius: 18px; padding: 16px; margin: 0; }}
    legend {{ padding: 0 8px; font-weight: 700; }}
    label {{ display: block; font-size: 14px; color: var(--muted); margin-bottom: 6px; }}
    input[type="text"], input[type="password"], textarea {{ width: 100%; border: 1px solid var(--line); border-radius: 12px; padding: 10px 12px; font: inherit; background: #fff; }}
    textarea {{ min-height: 110px; resize: vertical; }}
    .field {{ margin-bottom: 14px; }}
    .field small {{ display: block; color: var(--muted); margin-top: 6px; }}
    .row {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    .path {{ color: var(--muted); font-size: 14px; }}
    .preview {{ margin-top: 8px; }}
    .preview img {{ max-width: 220px; border-radius: 12px; border: 1px solid var(--line); display: block; }}
    .login {{ max-width: 420px; margin: 48px auto; }}
    @media (max-width: 900px) {{
      .grid, .row {{ grid-template-columns: 1fr; }}
      .top {{ flex-direction: column; align-items: flex-start; }}
    }}
  </style>
</head>
<body>
  <!-- Google Tag Manager (noscript) -->
  <noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-T68P3M9M"
  height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
  <!-- End Google Tag Manager (noscript) -->
{body}
</body>
</html>""".encode("utf-8")


def render_login(error: str = "") -> bytes:
    message = f'<div class="warning">{h(error)}</div>' if error else ""
    body = f"""
    <div class="shell">
      <div class="panel login">
        <h1>Mini CMS</h1>
        <p class="muted">Вход только для редактирования текста и фото сайта.</p>
        {message}
        <form method="post" action="/admin/login">
          <div class="field">
            <label for="username">Логин</label>
            <input id="username" name="username" type="text" value="admin" required>
          </div>
          <div class="field">
            <label for="password">Пароль</label>
            <input id="password" name="password" type="password" required>
          </div>
          <button type="submit">Войти</button>
        </form>
      </div>
    </div>
    """
    return render_layout("Mini CMS Login", body)


def render_admin(page_slug: str, notice: str = "") -> bytes:
    pages = list_pages()
    current_page = get_page(page_slug)
    content = current_page["content"]
    flat_fields = flatten_content(content)

    groups = []
    for name, value in flat_fields:
        if name.startswith("meta."):
            continue
        if page_slug == "site-settings" and name.startswith("schedule.") and name != "schedule.closed_note":
            continue
        field_html = render_field(name, value)
        groups.append(field_html)

    if page_slug == "site-settings" and "schedule" in content:
        groups.append(
            f"""
    <div class="field">
      <label>Schedule / Horario</label>
      <textarea name="schedule_summary">{h(build_schedule_summary(content["schedule"]))}</textarea>
      <small>Formato recomendado: Lunes - Jueves: 8:00-18:00h</small>
    </div>
    """
        )

    menu_items = []
    for page in pages:
        active = "active" if page["slug"] == page_slug else ""
        menu_items.append(
            f'<a class="{active}" href="/admin/page/{h(page["slug"])}">{h(page["title"])}</a>'
        )

    warn = ""
    if notice:
        warn = f'<div class="notice">{h(notice)}</div>'
    body = f"""
    <div class="shell">
      <div class="top">
        <a class="brand" href="/admin">Ybarra Mini CMS</a>
        <div class="nav">
          <a class="btn btn-secondary" href="/" target="_blank" rel="noopener">Открыть сайт</a>
          <a class="btn btn-secondary" href="/admin/logout">Выйти</a>
        </div>
      </div>
      {warn}
      <div class="grid">
        <aside class="panel menu">
          <h2>Страницы</h2>
          <p class="muted">Клиент сможет менять только содержимое.</p>
          {''.join(menu_items)}
        </aside>
        <main class="panel">
          <h1>{h(current_page['title'])}</h1>
          <p class="path">{h(current_page['path'])}</p>
          <form method="post" enctype="multipart/form-data" action="/admin/page/{h(page_slug)}">
            <input type="hidden" name="page_title" value="{h(current_page['title'])}">
            {''.join(groups)}
            <button type="submit">Сохранить и обновить сайт</button>
          </form>
        </main>
      </div>
    </div>
    """
    return render_layout("Ybarra Mini CMS", body)


def render_field(name: str, value: str) -> str:
    if name.endswith(".alt"):
        return ""
    label = slug_label(name)
    is_textarea = len(value) > 100 or name.endswith(".text") or name.endswith(".lead") or name.endswith(".description") or name.endswith(".address_line") or name.endswith(".directions_url") or name.endswith(".map_search_url") or name.endswith(".map_embed_url")
    input_html = (
        f'<textarea name="{h(name)}">{h(value)}</textarea>'
        if is_textarea
        else f'<input type="text" name="{h(name)}" value="{h(value)}">'
    )
    file_input = ""
    preview = ""
    if name.endswith(".path"):
        file_input = f'<small>Можно оставить путь как есть или загрузить новый файл:</small><input type="file" name="upload__{h(name)}" accept=".jpg,.jpeg,.png,.webp">'
        preview = f'<div class="preview"><img src="{h(value)}" alt=""></div>' if value else ""
    return f"""
    <div class="field">
      <label>{label}</label>
      {input_html}
      {file_input}
      {preview}
    </div>
    """


def redirect(start_response, location: str, cookie_header: str | None = None):
    headers = [("Location", location)]
    if cookie_header:
        headers.append(("Set-Cookie", cookie_header))
    start_response("302 Found", headers)
    return [b""]


def unauthorized(start_response):
    start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
    return [render_login()]


def get_current_user(environ) -> str | None:
    raw_cookie = environ.get("HTTP_COOKIE", "")
    if not raw_cookie:
        return None
    jar = cookies.SimpleCookie()
    jar.load(raw_cookie)
    token_cookie = jar.get(SESSION_COOKIE)
    if not token_cookie:
        return None
    return get_session_user(token_cookie.value)


def application(environ, start_response):
    initialize_database()
    import_existing_site(force=False)

    path = environ.get("PATH_INFO", "") or "/"
    method = environ.get("REQUEST_METHOD", "GET").upper()
    is_head = method == "HEAD"

    if path == "/admin/login" and method == "POST":
        fields, _files = parse_post_data(environ)
        username = fields.get("username", "")
        password = fields.get("password", "")
        if not authenticate(username, password):
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [render_login("Неверный логин или пароль.")]
        token = create_session(username)
        cookie = cookies.SimpleCookie()
        cookie[SESSION_COOKIE] = token
        cookie[SESSION_COOKIE]["path"] = "/"
        cookie[SESSION_COOKIE]["httponly"] = True
        return redirect(start_response, "/admin", cookie.output(header="").strip())

    if path == "/admin/logout":
        raw_cookie = environ.get("HTTP_COOKIE", "")
        jar = cookies.SimpleCookie()
        jar.load(raw_cookie)
        token_cookie = jar.get(SESSION_COOKIE)
        if token_cookie:
            delete_session(token_cookie.value)
        cookie = cookies.SimpleCookie()
        cookie[SESSION_COOKIE] = ""
        cookie[SESSION_COOKIE]["path"] = "/"
        cookie[SESSION_COOKIE]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
        return redirect(start_response, "/admin/login", cookie.output(header="").strip())

    if path in {"/admin", "/admin/login"} and method in {"GET", "HEAD"}:
        user = get_current_user(environ)
        if user:
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [b"" if is_head else render_admin("home")]
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [b"" if is_head else render_login()]

    if path.startswith("/admin/page/"):
        user = get_current_user(environ)
        if not user:
            return unauthorized(start_response)

        slug = path.rsplit("/", 1)[-1]
        if slug not in PAGE_DEFINITIONS:
            start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
            return [b"Page not found"]

        if method in {"GET", "HEAD"}:
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [b"" if is_head else render_admin(slug)]

        fields, files = parse_post_data(environ)
        page = get_page(slug)
        content = page["content"]
        for name, value in fields.items():
            if name in {"page_title", "schedule_summary"} or name.startswith("upload__"):
                continue
            set_nested(content, name, value)
        if slug == "site-settings" and fields.get("schedule_summary"):
            apply_schedule_summary(content["schedule"], fields["schedule_summary"])
        for name, field in files.items():
            if not name.startswith("upload__"):
                continue
            target_name = name.replace("upload__", "", 1)
            uploaded = save_uploaded_file(field, slug, target_name)
            if uploaded:
                set_nested(content, target_name, uploaded)
        save_page(slug, fields.get("page_title", page["title"]), content)
        if slug == "site-settings":
            generate_all_pages(content)
            notice_text = "Настройки сайта сохранены и все страницы пересобраны."
        else:
            generate_page(slug)
            notice_text = "Изменения сохранены и страница пересобрана."
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [render_admin(slug, notice_text)]

    start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
    return [b"Not found"]


if __name__ == "__main__":
    from wsgiref.simple_server import make_server

    with make_server("127.0.0.1", 8081, application) as server:
        print("Mini CMS running on http://127.0.0.1:8081/admin")
        server.serve_forever()

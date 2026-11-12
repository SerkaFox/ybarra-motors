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

from . import mailcow_api
from .defaults import PAGE_DEFINITIONS
from .generator import generate_all_pages, generate_page
from .importer import import_existing_site
from .storage import (
    add_mail_password_history,
    authenticate,
    create_session,
    delete_session,
    get_mail_password_history,
    get_page,
    get_session_user,
    initialize_database,
    list_pages,
    save_page,
)

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "assets" / "uploads"
SESSION_COOKIE = "ybm_cms_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 90  # 90 días
HTML_HEADERS = [
    ("Content-Type", "text/html; charset=utf-8"),
    ("Cache-Control", "no-store, no-cache, must-revalidate"),
    ("Pragma", "no-cache"),
]
LOCAL_PART_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


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

def is_day_closed(day: dict) -> bool:
    closed = day.get("closed")
    return closed is True or str(closed).strip().lower() == "true"


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

DAY_KEY_TO_INDEX = {key: index for index, (key, _label) in enumerate(DAY_SEQUENCE)}


def schedule_day_value(day: dict) -> str:
    if is_day_closed(day):
        return "Cerrado"
    if day.get("afternoon_open") and day.get("afternoon_close"):
        return f"{day['morning_open']}-{day['morning_close']} / {day['afternoon_open']}-{day['afternoon_close']}h"
    return f"{day['morning_open']}-{day['morning_close']}h"


def format_schedule_line(day_range: str, value: str) -> str:
    if value == "Cerrado":
        return f"Cerrado: {day_range}"
    return f"{day_range}: {value}"


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
        lines.append(format_schedule_line(day_range, current_value))
        current_start = label
        current_end = label
        current_value = value

    day_range = current_start if current_start == current_end else f"{current_start} - {current_end}"
    lines.append(format_schedule_line(day_range, current_value))
    return "\n".join(lines)


def normalize_day_name(value: str) -> str:
    return value.strip().lower().replace(".", "")


def parse_day_tokens(day_part: str) -> list[str] | None:
    """Разбирает «Lunes - Viernes», «Sábado y Domingo», «Sábado, Domingo» и т.п.
    Возвращает список ключей дней или None, если не удалось распознать хоть один токен."""
    tokens = re.split(r"\s*(?:,|\by\b)\s*", day_part.strip(), flags=re.IGNORECASE)
    day_keys: list[str] = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if re.search(r"[-–—]", token):
            start_name, end_name = re.split(r"\s*[-–—]\s*", token, maxsplit=1)
            start_key = DAY_NAME_TO_KEY.get(normalize_day_name(start_name))
            end_key = DAY_NAME_TO_KEY.get(normalize_day_name(end_name))
            if not start_key or not end_key:
                return None
            start_index = DAY_KEY_TO_INDEX[start_key]
            end_index = DAY_KEY_TO_INDEX[end_key]
            day_keys.extend(key for key, _label in DAY_SEQUENCE[start_index:end_index + 1])
        else:
            key = DAY_NAME_TO_KEY.get(normalize_day_name(token))
            if not key:
                return None
            day_keys.append(key)
    return day_keys or None


def parse_time_range(value: str) -> tuple[str, str, str, str, bool]:
    raw = value.strip().lower().rstrip(".")
    if raw in {"cerrado", "closed"}:
        return "", "", "", "", True

    cleaned = raw.replace(" ", "").replace("–", "-").replace("—", "-")
    cleaned = cleaned.replace("h", "")
    parts = [part for part in cleaned.split("/") if part]

    def split_range(chunk: str) -> tuple[str, str]:
        start, end = chunk.split("-", 1)
        return start.strip(), end.strip()

    morning_open, morning_close = split_range(parts[0])
    afternoon_open = ""
    afternoon_close = ""

    if len(parts) > 1:
        afternoon_open, afternoon_close = split_range(parts[1])

    return morning_open, morning_close, afternoon_open, afternoon_close, False


def split_schedule_line(line: str) -> tuple[str, str] | None:
    """Делит строку на две половины по ':' (приоритетно) или по ' - '.
    Не решает, где дни, а где значение — это делает apply_schedule_summary перебором."""
    if ":" in line:
        left, right = line.split(":", 1)
        return left.strip(), right.strip()
    match = re.search(r"\s+[-–—]\s+", line)
    if not match:
        return None
    left = line[:match.start()].strip()
    right = line[match.end():].strip()
    if not left or not right:
        return None
    return left, right


def apply_schedule_summary(schedule: dict, summary: str) -> list[str]:
    """Применяет текст расписания к структуре дней. Понимает оба порядка —
    «Дни: значение» и «значение - Дни» (и наоборот) — через ':' или ' - '.
    Возвращает список строк, которые не удалось распознать (и поэтому не применились)."""
    problems: list[str] = []
    for line in [item.strip() for item in summary.splitlines() if item.strip()]:
        parts = split_schedule_line(line)
        if not parts:
            problems.append(line)
            continue
        applied = False
        for days_str, value_str in (parts, (parts[1], parts[0])):
            try:
                day_keys = parse_day_tokens(days_str)
            except (ValueError, IndexError):
                day_keys = None
            if not day_keys:
                continue
            try:
                morning_open, morning_close, afternoon_open, afternoon_close, closed = parse_time_range(value_str)
            except (ValueError, IndexError):
                continue
            for day_key in day_keys:
                label = dict(DAY_SEQUENCE)[day_key]
                schedule[day_key] = {
                    "label": label,
                    "closed": closed,
                    "morning_open": morning_open,
                    "morning_close": morning_close,
                    "afternoon_open": afternoon_open,
                    "afternoon_close": afternoon_close,
                }
            applied = True
            break
        if not applied:
            problems.append(line)
    return problems


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
    .btn-ghost {{ background: transparent; color: var(--muted); border: 1px solid var(--line); font-size: 13px; padding: 7px 12px; }}
    .btn-ghost:hover {{ color: var(--ink); border-color: var(--muted); }}
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
    .scroll-top {{
      position: fixed;
      right: 24px;
      bottom: 24px;
      z-index: 120;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 46px;
      height: 46px;
      border: none;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      color: #fff;
      cursor: pointer;
      box-shadow: 0 12px 30px rgba(80, 56, 20, 0.28);
      opacity: 0;
      transform: translateY(10px);
      pointer-events: none;
      transition: transform 0.2s ease, opacity 0.2s ease, box-shadow 0.2s ease;
    }}
    .scroll-top.is-visible {{ opacity: 1; transform: translateY(0); pointer-events: auto; }}
    .scroll-top:hover {{ transform: translateY(-2px); box-shadow: 0 16px 34px rgba(80, 56, 20, 0.34); }}
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
  <button id="scroll-top" class="scroll-top" type="button" aria-label="Volver arriba">
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 15 12 9 18 15"></polyline></svg>
  </button>
  <script>
    (function () {{
      var btn = document.getElementById('scroll-top');
      if (!btn) return;
      var toggle = function () {{ btn.classList.toggle('is-visible', window.scrollY > 400); }};
      toggle();
      window.addEventListener('scroll', toggle, {{ passive: true }});
      btn.addEventListener('click', function () {{ window.scrollTo({{ top: 0, behavior: 'smooth' }}); }});
    }})();
  </script>
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
            <label for="password">Пароль</label>
            <div class="password-field">
              <input id="password" name="password" type="password" required autofocus autocomplete="current-password">
              <button type="button" class="password-toggle" aria-label="Mostrar contraseña" aria-pressed="false">
                <svg class="icon-eye" style="display:inline-block" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7Z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                <svg class="icon-eye-off" style="display:none" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.94 10.94 0 0 1 12 19c-7 0-11-7-11-7a21.3 21.3 0 0 1 5.06-5.94M9.9 4.24A10.94 10.94 0 0 1 12 5c7 0 11 7 11 7a21.4 21.4 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>
              </button>
            </div>
          </div>
          <button type="submit">Войти</button>
        </form>
      </div>
    </div>
    <style>
      .password-field {{ position: relative; }}
      .password-field input {{ padding-right: 44px; }}
      .password-toggle {{
        position: absolute; top: 0; right: 0; bottom: 0;
        display: flex; align-items: center; justify-content: center;
        width: 40px; padding: 0; background: transparent; color: var(--muted);
        border-radius: 0 12px 12px 0;
      }}
      .password-toggle:hover {{ color: var(--ink); background: transparent; }}
    </style>
    <script>
      (function () {{
        var input = document.getElementById('password');
        var toggle = document.querySelector('.password-toggle');
        if (!input || !toggle) return;
        toggle.addEventListener('click', function () {{
          var showing = input.type === 'text';
          input.type = showing ? 'password' : 'text';
          toggle.setAttribute('aria-pressed', String(!showing));
          toggle.setAttribute('aria-label', showing ? 'Mostrar contraseña' : 'Ocultar contraseña');
          toggle.querySelector('.icon-eye').style.display = showing ? 'inline-block' : 'none';
          toggle.querySelector('.icon-eye-off').style.display = showing ? 'none' : 'inline-block';
        }});
      }})();
    </script>
    """
    return render_layout("Mini CMS Login", body)


def build_menu_html(active_key: str) -> str:
    pages = list_pages()
    menu_items = []
    for page in pages:
        active = "active" if page["slug"] == active_key else ""
        menu_items.append(
            f'<a class="{active}" href="/admin/page/{h(page["slug"])}">{h(page["title"])}</a>'
        )
    mail_active = "active" if active_key == "mail" else ""
    menu_items.append(f'<a class="{mail_active}" href="/admin/mail">Correo</a>')
    return "".join(menu_items)


def render_admin(page_slug: str, notice: str = "") -> bytes:
    current_page = get_page(page_slug)
    content = current_page["content"]
    flat_fields = flatten_content(content)

    groups = []
    for name, value in flat_fields:
        if name.startswith("meta.") or name.startswith("seo."):
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
      <textarea name="schedule_summary" rows="8">{h(build_schedule_summary(content["schedule"]))}</textarea>
      <small>Una línea por grupo de días. Ejemplos: «Lunes - Viernes: 8:00-18:00h», «Sábado y Domingo: Cerrado», «Sábado: 9:00-13:00h».</small>
    </div>
    """
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
          {build_menu_html(page_slug)}
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


def render_mail(notice: str = "", error: str = "", revealed: dict | None = None) -> bytes:
    warn = f'<div class="notice">{h(notice)}</div>' if notice else ""
    if error:
        warn += f'<div class="warning">{h(error)}</div>'

    reveal_html = ""
    if revealed:
        reveal_html = f"""
    <div class="notice">
      <strong>{h(revealed['email'])}</strong> — {h(revealed['label'])}. Este contraseña se muestra una única vez, copêlo ahora:
      <div style="margin-top:8px;padding:10px 12px;background:#fff;border:1px solid var(--line);border-radius:10px;font-family:monospace;font-size:16px;letter-spacing:0.5px;user-select:all;">{h(revealed['password'])}</div>
    </div>
    """

    rows_html = ""
    boxes: list[dict] = []
    fetch_error = ""
    if not mailcow_api.is_configured():
        fetch_error = "La integración con el servidor de correo no está configurada (falta la clave API)."
    else:
        try:
            boxes = mailcow_api.list_mailboxes()
        except Exception as exc:  # noqa: BLE001 - mostramos cualquier fallo al admin
            fetch_error = f"No se pudo consultar el servidor de correo: {exc}"

    if fetch_error:
        rows_html = f'<div class="warning">{h(fetch_error)}</div>'
    elif not boxes:
        rows_html = '<p class="muted">No hay buzones en el dominio ybarra-motor.es.</p>'
    else:
        rows = []
        for box in boxes:
            email = str(box.get("username", ""))
            active = str(box.get("active", "")) in {"1", "true", "True"}
            status = "activo" if active else "desactivado"
            try:
                app_pw_names = [str(a.get("name", "")) for a in mailcow_api.list_app_passwords(email)]
            except Exception:  # noqa: BLE001
                app_pw_names = []
            app_pw_summary = ", ".join(h(n) for n in app_pw_names) if app_pw_names else "ninguna todavía"
            rows.append(f"""
        <div class="field" style="border:1px solid var(--line);border-radius:14px;padding:14px 16px;">
          <strong>{h(email)}</strong>
          <span class="muted" style="font-size:13px;"> — Estado: {status}</span>

          <div style="margin-top:10px;background:#fff6f0;border:1px solid #f0c9ae;border-radius:12px;padding:10px 12px;">
            <small><strong>Contraseña para Outlook / Gmail / móvil</strong> — esta es la que necesitas.<br>Activas ahora: {app_pw_summary}.</small>
            <form method="post" action="/admin/mail/app-password" style="margin-top:6px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
              <input type="hidden" name="email" value="{h(email)}">
              <input type="text" name="app_name" placeholder="nombre, ej. Outlook" style="width:130px;">
              <input type="text" name="custom_password" placeholder="dejar vacío para generar" style="width:150px;">
              <button type="submit">Generar contraseña de correo</button>
            </form>
          </div>

          <details style="margin-top:8px;">
            <summary class="muted" style="cursor:pointer;font-size:13px;">Opción avanzada: contraseña de acceso web</summary>
            <div style="margin-top:6px;">
              <small class="muted">Solo para entrar en mail.ybarra-motor.es desde el navegador. <strong>No la uses en Outlook ni Gmail</strong>, ahí no funciona.</small>
              <form method="post" action="/admin/mail/reset" onsubmit="return confirm('¿Seguro que quieres restablecer la contraseña WEB de {h(email)}?');" style="margin-top:6px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                <input type="hidden" name="email" value="{h(email)}">
                <input type="text" name="custom_password" placeholder="dejar vacío para generar" style="width:150px;">
                <button type="submit" class="btn-ghost">Restablecer contraseña web</button>
              </form>
            </div>
          </details>
        </div>
        """)
        rows_html = "".join(rows)

    history = get_mail_password_history(limit=20)
    if not history:
        history_html = ""
    else:
        history_rows = []
        for entry in history:
            is_app_pw = "contraseña de correo" in entry["label"]
            border = "border-left:4px solid var(--accent);" if is_app_pw else "border-left:4px solid var(--line);"
            tag = (
                '<span style="font-size:11px;font-weight:700;color:var(--accent);text-transform:uppercase;">Outlook/Gmail · </span>'
                if is_app_pw
                else '<span class="muted" style="font-size:11px;font-weight:700;text-transform:uppercase;">Web · </span>'
            )
            history_rows.append(f"""
        <div class="field" style="border:1px solid var(--line);{border}border-radius:14px;padding:10px 14px;">
          <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center;">
            <div>
              <strong>{h(entry['email'])}</strong>
              <span class="muted" style="font-size:13px;"> — {tag}{h(entry['label'])} · {h(str(entry['created_at']))}</span>
            </div>
            <div style="font-family:monospace;font-size:15px;user-select:all;">{h(entry['password'])}</div>
          </div>
        </div>
        """)
        history_html = f"""
          <fieldset>
            <legend>Historial de contraseñas generadas</legend>
            <p class="muted" style="margin-top:0;">Se guardan aquí en texto plano para poder consultarlas de nuevo. Solo visible para quien tenga acceso a este panel.</p>
            {''.join(history_rows)}
          </fieldset>
        """

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
          {build_menu_html('mail')}
        </aside>
        <main class="panel">
          <h1>Correo corporativo</h1>
          <p class="path">Dominio: ybarra-motor.es</p>
          {reveal_html}

          <fieldset>
            <legend>Buzones existentes</legend>
            {rows_html}
          </fieldset>

          <fieldset>
            <legend>Crear nuevo buzón</legend>
            <form method="post" action="/admin/mail/create">
              <div class="field">
                <label>Parte local (antes de @ybarra-motor.es)</label>
                <input type="text" name="local_part" placeholder="por ejemplo: ventas" required pattern="[a-z0-9][a-z0-9._-]{{0,63}}">
                <small>Solo minúsculas, números, puntos, guiones. Sin espacios ni mayúsculas.</small>
              </div>
              <div class="field">
                <label>Nombre (opcional)</label>
                <input type="text" name="full_name" placeholder="Nombre visible del buzón">
              </div>
              <div class="field">
                <label>Contraseña (opcional)</label>
                <input type="text" name="custom_password" placeholder="dejar vacío para generar automáticamente">
                <small>Mínimo 8 caracteres si la escribes tú. Si lo dejas vacío, se genera una segura.</small>
              </div>
              <button type="submit">Crear buzón</button>
              <small class="muted">Si no escribes una contraseña, se genera automáticamente y se muestra una sola vez.</small>
            </form>
          </fieldset>

          {history_html}
        </main>
      </div>
    </div>
    """
    return render_layout("Correo · Ybarra Mini CMS", body)


def redirect(start_response, location: str, cookie_header: str | None = None):
    headers = [("Location", location)]
    if cookie_header:
        headers.append(("Set-Cookie", cookie_header))
    start_response("302 Found", headers)
    return [b""]


def unauthorized(start_response):
    start_response("200 OK", HTML_HEADERS)
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
    if path.lower().startswith("/admin"):
        path = path.lower()
    method = environ.get("REQUEST_METHOD", "GET").upper()
    is_head = method == "HEAD"

    if path == "/admin/login" and method == "POST":
        fields, _files = parse_post_data(environ)
        username = "admin"
        password = fields.get("password", "")
        if not authenticate(username, password):
            start_response("200 OK", HTML_HEADERS)
            return [render_login("Неверный логин или пароль.")]
        token = create_session(username)
        cookie = cookies.SimpleCookie()
        cookie[SESSION_COOKIE] = token
        cookie[SESSION_COOKIE]["path"] = "/"
        cookie[SESSION_COOKIE]["httponly"] = True
        cookie[SESSION_COOKIE]["max-age"] = SESSION_MAX_AGE_SECONDS
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
            start_response("200 OK", HTML_HEADERS)
            return [b"" if is_head else render_admin("home")]
        start_response("200 OK", HTML_HEADERS)
        return [b"" if is_head else render_login()]

    if path == "/admin/mail" and method in {"GET", "HEAD"}:
        user = get_current_user(environ)
        if not user:
            return unauthorized(start_response)
        start_response("200 OK", HTML_HEADERS)
        return [b"" if is_head else render_mail()]

    if path == "/admin/mail/create" and method == "POST":
        user = get_current_user(environ)
        if not user:
            return unauthorized(start_response)
        fields, _files = parse_post_data(environ)
        local_part = fields.get("local_part", "").strip().lower()
        full_name = fields.get("full_name", "").strip()
        custom_password = fields.get("custom_password", "").strip()
        start_response("200 OK", HTML_HEADERS)
        if not LOCAL_PART_RE.match(local_part):
            return [render_mail(error="Parte local no válida. Usa solo minúsculas, números, puntos y guiones, sin espacios.")]
        if custom_password and len(custom_password) < 8:
            return [render_mail(error="La contraseña debe tener al menos 8 caracteres.")]
        password = custom_password or mailcow_api.generate_password()
        try:
            ok, msg = mailcow_api.create_mailbox(local_part, password, full_name)
        except Exception as exc:  # noqa: BLE001 - se muestra al admin
            ok, msg = False, str(exc)
        email = f"{local_part}@{mailcow_api.DOMAIN}"
        label = "buzón creado (contraseña propia)" if custom_password else "buzón creado (generada)"
        if ok:
            add_mail_password_history(email, password, label)
            return [render_mail(revealed={"email": email, "password": password, "label": label})]
        return [render_mail(error=f"No se pudo crear el buzón: {msg}")]

    if path == "/admin/mail/reset" and method == "POST":
        user = get_current_user(environ)
        if not user:
            return unauthorized(start_response)
        fields, _files = parse_post_data(environ)
        email = fields.get("email", "").strip().lower()
        custom_password = fields.get("custom_password", "").strip()
        start_response("200 OK", HTML_HEADERS)
        if not email.endswith("@" + mailcow_api.DOMAIN):
            return [render_mail(error="Buzón no válido.")]
        if custom_password and len(custom_password) < 8:
            return [render_mail(error="La contraseña debe tener al menos 8 caracteres.")]
        password = custom_password or mailcow_api.generate_password()
        try:
            ok, msg = mailcow_api.set_password(email, password)
        except Exception as exc:  # noqa: BLE001 - se muestra al admin
            ok, msg = False, str(exc)
        reset_label = "contraseña web restablecida (propia)" if custom_password else "contraseña web restablecida (generada)"
        if ok:
            add_mail_password_history(email, password, reset_label)
            return [render_mail(revealed={"email": email, "password": password, "label": reset_label})]
        return [render_mail(error=f"No se pudo restablecer la contraseña: {msg}")]

    if path == "/admin/mail/app-password" and method == "POST":
        user = get_current_user(environ)
        if not user:
            return unauthorized(start_response)
        fields, _files = parse_post_data(environ)
        email = fields.get("email", "").strip().lower()
        app_name = fields.get("app_name", "").strip() or "Correo (Outlook/Gmail/móvil)"
        custom_password = fields.get("custom_password", "").strip()
        start_response("200 OK", HTML_HEADERS)
        if not email.endswith("@" + mailcow_api.DOMAIN):
            return [render_mail(error="Buzón no válido.")]
        if custom_password and len(custom_password) < 8:
            return [render_mail(error="La contraseña debe tener al menos 8 caracteres.")]
        password = custom_password or mailcow_api.generate_password()
        try:
            ok, msg = mailcow_api.create_app_password(email, app_name, password)
        except Exception as exc:  # noqa: BLE001 - se muestra al admin
            ok, msg = False, str(exc)
        app_label = f"contraseña de correo «{app_name}»" + (" (propia)" if custom_password else " (generada)")
        if ok:
            add_mail_password_history(email, password, app_label)
            return [render_mail(revealed={"email": email, "password": password, "label": app_label})]
        return [render_mail(error=f"No se pudo generar la contraseña de correo: {msg}")]

    if path.startswith("/admin/page/"):
        user = get_current_user(environ)
        if not user:
            return unauthorized(start_response)

        slug = path.rsplit("/", 1)[-1]
        if slug not in PAGE_DEFINITIONS:
            start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
            return [b"Page not found"]

        if method in {"GET", "HEAD"}:
            start_response("200 OK", HTML_HEADERS)
            return [b"" if is_head else render_admin(slug)]

        fields, files = parse_post_data(environ)
        page = get_page(slug)
        content = page["content"]
        for name, value in fields.items():
            if name in {"page_title", "schedule_summary"} or name.startswith("upload__"):
                continue
            set_nested(content, name, value)
        schedule_problems: list[str] = []
        if slug == "site-settings" and fields.get("schedule_summary"):
            schedule_problems = apply_schedule_summary(content["schedule"], fields["schedule_summary"])
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
            if schedule_problems:
                notice_text = (
                    "Guardado, pero no entendí estas líneas del horario y NO se aplicaron: "
                    + " | ".join(schedule_problems)
                    + ". Corrígelas y guarda de nuevo."
                )
            else:
                notice_text = "Настройки сайта сохранены и все страницы пересобраны."
        else:
            generate_page(slug)
            notice_text = "Изменения сохранены и страница пересобрана."
        start_response("200 OK", HTML_HEADERS)
        return [render_admin(slug, notice_text)]

    start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
    return [b"Not found"]


if __name__ == "__main__":
    from wsgiref.simple_server import make_server

    with make_server("127.0.0.1", 8081, application) as server:
        print("Mini CMS running on http://127.0.0.1:8081/admin")
        server.serve_forever()

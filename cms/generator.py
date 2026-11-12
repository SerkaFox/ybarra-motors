from __future__ import annotations

import html
import json
import subprocess
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from .defaults import SERVICE_PAGES
from .storage import get_page, get_site_settings

BASE_DIR = Path(__file__).resolve().parent.parent

SITE_URL = "https://ybarra-motor.es"


def asset_version(relative_path: str) -> str:
    asset_path = BASE_DIR / relative_path.lstrip("/")
    try:
        return str(int(asset_path.stat().st_mtime))
    except OSError:
        return "1"


def e(value: str) -> str:
    return html.escape(value, quote=True)


def rich_text(value: str) -> str:
    escaped = e(value).replace("\n", "<br>\n")
    replacements = {
        "&lt;strong&gt;": "<strong>",
        "&lt;/strong&gt;": "</strong>",
        "&lt;em&gt;": "<em>",
        "&lt;/em&gt;": "</em>",
        "&lt;br&gt;": "<br>",
        "&lt;br /&gt;": "<br>",
        "&lt;br/&gt;": "<br>",
    }
    for original, replacement in replacements.items():
        escaped = escaped.replace(original, replacement)
    return escaped


@lru_cache(maxsize=256)
def image_dimensions(path: str) -> str:
    """Return a ' width="W" height="H"' HTML attribute string for a local image path, or "" if unknown."""
    if path.startswith("http://") or path.startswith("https://"):
        return ""
    fs_path = BASE_DIR / path.lstrip("/")
    try:
        result = subprocess.run(
            ["identify", "-format", "%w %h", str(fs_path)],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        width, height = result.stdout.strip().split()
        return f' width="{int(width)}" height="{int(height)}"'
    except Exception:
        return ""


def og_image_url(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{SITE_URL}{quote(path, safe='/:')}"


def opening_hours_jsonld(settings: dict) -> str:
    day_codes = {
        "monday": "Monday",
        "tuesday": "Tuesday",
        "wednesday": "Wednesday",
        "thursday": "Thursday",
        "friday": "Friday",
        "saturday": "Saturday",
        "sunday": "Sunday",
    }
    specs = []
    for key, code in day_codes.items():
        day = settings["schedule"][key]
        if day["closed"] in (True, "True", "true"):
            continue
        if day["morning_open"] and day["morning_close"]:
            specs.append(
                f'    {{ "@type": "OpeningHoursSpecification", "dayOfWeek": "{code}", '
                f'"opens": "{day["morning_open"]}", "closes": "{day["morning_close"]}" }}'
            )
        if day["afternoon_open"] and day["afternoon_close"]:
            specs.append(
                f'    {{ "@type": "OpeningHoursSpecification", "dayOfWeek": "{code}", '
                f'"opens": "{day["afternoon_open"]}", "closes": "{day["afternoon_close"]}" }}'
            )
    return ",\n".join(specs)


def is_day_closed(day: dict) -> bool:
    closed = day.get("closed")
    return closed is True or str(closed).strip().lower() == "true"


def build_schedule_rows(settings: dict) -> str:
    rows = []
    for key in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
        day = settings["schedule"][key]
        if is_day_closed(day):
            value = '<span class="contact-schedule-closed">Cerrado</span>'
        elif day["afternoon_open"] and day["afternoon_close"]:
            value = f"{e(day['morning_open'])}–{e(day['morning_close'])} / {e(day['afternoon_open'])}–{e(day['afternoon_close'])}"
        else:
            value = f"{e(day['morning_open'])}–{e(day['morning_close'])}"
        rows.append(
            f"""      <div class="contact-schedule-row">
        <span>{e(day['label'])}</span>
        <span>{value}</span>
      </div>"""
        )
    return "\n".join(rows)


def format_schedule_value(day: dict) -> str:
    if is_day_closed(day):
        return "Cerrado"
    if day["afternoon_open"] and day["afternoon_close"]:
        return f"{day['morning_open']}-{day['morning_close']} / {day['afternoon_open']}-{day['afternoon_close']}h"
    return f"{day['morning_open']}-{day['morning_close']}h"


def format_schedule_line(day_range: str, value: str) -> str:
    if value == "Cerrado":
        return f"Cerrado: {day_range}"
    return f"{day_range}: {value}"


def build_schedule_summary(settings: dict) -> str:
    ordered_days = [
        ("monday", "Lunes"),
        ("tuesday", "Martes"),
        ("wednesday", "Miércoles"),
        ("thursday", "Jueves"),
        ("friday", "Viernes"),
        ("saturday", "Sábado"),
        ("sunday", "Domingo"),
    ]
    lines = []
    start_key, start_label = ordered_days[0]
    current_value = format_schedule_value(settings["schedule"][start_key])
    current_start = start_label
    current_end = start_label

    for key, label in ordered_days[1:]:
        value = format_schedule_value(settings["schedule"][key])
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
    return "<br>\n".join(e(line) for line in lines)


def schedule_script(settings: dict) -> str:
    return f'<script>window.YBARRA_CONTACT = {json.dumps(settings, ensure_ascii=False)};</script>'


def render_header_include(settings: dict) -> str:
    phone_href = settings["contact"]["phone_href"]
    phone_display = settings["contact"]["phone_display"]
    return f"""
<header class="topbar">
  <div class="wrap topbar-inner">
    <a class="brand" href="/" aria-label="Ybarra Motor Inicio">
      <div class="brand-logo">
        <img src="/assets/img/logo-ybarra.jpg" alt="Logo Ybarra Motor"{image_dimensions("/assets/img/logo-ybarra.jpg")}>
      </div>
    </a>

    <nav class="nav nav--menu" aria-label="Navegación principal">
      <a href="/">Inicio</a>

      <div class="dropdown">
        <button class="dropdown-toggle" type="button" aria-expanded="false">
          Servicios
          <span class="dropdown-arrow">▾</span>
        </button>

        <div class="dropdown-menu">
          <a href="/servicios/neumaticos/">Neumáticos</a>
          <a href="/servicios/mantenimiento-general/">Mantenimiento general</a>
          <a href="/servicios/suspension-y-direccion/">Suspensión y dirección</a>
          <a href="/servicios/baterias-para-coches/">Baterías para coches</a>
          <a href="/servicios/frenos-y-pastillas/">Frenos y pastillas</a>
          <a href="/servicios/pre-itv/">Pre ITV</a>
        </div>
      </div>

      <a href="/#contacto">Contacto</a>
      <a class="nav-phone" href="tel:{e(phone_href)}" aria-label="Llamar al {e(phone_display)}">{e(phone_display)}</a>
    </nav>
  </div>
</header>
""".lstrip()


def render_footer_include(settings: dict) -> str:
    whatsapp = settings["contact"]["whatsapp_number"]
    directions = settings["contact"]["directions_url"]
    return f"""
<footer class="footer">
  <div class="wrap footer-inner">
    <span>© <span id="current-year"></span> {e(settings["contact"]["company_name"])}</span>
    <span>Bilbao · Taller multimarca · Neumáticos · Mantenimiento · Frenos · Pre ITV</span>
    <span><a href="https://wa.me/{e(whatsapp)}" target="_blank" rel="noopener">WhatsApp</a></span>
    <span><a href="{e(directions)}" target="_blank" rel="noopener">Cómo llegar</a></span>
    <span><a href="/aviso-legal/">Aviso legal</a> · <a href="/politica-de-privacidad/">Privacidad</a> · <a href="/politica-de-cookies/">Cookies</a></span>
  </div>
  <a class="whatsapp-float" href="https://wa.me/{e(whatsapp)}" target="_blank" rel="noopener" aria-label="Escribir por WhatsApp">
    WhatsApp
  </a>
  <button id="scroll-top" class="scroll-top" type="button" hidden aria-label="Volver arriba">
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 15 12 9 18 15"></polyline></svg>
  </button>
</footer>
""".lstrip()


def render_home(page: dict, settings: dict | None = None) -> str:
    c = page["content"]
    settings = settings or get_site_settings()
    phone_href = settings["contact"]["phone_href"]
    phone_display = settings["contact"]["phone_display"]
    email = settings["contact"]["email"]
    whatsapp = settings["contact"]["whatsapp_number"]
    address = settings["contact"]["address_line"]
    directions = settings["contact"]["directions_url"]
    map_search = settings["contact"]["map_search_url"]
    map_embed = settings["contact"]["map_embed_url"]
    panorama_embed = "https://www.google.com/maps/embed?pb=!4v1776806016200!6m8!1m7!1s7UGrjcZmWG7MwbrSEzgemg!2m2!1d43.26935937132199!2d-2.945317985302342!3f71.0466424430656!4f-4.812830387258074!5f0.7820865974627469"
    schedule_summary = build_schedule_summary(settings)
    hero_points = "\n".join(
        f"""            <div class="mini-point">
              <strong>{e(item['title'])}</strong>
              <span>{rich_text(item['text'])}</span>
            </div>"""
        for item in c["hero"]["points"]
    )
    hero_quick = "\n".join(
        f"""    <div class="hero-quick-item">
      <strong>{e(item['title'])}</strong>
      <span>{rich_text(item['text'])}</span>
    </div>"""
        for item in c["hero"]["quick_items"]
    )
    offer_catalog_items = ",\n".join(
        f'''      {{ "@type": "Offer", "itemOffered": {{ "@type": "Service", "name": "{e(meta["label"])}", "url": "{SITE_URL}{meta["url"]}" }} }}'''
        for meta in SERVICE_PAGES.values()
    )
    opening_hours = opening_hours_jsonld(settings)
    service_cards = "\n".join(
        f"""  <a class="service-card reveal" href="{e(card['href'])}">
    <div class="service-card-media">
      <img src="{e(card['image']['path'])}" alt="{e(card['image']['alt'])}" loading="lazy"{image_dimensions(card['image']['path'])}>
      <div class="service-card-overlay"></div>
    </div>
    <div class="service-card-body">
      <h3>{e(card['title'])}</h3>
      <p>{rich_text(card['text'])}</p>
      <span class="service-card-cta">Saber más</span>
    </div>
  </a>"""
        for card in c["services"]["cards"]
    )
    features = "\n".join(
        f"""    <div class="feature-item">
      <div class="feature-icon"></div>
      <div>
        <strong>{e(item['title'])}</strong>
        <span>{rich_text(item['text'])}</span>
      </div>
    </div>"""
        for item in c["advantages"]["features"]
    )
    reviews = "\n".join(
        f"""        <div class="review-card">
          <p>
            {e(item['text'])}
          </p>
          <div class="review-meta">
            <strong>{e(item['author'])}</strong>
          </div>
        </div>"""
        for item in c["reviews"]["items"]
    )
    return f"""<!doctype html>
<html lang="es">
<head>
  <script src="/assets/js/consent.js?v={asset_version('assets/js/consent.js')}" defer></script>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{e(c['seo']['title'])}</title>
  <meta name="description" content="{e(c['seo']['description'])}">
  <meta name="keywords" content="taller mecánico Bilbao, taller multimarca Bilbao, neumáticos Bilbao, frenos Bilbao, baterías coche Bilbao, pre ITV Bilbao, suspensión dirección Bilbao, mantenimiento coche Bilbao">
  <meta name="robots" content="index,follow">
  <meta name="theme-color" content="#121212">
  <link rel="canonical" href="{e(c['seo']['canonical_url'])}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/assets/css/styles.css?v={asset_version('assets/css/styles.css')}">
<link rel="icon" href="/assets/favicon/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/assets/favicon/favicon-32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/assets/favicon/favicon-16.png">
<link rel="apple-touch-icon" href="/assets/favicon/apple-touch-icon.png">

  <meta property="og:type" content="website">
  <meta property="og:title" content="{e(c['seo']['og_title'])}">
  <meta property="og:description" content="{e(c['seo']['og_description'])}">
  <meta property="og:url" content="{e(c['seo']['canonical_url'])}">
  <meta property="og:site_name" content="Ybarra Motor">
  <meta property="og:image" content="{e(og_image_url(c['hero']['image']['path']))}">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{e(c['seo']['twitter_title'])}">
  <meta name="twitter:description" content="{e(c['seo']['twitter_description'])}">
  <meta name="twitter:image" content="{e(c['seo']['twitter_image'])}">
  {schedule_script(settings)}

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "AutoRepair",
    "@id": "{SITE_URL}/#taller",
    "name": "{e(settings["contact"]["company_name"])}",
    "image": "{SITE_URL}/assets/img/logo-ybarra.jpg",
    "url": "{SITE_URL}/",
    "telephone": "{e(phone_href)}",
    "email": "{e(email)}",
    "priceRange": "€€",
    "address": {{
      "@type": "PostalAddress",
      "streetAddress": "{e(settings["contact"]["street_address"])}",
      "addressLocality": "{e(settings["contact"]["locality"])}",
      "addressRegion": "Bizkaia",
      "postalCode": "{e(settings["contact"]["postal_code"])}",
      "addressCountry": "{e(settings["contact"]["country"])}"
    }},
    "geo": {{
      "@type": "GeoCoordinates",
      "latitude": 43.26944555007976,
      "longitude": -2.945343068251051
    }},
    "areaServed": [
      {{ "@type": "City", "name": "Bilbao" }},
      {{ "@type": "Place", "name": "Deusto" }}
    ],
    "description": "Taller mecánico multimarca en Bilbao (Deusto) con servicios de neumáticos, mantenimiento general, suspensión y dirección, baterías, frenos y Pre ITV.",
    "openingHoursSpecification": [
{opening_hours}
    ],
    "sameAs": [
      "https://www.facebook.com/Ybarra-Motor-Taller-Mec%C3%A1nico-100054352218088/",
      "{e(settings["contact"]["map_search_url"])}"
    ],
    "aggregateRating": {{
      "@type": "AggregateRating",
      "ratingValue": "4.8",
      "reviewCount": "100"
    }},
    "hasOfferCatalog": {{
      "@type": "OfferCatalog",
      "name": "Servicios del taller",
      "itemListElement": [
{offer_catalog_items}
      ]
    }}
  }}
  </script>
</head>
<body>
  <div id="site-header"></div>

  <main>
    <section class="hero" id="inicio">
      <div class="wrap hero-grid">
        <div class="hero-main reveal">
          <div class="eyebrow">Bilbao (Deusto) · atención cercana · rapidez real</div>
          <h1>
            <span class="hero-title-line">Ybarra Motor</span>
            <span class="hero-title-line hero-title-line--accent">Tu <span class="hero-scramble" data-text-from="amigo" data-text-to="taller">amigo</span> mecánico en Bilbao</span>
          </h1>
          <p class="lead">Revisión clara, trabajo fino y soluciones pensadas para el uso diario del coche. En <strong>Ybarra Motor</strong>, tu taller mecánico multimarca en Bilbao (Deusto), cuidamos tu vehículo con trato cercano, montaje correcto y tiempos razonables.</p>

          <div class="hero-actions">
            <a class="btn btn-primary" href="tel:{e(phone_href)}">Llamar: {e(phone_display)}</a>
            <a class="btn btn-secondary" href="https://wa.me/{e(whatsapp)}" target="_blank" rel="noopener">WhatsApp</a>
            <a class="btn btn-secondary" href="{e(directions)}" target="_blank" rel="noopener">Cómo llegar</a>
          </div>

          <div class="hero-points">
{hero_points}
          </div>
        </div>

<aside class="hero-side reveal">

  <div class="hero-media-card">
    <img
      class="hero-media-fallback"
      src="{e(c['hero']['image']['path'])}"
      alt="{e(c['hero']['image']['alt'])}"
      fetchpriority="high"{image_dimensions(c['hero']['image']['path'])}
    >
    <div class="hero-media-overlay"></div>

  </div>

  <div class="hero-quick">
{hero_quick}
  </div>

</aside>
      </div>
    </section>

    <section id="servicios">
      <div class="wrap">
        <div class="section-head reveal">
          <div>
            <h2>{e(c['services']['title'])}</h2>
          </div>
          <p>
            {rich_text(c['services']['description'])}
          </p>
        </div>
<div class="services-grid">
{service_cards}
</div>
        <p style="margin-top:18px;"><a href="/servicios/">Ver todos los servicios del taller →</a></p>
      </div>
    </section>

    <section id="ventajas">
      <div class="wrap info-grid">
<article class="about-card reveal">
  <div class="section-head section-head--stack">
    <h2>{e(c['advantages']['title'])}</h2>
  </div>
  <p>
    {rich_text(c['advantages']['text'])}
  </p>

  <div class="feature-list">
{features}
  </div>

  <div class="about-photo">
    <img src="{e(c['advantages']['image']['path'])}" alt="{e(c['advantages']['image']['alt'])}" loading="lazy"{image_dimensions(c['advantages']['image']['path'])}>
  </div>
</article>

		<article class="contact-card reveal" id="contacto">
  <div class="section-head section-head--stack">
    <h2>{e(c['contact']['title'])}</h2>
  </div>

  <p>
    {rich_text(c['contact']['text'])}
  </p>

    <div class="contact-list">
      <div class="contact-item">
        <span>📞 Teléfono</span>
      <a href="tel:{e(phone_href)}"><strong>{e(phone_display)}</strong></a>
      </div>
      <div class="contact-item">
        <span>✉️ Email</span>
      <a href="mailto:{e(email)}"><strong>{e(email)}</strong></a>
      </div>
      <div class="contact-item">
        <span>📍 Dirección</span>
      <strong>{e(address)}</strong>
      </div>
      <div class="contact-item">
        <span>🗺️ Cómo llegar</span>
      <a href="{e(directions)}" target="_blank" rel="noopener">
        <strong>Abrir ruta en Google Maps</strong>
      </a>
    </div>
  </div>

  <div class="contact-schedule">
    <div id="open-status" class="open-status open-status--inline">
      <strong id="open-status-text">Consultando horario...</strong>
      <span id="open-status-subtext">Horario de Bilbao</span>
    </div>

    <div class="schedule-summary">
      <strong>Horario</strong>
      <p>{schedule_summary}</p>
    </div>

    <p class="contact-schedule-note">
      {e(settings["schedule"]["closed_note"])}
    </p>
  </div>
</article>
		</div>
    </section>

    <section id="mapa">
      <div class="wrap">
        <div class="section-head reveal">
          <div>
            <h2>{e(c['contact']['map_title'])}</h2>
          </div>
          <p>
            {rich_text(c['contact']['map_text'])}
          </p>
        </div>

        <div class="contact-card reveal map-card">
          <div class="map-split">
            <div class="map-embed">
              <iframe
                data-src="{e(panorama_embed)}"
                loading="lazy"
                referrerpolicy="no-referrer-when-downgrade"
                title="Panorámica de Ybarra Motor Taller Mecánico">
              </iframe>
            </div>

            <div class="map-embed">
              <iframe
                data-src="{e(map_embed)}"
                loading="lazy"
                referrerpolicy="no-referrer-when-downgrade"
                title="Mapa de Ybarra Motor Taller Mecánico">
              </iframe>
            </div>
          </div>

          <div class="hero-actions">
            <a class="btn btn-primary" href="{e(directions)}" target="_blank" rel="noopener">Cómo llegar</a>
            <a class="btn btn-secondary" href="{e(map_search)}" target="_blank" rel="noopener">Abrir mapa</a>
          </div>
        </div>
      </div>
    </section>
<section id="reseñas">
  <div class="wrap">
    <div class="reviews-panel reveal">
      <div class="reviews-head">
        <div class="reviews-heading">
          <div class="google-badge" aria-label="Reseñas de Google">
            <span class="google-badge-word">
              <span class="google-g1">G</span><span class="google-o1">o</span><span class="google-o2">o</span><span class="google-g2">g</span><span class="google-l">l</span><span class="google-e">e</span>
            </span>
            <span class="google-badge-label">Reseñas verificadas</span>
          </div>
        </div>

        <div class="reviews-score">
          <div class="reviews-score-stars">★★★★★</div>
          <strong>{e(c['reviews']['score'])}</strong>
          <span>{e(c['reviews']['score_detail'])}</span>
          <a class="btn btn-secondary" href="https://www.google.com/maps/place/Taller+Ybarra+Motor/@43.2692773,-2.9477529,641m/data=!3m1!1e3!4m8!3m7!1s0xd4e50230634c72b:0x188ac095b6a1561b!8m2!3d43.2692773!4d-2.945178!9m1!1b1!16s%2Fg%2F11cns67vjg?entry=ttu&g_ep=EgoyMDI2MDMzMC4wIKXMDSoASAFQAw%3D%3D" target="_blank" rel="noopener">
            Ver reseñas
          </a>
        </div>
      </div>

      <div class="reviews-slider">
{reviews}
      </div>

    </div>
  </div>
</section>
    <section>
      <div class="wrap">
        <div class="cta-card reveal">
          <div>
            <h2 class="cta-title">{e(c['cta']['title'])}</h2>
            <p>{rich_text(c['cta']['text'])}</p>
          </div>
          <div class="hero-actions hero-actions--compact">
            <a class="btn btn-primary" href="tel:{e(phone_href)}">Llamar ahora</a>
            <a class="btn btn-secondary" href="https://wa.me/{e(whatsapp)}" target="_blank" rel="noopener">WhatsApp</a>
          </div>
        </div>
      </div>
    </section>
  </main>

  <div id="site-footer"></div>

  <script src="/assets/js/main.js?v={asset_version('assets/js/main.js')}"></script>
</body>
</html>
"""


def render_service(page: dict, settings: dict | None = None) -> str:
    c = page["content"]
    settings = settings or get_site_settings()
    phone_href = settings["contact"]["phone_href"]
    phone_display = settings["contact"]["phone_display"]
    email = settings["contact"]["email"]
    address = settings["contact"]["address_line"]
    service_meta = SERVICE_PAGES[page["slug"]]
    service_url = f"{SITE_URL}{service_meta['url']}"
    points = "\n".join(
        f"""            <div class="mini-point">
              <strong>{e(item['title'])}</strong>
              <span>{rich_text(item['text'])}</span>
            </div>"""
        for item in c["hero"]["points"]
    )
    badges = "\n".join(f'            <span class="badge">{e(item)}</span>' for item in c["hero"]["badges"])
    gallery_images = "\n".join(
        f'        <img src="{e(item["path"])}" alt="{e(item["alt"])}" loading="lazy"{image_dimensions(item["path"])}>'
        for item in c["gallery"]["images"]
    )
    gallery_duplicates = "\n".join(
        f'        <img src="{e(item["path"])}" alt="" loading="lazy" aria-hidden="true"{image_dimensions(item["path"])}>'
        for item in c["gallery"]["images"]
    )
    features = "\n".join(
        f"""            <div class="feature-item">
              <div class="feature-icon"></div>
              <div>
                <strong>{e(item['title'])}</strong>
                <span>{rich_text(item['text'])}</span>
              </div>
            </div>"""
        for item in c["about"]["features"]
    )

    return f"""<!doctype html>
<html lang="es">
<head>
  <script src="/assets/js/consent.js?v={asset_version('assets/js/consent.js')}" defer></script>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{e(c['seo']['title'])}</title>
  <meta name="description" content="{e(c['seo']['description'])}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{e(c['seo']['canonical_url'])}">
  <link rel="stylesheet" href="/assets/css/styles.css?v={asset_version('assets/css/styles.css')}">
<link rel="icon" href="/assets/favicon/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/assets/favicon/favicon-32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/assets/favicon/favicon-16.png">
<link rel="apple-touch-icon" href="/assets/favicon/apple-touch-icon.png">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{e(c['seo']['og_title'])}">
  <meta property="og:description" content="{e(c['seo']['og_description'])}">
  <meta property="og:url" content="{e(c['seo']['canonical_url'])}">
  <meta property="og:image" content="{e(og_image_url(c['hero']['image']['path']))}">

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Service",
    "serviceType": "{e(service_meta['label'])}",
    "name": "{e(c['seo']['og_title'])}",
    "url": "{service_url}",
    "description": "{e(c['seo']['description'])}",
    "areaServed": [
      {{ "@type": "City", "name": "Bilbao" }},
      {{ "@type": "Place", "name": "Deusto" }}
    ],
    "provider": {{ "@id": "{SITE_URL}/#taller" }}
  }}
  </script>
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
      {{ "@type": "ListItem", "position": 1, "name": "Inicio", "item": "{SITE_URL}/" }},
      {{ "@type": "ListItem", "position": 2, "name": "Servicios", "item": "{SITE_URL}/servicios/" }},
      {{ "@type": "ListItem", "position": 3, "name": "{e(service_meta['label'])}", "item": "{service_url}" }}
    ]
  }}
  </script>
</head>
<body>
  <div id="site-header"></div>

  <main>
    <section class="hero service-hero">
      <div class="wrap hero-grid">
        <div class="hero-main reveal">
          <div class="eyebrow">{e(c['hero']['eyebrow'])}</div>
          <h1>{e(c['hero']['title'])}</h1>
          <p class="lead">
            {rich_text(c['hero']['lead'])}
          </p>

          <div class="hero-actions">
            <a class="btn btn-primary" href="tel:{e(phone_href)}">Llamar ahora</a>
            <a class="btn btn-secondary" href="mailto:{e(email)}">Pedir información</a>
          </div>

          <div class="hero-points">
{points}
          </div>
        </div>

        <aside class="hero-side reveal">
          <div class="service-hero-photo-card">
            <img src="{e(c['hero']['image']['path'])}" alt="{e(c['hero']['image']['alt'])}" fetchpriority="high"{image_dimensions(c['hero']['image']['path'])}>
            <div class="service-hero-photo-overlay"></div>
            <div class="service-hero-badge">{e(c['hero']['badge'])}</div>
          </div>

          <div class="service-badges">
{badges}
          </div>
        </aside>
      </div>
    </section>

    <section class="service-gallery-section">
  <div class="wrap">
    <div class="section-head reveal">
      <div>
        <h2>{e(c['gallery']['title'])}</h2>
      </div>
      <p>
        {rich_text(c['gallery']['description'])}
      </p>
    </div>

    <div class="service-slider reveal">
      <div class="service-slider-track">
{gallery_images}

{gallery_duplicates}
      </div>
    </div>
  </div>
</section>

    <section>
      <div class="wrap info-grid">
        <article class="about-card reveal">
          <div class="section-head section-head--stack">
            <h2>{e(c['about']['title'])}</h2>
          </div>
          <p>
            {rich_text(c['about']['text'])}
          </p>

          <div class="feature-list">
{features}
          </div>
        </article>

        <article class="contact-card reveal">
          <div class="section-head section-head--stack">
            <h2>{e(c['contact']['title'])}</h2>
          </div>
          <p>
            {rich_text(c['contact']['text'])}
          </p>

          <div class="contact-list">
            <div class="contact-item">
              <span>Teléfono</span>
              <a href="tel:{e(phone_href)}"><strong>{e(phone_display)}</strong></a>
            </div>
            <div class="contact-item">
              <span>Email</span>
              <a href="mailto:{e(email)}"><strong>{e(email)}</strong></a>
            </div>
            <div class="contact-item">
              <span>Dirección</span>
              <strong>{e(address)}</strong>
            </div>
          </div>
        </article>
      </div>
    </section>

    <section>
      <div class="wrap">
        <div class="cta-card reveal">
          <div>
            <h2 class="cta-title">{e(c['cta']['title'])}</h2>
            <p>{rich_text(c['cta']['text'])}</p>
          </div>
          <div class="hero-actions hero-actions--compact">
            <a class="btn btn-primary" href="tel:{e(phone_href)}">Llamar ahora</a>
            <a class="btn btn-secondary" href="/">Volver al inicio</a>
          </div>
        </div>
      </div>
    </section>
  </main>

  <div id="site-footer"></div>

  <script src="/assets/js/main.js?v={asset_version('assets/js/main.js')}"></script>
</body>
</html>
"""


def generate_page(slug: str, settings_override: dict | None = None) -> None:
    page = get_page(slug)
    if not page:
        raise ValueError(f"Unknown page slug: {slug}")
    if page["kind"] == "settings":
        generate_includes(settings_override)
        return
    target = BASE_DIR / page["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    html_output = (
        render_home(page, settings_override)
        if page["kind"] == "home"
        else render_service(page, settings_override)
    )
    target.write_text(html_output, encoding="utf-8")


def generate_includes(settings_override: dict | None = None) -> None:
    settings = settings_override or get_site_settings()
    (BASE_DIR / "assets" / "includes" / "header.html").write_text(
        render_header_include(settings),
        encoding="utf-8",
    )
    (BASE_DIR / "assets" / "includes" / "footer.html").write_text(
        render_footer_include(settings),
        encoding="utf-8",
    )


def generate_all_pages(settings_override: dict | None = None) -> None:
    generate_includes(settings_override)
    generate_page("home", settings_override)
    for slug in SERVICE_PAGES:
        generate_page(slug, settings_override)

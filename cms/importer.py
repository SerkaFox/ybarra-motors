from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .defaults import (
    HOME_HERO_POINTS_FALLBACK,
    HOME_HERO_QUICK_FALLBACK,
    PAGE_DEFINITIONS,
    SERVICE_PAGES,
    SITE_SETTINGS_DEFAULT,
)
from .storage import get_connection, initialize_database

BASE_DIR = Path(__file__).resolve().parent.parent


def _clean_html(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract(pattern: str, source: str, flags: int = re.S) -> str:
    match = re.search(pattern, source, flags)
    if not match:
        raise ValueError(f"Pattern not found: {pattern}")
    return match.group(1).strip()


def _extract_all(pattern: str, source: str, flags: int = re.S) -> list[tuple[str, ...]]:
    return [tuple(group.strip() for group in match) for match in re.findall(pattern, source, flags)]


def parse_service_page(html: str, slug: str) -> dict[str, Any]:
    gallery_images = []
    for src, alt in _extract_all(r'<img src="([^"]+)" alt="([^"]*)">', _extract(
        r'<section class="service-gallery-section">(.*?)</section>',
        html,
    )):
        if alt:
            gallery_images.append({"path": src, "alt": alt})

    features = [
        {"title": title, "text": _clean_html(text)}
        for title, text in _extract_all(
            r"<strong>(.*?)</strong>\s*<span>(.*?)</span>",
            _extract(r'<div class="feature-list">(.*?)</div>\s*</article>', html),
        )
    ]

    points = [
        {"title": title, "text": _clean_html(text)}
        for title, text in _extract_all(
            r'<div class="mini-point">\s*<strong>(.*?)</strong>\s*<span>(.*?)</span>\s*</div>',
            html,
        )
    ]

    badges = re.findall(
        r'<span class="badge">(.*?)</span>',
        _extract(r'<div class="service-badges">(.*?)</div>', html),
        re.S,
    )

    about_section = _extract(
        r'<article class="about-card reveal">(.*?)</article>',
        html,
    )
    contact_section = _extract(
        r'<article class="contact-card reveal">(.*?)</article>\s*</div>\s*</section>',
        html,
    )
    cta_section = _extract(r'<div class="cta-card reveal">(.*?)</div>\s*</div>\s*</section>', html)

    return {
        "seo": {
            "title": _extract(r"<title>(.*?)</title>", html),
            "description": _extract(r'<meta name="description" content="([^"]*)">', html),
            "canonical_url": _extract(r'<link rel="canonical" href="([^"]*)">', html),
            "og_title": _extract(r'<meta property="og:title" content="([^"]*)">', html),
            "og_description": _extract(r'<meta property="og:description" content="([^"]*)">', html),
            "og_image": _extract(r'<meta property="og:image" content="([^"]*)">', html),
        },
        "hero": {
            "eyebrow": _extract(r'<div class="eyebrow">(.*?)</div>', html),
            "title": _extract(r"<h1>(.*?)</h1>", html),
            "lead": _clean_html(_extract(r'<p class="lead">(.*?)</p>', html)),
            "points": points,
            "image": {
                "path": _extract(r'<div class="service-hero-photo-card">\s*<img src="([^"]+)"', html),
                "alt": _extract(r'<div class="service-hero-photo-card">\s*<img src="[^"]+" alt="([^"]+)"', html),
            },
            "badge": _extract(r'<div class="service-hero-badge">(.*?)</div>', html),
            "badges": badges,
        },
        "gallery": {
            "title": _extract(r'<section class="service-gallery-section">.*?<h2>(.*?)</h2>', html),
            "description": _clean_html(
                _extract(r'<section class="service-gallery-section">.*?<p>\s*(.*?)\s*</p>', html)
            ),
            "images": gallery_images,
        },
        "about": {
            "title": _extract(r"<h2>(.*?)</h2>", about_section),
            "text": _clean_html(_extract(r"</div>\s*<p>\s*(.*?)\s*</p>", about_section)),
            "features": features,
        },
        "contact": {
            "title": _extract(r"<h2>(.*?)</h2>", contact_section),
            "text": _clean_html(_extract(r"</div>\s*<p>\s*(.*?)\s*</p>", contact_section)),
        },
        "cta": {
            "title": _extract(r'<h2 class="cta-title">(.*?)</h2>', cta_section),
            "text": _clean_html(_extract(r"<p>(.*?)</p>", cta_section)),
        },
        "meta": {
            "slug": slug,
            "kind": "service",
        },
    }


def parse_home_page(html: str) -> dict[str, Any]:
    reviews_section = _extract(r'<section id="reseñas">(.*?)</section>', html)
    service_cards_section = _extract(r'<div class="services-grid">(.*?)</div>\s*</div>\s*</section>', html)
    service_cards = []
    for href, image, alt, title, description, bullets_html in _extract_all(
        r'<a class="service-card reveal" href="([^"]+)">.*?<img src="([^"]+)" alt="([^"]+)">.*?<h3>(.*?)</h3>\s*<p>(.*?)</p>\s*<ul>(.*?)</ul>',
        service_cards_section,
    ):
        bullets = re.findall(r"<li>(.*?)</li>", bullets_html, re.S)
        service_cards.append(
            {
                "href": href,
                "image": {"path": image, "alt": alt},
                "title": title,
                "text": _clean_html(description),
                "bullets": [_clean_html(item) for item in bullets],
            }
        )

    hero_points = [
        {"title": title, "text": _clean_html(text)}
        for title, text in _extract_all(
            r'<div class="mini-point">\s*<strong>(.*?)</strong>\s*<span>(.*?)</span>\s*</div>',
            html,
        )
    ]
    hero_quick = [
        {"title": title, "text": _clean_html(text)}
        for title, text in _extract_all(
            r'<div class="hero-quick-item">\s*<strong>(.*?)</strong>\s*<span>(.*?)</span>\s*</div>',
            html,
        )
    ]
    if len(hero_points) < 3:
        hero_points = HOME_HERO_POINTS_FALLBACK
    if len(hero_quick) < 3:
        hero_quick = HOME_HERO_QUICK_FALLBACK
    features = [
        {"title": title, "text": _clean_html(text)}
        for title, text in _extract_all(
            r"<strong>(.*?)</strong>\s*<span>(.*?)</span>",
            _extract(r'<div class="feature-list">(.*?)</div>', _extract(r'<section id="ventajas">(.*?)</section>', html)),
        )
    ]
    reviews = [
        {"text": _clean_html(text), "author": author}
        for text, author in _extract_all(
            r'<div class="review-card">\s*<p>\s*(.*?)\s*</p>\s*<div class="review-meta">\s*<strong>(.*?)</strong>',
            _extract(r'<div class="reviews-slider">(.*)', reviews_section),
        )
    ]

    return {
        "seo": {
            "title": _extract(r"<title>(.*?)</title>", html),
            "description": _extract(r'<meta name="description" content="([^"]*)">', html),
            "canonical_url": _extract(r'<link rel="canonical" href="([^"]*)">', html),
            "og_title": _extract(r'<meta property="og:title" content="([^"]*)">', html),
            "og_description": _extract(r'<meta property="og:description" content="([^"]*)">', html),
            "og_image": _extract(r'<meta property="og:image" content="([^"]*)">', html),
            "twitter_title": _extract(r'<meta name="twitter:title" content="([^"]*)">', html),
            "twitter_description": _extract(r'<meta name="twitter:description" content="([^"]*)">', html),
            "twitter_image": _extract(r'<meta name="twitter:image" content="([^"]*)">', html),
        },
        "hero": {
            "eyebrow": _extract(r'<div class="eyebrow">(.*?)</div>', html),
            "title": _extract(r"<h1>(.*?)</h1>", html),
            "lead": _clean_html(_extract(r'<p class="lead">\s*(.*?)\s*</p>', html)),
            "points": hero_points,
            "image": {
                "path": _extract(r'<img\s+class="hero-media-fallback"\s+src="([^"]+)"', html),
                "alt": _extract(r'<img\s+class="hero-media-fallback"\s+src="[^"]+"\s+alt="([^"]+)"', html),
            },
            "quick_items": hero_quick,
        },
        "services": {
            "title": _extract(r'<section id="servicios">.*?<h2>(.*?)</h2>', html),
            "description": _clean_html(_extract(r'<section id="servicios">.*?</div>\s*<p>\s*(.*?)\s*</p>', html)),
            "cards": service_cards,
        },
        "advantages": {
            "title": _extract(r'<section id="ventajas">.*?<h2>(.*?)</h2>', html),
            "text": _clean_html(_extract(r'<section id="ventajas">.*?</div>\s*<p>\s*(.*?)\s*</p>', html)),
            "features": features,
            "image": {
                "path": _extract(r'<div class="about-photo">\s*<img src="([^"]+)"', html),
                "alt": _extract(r'<div class="about-photo">\s*<img src="[^"]+" alt="([^"]+)"', html),
            },
        },
        "contact": {
            "title": _extract(r'<article class="contact-card reveal" id="contacto">.*?<h2>(.*?)</h2>', html),
            "text": _clean_html(_extract(r'<article class="contact-card reveal" id="contacto">.*?</div>\s*<p>\s*(.*?)\s*</p>', html)),
            "map_title": _extract(r'<section id="mapa">.*?<h2>(.*?)</h2>', html),
            "map_text": _clean_html(_extract(r'<section id="mapa">.*?</div>\s*<p>\s*(.*?)\s*</p>', html)),
        },
        "reviews": {
            "title": _extract(r'<h2>(.*?)</h2>', reviews_section),
            "text": _clean_html(_extract(r'<h2>.*?</h2>\s*<p>\s*(.*?)\s*</p>', reviews_section)),
            "score": _extract(r'<strong>(.*?)</strong>', reviews_section),
            "score_detail": _extract(r'<strong>.*?</strong>\s*<span>(.*?)</span>', reviews_section),
            "items": reviews,
        },
        "cta": {
            "title": _extract(r'<section>\s*<div class="wrap">\s*<div class="cta-card reveal">.*?<h2 class="cta-title">(.*?)</h2>', html),
            "text": _clean_html(_extract(r'<h2 class="cta-title">.*?</h2>\s*<p>(.*?)</p>', html)),
        },
        "meta": {
            "slug": "home",
            "kind": "home",
        },
    }


def import_existing_site(force: bool = False) -> None:
    initialize_database()
    with get_connection() as conn:
        current = conn.execute("SELECT slug, content_json FROM pages").fetchall()
        if current and not force and all(json.loads(row["content_json"]) for row in current if row["slug"] in PAGE_DEFINITIONS):
            return

        home_html = (BASE_DIR / "index.html").read_text(encoding="utf-8")
        home_content = parse_home_page(home_html)
        conn.execute(
            "UPDATE pages SET content_json = ?, title = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = 'home'",
            (json.dumps(home_content, ensure_ascii=False), PAGE_DEFINITIONS["home"]["label"]),
        )

        settings_row = conn.execute(
            "SELECT content_json FROM pages WHERE slug = 'site-settings'"
        ).fetchone()
        if settings_row and not json.loads(settings_row["content_json"]):
            conn.execute(
                "UPDATE pages SET content_json = ?, title = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = 'site-settings'",
                (json.dumps(SITE_SETTINGS_DEFAULT, ensure_ascii=False), PAGE_DEFINITIONS["site-settings"]["label"]),
            )

        for slug, meta in SERVICE_PAGES.items():
            html = (BASE_DIR / meta["path"]).read_text(encoding="utf-8")
            content = parse_service_page(html, slug)
            conn.execute(
                "UPDATE pages SET content_json = ?, title = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ?",
                (json.dumps(content, ensure_ascii=False), meta["label"], slug),
            )

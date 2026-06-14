from __future__ import annotations

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "changeme123"

SERVICE_PAGES = {
    "neumaticos": {
        "label": "Neumáticos",
        "path": "servicios/neumaticos/index.html",
        "url": "/servicios/neumaticos/",
    },
    "mantenimiento-general": {
        "label": "Mantenimiento general",
        "path": "servicios/mantenimiento-general/index.html",
        "url": "/servicios/mantenimiento-general/",
    },
    "suspension-y-direccion": {
        "label": "Suspensión y dirección",
        "path": "servicios/suspension-y-direccion/index.html",
        "url": "/servicios/suspension-y-direccion/",
    },
    "baterias-para-coches": {
        "label": "Baterías para coches",
        "path": "servicios/baterias-para-coches/index.html",
        "url": "/servicios/baterias-para-coches/",
    },
    "frenos-y-pastillas": {
        "label": "Frenos y pastillas",
        "path": "servicios/frenos-y-pastillas/index.html",
        "url": "/servicios/frenos-y-pastillas/",
    },
    "pre-itv": {
        "label": "Pre ITV",
        "path": "servicios/pre-itv/index.html",
        "url": "/servicios/pre-itv/",
    },
}

SITE_SETTINGS_DEFAULT = {
    "contact": {
        "company_name": "Ybarra Motor Taller Mecánico",
        "phone_display": "644 047 147",
        "phone_href": "+34644047147",
        "email": "info@ybarra-motor.es",
        "whatsapp_number": "34678245670",
        "address_line": "Calle Rafaela Ybarra, 2, 48014 Bilbao",
        "street_address": "Calle Rafaela Ybarra, 2",
        "locality": "Bilbao",
        "postal_code": "48014",
        "country": "ES",
        "directions_url": "https://www.google.com/maps/dir/?api=1&destination=Calle+Rafaela+Ybarra+2,+48014+Bilbao",
        "map_search_url": "https://www.google.com/maps/search/?api=1&query=Calle+Rafaela+Ybarra+2,+48014+Bilbao",
        "map_embed_url": "https://maps.google.com/maps?q=Calle%20Rafaela%20Ybarra%202%2C%2048014%20Bilbao&t=&z=16&ie=UTF8&iwloc=&output=embed",
    },
    "schedule": {
        "monday": {"label": "Lunes", "closed": False, "morning_open": "08:30", "morning_close": "13:00", "afternoon_open": "15:00", "afternoon_close": "19:00"},
        "tuesday": {"label": "Martes", "closed": False, "morning_open": "08:30", "morning_close": "13:00", "afternoon_open": "15:00", "afternoon_close": "19:00"},
        "wednesday": {"label": "Miércoles", "closed": False, "morning_open": "08:30", "morning_close": "13:00", "afternoon_open": "15:00", "afternoon_close": "19:00"},
        "thursday": {"label": "Jueves", "closed": False, "morning_open": "08:30", "morning_close": "13:00", "afternoon_open": "15:00", "afternoon_close": "19:00"},
        "friday": {"label": "Viernes", "closed": False, "morning_open": "08:30", "morning_close": "15:00", "afternoon_open": "", "afternoon_close": ""},
        "saturday": {"label": "Sábado", "closed": True, "morning_open": "", "morning_close": "", "afternoon_open": "", "afternoon_close": ""},
        "sunday": {"label": "Domingo", "closed": True, "morning_open": "", "morning_close": "", "afternoon_open": "", "afternoon_close": ""},
        "closed_note": "Cerrado en festivos oficiales de Euskadi, Bizkaia y Bilbao, además de San Pedro de Deusto.",
    },
}

PAGE_DEFINITIONS = {
    "home": {
        "label": "Inicio",
        "kind": "home",
        "path": "index.html",
        "url": "/",
    },
    "site-settings": {
        "label": "Настройки сайта",
        "kind": "settings",
        "path": "",
        "url": "",
    },
    **{
        slug: {
            "label": meta["label"],
            "kind": "service",
            "path": meta["path"],
            "url": meta["url"],
        }
        for slug, meta in SERVICE_PAGES.items()
    },
}

HOME_HERO_POINTS_FALLBACK = [
    {
        "title": "Rapidez",
        "text": "Trabajamos para que tu vehículo vuelva a estar listo lo antes posible.",
    },
    {
        "title": "Montaje y revisión",
        "text": "Atención al detalle en neumáticos, frenos, batería y mantenimiento general.",
    },
    {
        "title": "Calidad y confianza",
        "text": "Servicio claro, trato cercano y soluciones pensadas para el uso real del coche.",
    },
]

HOME_HERO_QUICK_FALLBACK = [
    {
        "title": "Atención rápida",
        "text": "Trabajamos para que tu coche esté listo lo antes posible.",
    },
    {
        "title": "Taller multimarca",
        "text": "Servicio práctico para mantenimiento, frenos, neumáticos y revisión.",
    },
    {
        "title": "Ubicación cómoda",
        "text": "Calle Rafaela Ybarra, 2 · Bilbao",
    },
]

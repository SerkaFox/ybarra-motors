# Ybarra Motor Website

Website for **Ybarra Motor**, an automotive repair workshop in Bilbao, Spain.

The project is built as a fast static website with a small Python-based CMS for editing content and regenerating the public HTML pages.

## What The Site Does

- Presents workshop services, contact details, opening hours, map embeds, and customer review sections.
- Provides individual landing pages for each service category.
- Uses reusable header and footer includes loaded by JavaScript.
- Allows site content to be edited through a lightweight admin CMS.
- Regenerates static HTML after CMS edits, so public visitors still receive simple static pages.

## Tech Stack

- **HTML** for page markup.
- **CSS** for layout, responsive design, and visual styling.
- **Vanilla JavaScript** for shared includes, UI interactions, sliders, open-status logic, and small animations.
- **Python 3** for the mini CMS and static page generator.
- **SQLite** for CMS content storage on the server.
- **WSGI** entrypoint for running the CMS behind a web server.

No frontend framework or build step is required for the public site.

## Project Structure

```text
.
├── index.html                  # Homepage
├── servicios/                  # Static service pages
│   ├── neumaticos/
│   ├── mantenimiento-general/
│   ├── suspension-y-direccion/
│   ├── baterias-para-coches/
│   ├── frenos-y-pastillas/
│   └── pre-itv/
├── assets/
│   ├── css/                    # Main stylesheet
│   ├── js/                     # Site JavaScript
│   ├── img/                    # Site images and video assets
│   ├── favicon/                # Favicons and app icons
│   └── includes/               # Header and footer HTML includes
├── cms/                        # Python CMS and static generator
├── cms.wsgi                    # WSGI entrypoint for the CMS
├── cms_data/                   # Runtime SQLite database, ignored by git
├── robots.txt
├── sitemap.xml
└── README-CMS.md               # Detailed CMS usage notes
```

## How It Works

The public website is served as static HTML from the project root. This keeps the site simple, fast, and easy to host.

The CMS is a separate Python application. It stores editable content in SQLite, exposes an admin interface, and uses the generator in `cms/generator.py` to write updated static HTML files back into the public site.

In normal operation:

1. A visitor opens the static website.
2. The browser loads HTML, CSS, JavaScript, images, and shared includes.
3. An administrator edits content through the CMS.
4. The CMS saves the content to SQLite.
5. The generator rewrites the affected static HTML pages.
6. The public site continues to be served as static files.

## CMS Data

The runtime database is stored in:

```text
cms_data/site.db
```

This file is intentionally ignored by git because it can contain admin password hashes, sessions, and live content state.

To initialize a new database:

```bash
python3 -m cms.manage init
```

To change the admin password:

```bash
python3 -m cms.manage set-password YOUR_NEW_PASSWORD
```

More CMS-specific notes are available in `README-CMS.md`.

## Language

The public website content is currently written in Spanish for the Bilbao audience.

The codebase can support language changes by editing the static content through the CMS/default content files and regenerating the pages. A full multilingual switcher is not currently implemented, but the site structure is simple enough to add one by generating separate localized page trees, for example:

```text
/es/
/ru/
/en/
```

or by adding language-aware routing in the CMS generator.

## Deployment Notes

The public site can be served directly by Nginx, Apache, or any static file server.

The CMS requires a Python WSGI-compatible setup and can be mounted behind an admin route such as:

```text
/admin
```

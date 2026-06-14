# Ybarra Motor

Static website and mini CMS for Ybarra Motor, a car repair workshop in Bilbao.

## Structure

- `index.html` - homepage
- `servicios/` - static service pages
- `assets/` - CSS, JavaScript, images, favicon files, shared header/footer includes
- `cms/` - Python mini CMS used to edit content and regenerate static HTML
- `cms.wsgi` - WSGI entrypoint for the CMS
- `README-CMS.md` - CMS setup and usage notes

## Analytics

The site includes:

- Google Tag Manager: `GTM-T68P3M9M`
- Google Analytics 4 tag: `G-SNSXVJXFC6`

## CMS Data

Runtime CMS data is stored in `cms_data/site.db` on the server and is intentionally ignored by git. It can contain admin password hashes and session tokens.

To initialize a fresh CMS database:

```bash
python3 -m cms.manage init
```

After initialization, change the default admin password:

```bash
python3 -m cms.manage set-password YOUR_NEW_PASSWORD
```

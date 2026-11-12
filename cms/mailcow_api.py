from __future__ import annotations

import os
import secrets
from urllib3.exceptions import InsecureRequestWarning

import requests

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

DOMAIN = "ybarra-motor.es"
TIMEOUT = 10
PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def _config() -> tuple[str, str, str]:
    return (
        os.environ.get("MAILCOW_API_URL", "https://127.0.0.1:8443"),
        os.environ.get("MAILCOW_API_KEY", ""),
        os.environ.get("MAILCOW_API_HOST", "mail.ybarra-motor.es"),
    )


def is_configured() -> bool:
    _, key, _ = _config()
    return bool(key)


def _headers() -> dict:
    _, key, host = _config()
    return {"X-API-Key": key, "Host": host, "Content-Type": "application/json"}


def _url(path: str) -> str:
    base, _, _ = _config()
    return f"{base}{path}"


def generate_password(length: int = 16) -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


def _parse_result(resp: "requests.Response") -> tuple[bool, str]:
    try:
        data = resp.json()
    except ValueError:
        return False, f"HTTP {resp.status_code}: respuesta no válida del servidor de correo."
    entries = data if isinstance(data, list) else [data]
    messages: list[str] = []
    ok = bool(entries)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        msg = entry.get("msg")
        if isinstance(msg, list):
            msg = " ".join(str(part) for part in msg)
        if entry.get("type") != "success":
            ok = False
        if msg:
            messages.append(str(msg))
    if not messages:
        messages.append("OK" if ok else "Error desconocido del servidor de correo.")
    return ok, "; ".join(messages)


def list_mailboxes() -> list[dict]:
    resp = requests.get(
        _url(f"/api/v1/get/mailbox/all/{DOMAIN}"),
        headers=_headers(),
        verify=False,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    boxes = data if isinstance(data, list) else []
    boxes.sort(key=lambda item: item.get("username", ""))
    return boxes


def create_mailbox(local_part: str, password: str, full_name: str = "") -> tuple[bool, str]:
    payload = {
        "local_part": local_part,
        "domain": DOMAIN,
        "password": password,
        "password2": password,
        "name": full_name or local_part,
        "quota": "3072",
        "active": "1",
        "force_pw_update": "0",
        "tls_enforce_in": "1",
        "tls_enforce_out": "1",
    }
    resp = requests.post(
        _url("/api/v1/add/mailbox"),
        headers=_headers(),
        json=payload,
        verify=False,
        timeout=TIMEOUT,
    )
    return _parse_result(resp)


def list_app_passwords(email: str) -> list[dict]:
    resp = requests.get(
        _url(f"/api/v1/get/app-passwd/all/{email}"),
        headers=_headers(),
        verify=False,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def create_app_password(email: str, app_name: str, password: str) -> tuple[bool, str]:
    payload = {
        "active": "1",
        "username": email,
        "app_name": app_name or "Correo (Outlook/Gmail/móvil)",
        "app_passwd": password,
        "app_passwd2": password,
        "protocols": [
            "imap_access",
            "smtp_access",
            "pop3_access",
            "eas_access",
            "dav_access",
            "sieve_access",
        ],
    }
    resp = requests.post(
        _url("/api/v1/add/app-passwd"),
        headers=_headers(),
        json=payload,
        verify=False,
        timeout=TIMEOUT,
    )
    return _parse_result(resp)


def set_password(email: str, password: str) -> tuple[bool, str]:
    payload = {"items": [email], "attr": {"password": password, "password2": password}}
    resp = requests.post(
        _url("/api/v1/edit/mailbox"),
        headers=_headers(),
        json=payload,
        verify=False,
        timeout=TIMEOUT,
    )
    return _parse_result(resp)

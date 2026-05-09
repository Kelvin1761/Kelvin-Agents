from __future__ import annotations

import socket
from urllib.request import Request, urlopen


def run_network_check() -> dict:
    hosts = ["google.com", "sportsbet.com.au", "www.sportsbet.com.au"]
    return {
        "dns": {host: _resolve_host(host) for host in hosts},
        "https": {
            "google": _http_head("https://www.google.com"),
            "sportsbet_tennis": _http_head("https://www.sportsbet.com.au/betting/tennis"),
        },
        "diagnosis": _diagnose(hosts),
    }


def _resolve_host(host: str) -> dict:
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, 443)})
        return {"ok": True, "addresses": addresses[:5], "error": None}
    except Exception as exc:
        return {"ok": False, "addresses": [], "error": str(exc)}


def _http_head(url: str) -> dict:
    try:
        request = Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=10) as response:
            return {"ok": True, "status": response.status, "error": None}
    except Exception as exc:
        return {"ok": False, "status": None, "error": str(exc)}


def _diagnose(hosts: list[str]) -> str:
    results = [_resolve_host(host) for host in hosts]
    if not any(result["ok"] for result in results):
        return "system_dns_unavailable"
    if not _resolve_host("www.sportsbet.com.au")["ok"]:
        return "sportsbet_dns_unavailable"
    sportsbet = _http_head("https://www.sportsbet.com.au/betting/tennis")
    if not sportsbet["ok"]:
        return "sportsbet_https_unavailable"
    return "network_ready"

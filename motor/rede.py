"""Acesso HTTP (só biblioteca padrão): JSON com gzip e novas tentativas.
No Brasil o DNS bloqueia o Polymarket: com DOH=1 os hosts do Polymarket são resolvidos por DNS-over-HTTPS
(dns.google) — só para rodar no PC; a Action do GitHub (EUA) não precisa.
"""
import gzip
import json
import os
import socket
import time
import urllib.request

HOSTS_PM = ("gamma-api.polymarket.com", "clob.polymarket.com", "data-api.polymarket.com")
_ip = {}
_orig = socket.getaddrinfo


def _doh(host):
    if host not in _ip:
        with urllib.request.urlopen(f"https://dns.google/resolve?name={host}&type=A", timeout=20) as r:
            _ip[host] = [a["data"] for a in json.load(r).get("Answer", []) if a.get("type") == 1][0]
    return _ip[host]


if os.environ.get("DOH") == "1":
    def _resolver(host, *a, **kw):
        return _orig(_doh(host) if host in HOSTS_PM else host, *a, **kw)
    socket.getaddrinfo = _resolver


def get_json(url, ua="Mozilla/5.0", tentativas=4, espera=2.0, timeout=60):
    ultimo = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                b = r.read()
            if b[:2] == bytes([0x1F, 0x8B]):
                b = gzip.decompress(b)
            return json.loads(b.decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            ultimo = e
            if i < tentativas - 1:
                time.sleep(espera * (i + 1))
    raise RuntimeError(f"{url[:90]}: {ultimo}")

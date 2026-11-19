"""Polymarket: jogos de CS2 abertos (vencedor da série e de cada mapa), com o livro de agora (gamma-api).
Preço de A = meio do livro (bestBid/bestAsk); comprar A paga o bestAsk, comprar B paga 1 − bestBid.
"""
import calendar
import json
import re
import time
from datetime import datetime, timedelta, timezone

from rede import get_json

GAMMA = "https://gamma-api.polymarket.com"


def _ts(s):
    if not s:
        return None
    s = s.replace("T", " ").replace("Z", "")[:19]
    try:
        return calendar.timegm(time.strptime(s, "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return None


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def jogos(horas_antes=8, horas_depois=48):
    agora = datetime.now(timezone.utc)
    iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    evs = {}
    for off in range(0, 1000, 100):
        p = get_json(f"{GAMMA}/events?tag_slug=counter-strike-2&closed=false&limit=100&offset={off}"
                     f"&start_time_min={iso(agora - timedelta(hours=horas_antes))}"
                     f"&start_time_max={iso(agora + timedelta(hours=horas_depois))}")
        for e in p:
            evs[e["id"]] = e
        if len(p) < 100:
            break
    out = []
    for e in evs.values():
        titulo = e.get("title") or ""
        bo = re.search(r"\(BO(\d)\)", titulo)
        jogo = {"slug": e.get("slug"), "titulo": titulo, "evento": titulo.split(" - ", 1)[1] if " - " in titulo else "",
                "bo": int(bo.group(1)) if bo else None, "inicio": _ts(e.get("startTime")), "vol": _f(e.get("volume")) or 0,
                "serie": None, "mapas": {}}
        for m in e.get("markets") or []:
            tipo = m.get("sportsMarketType")
            if tipo not in ("moneyline", "child_moneyline"):
                continue
            try:
                times = json.loads(m.get("outcomes") or "[]")
            except ValueError:
                continue
            if len(times) != 2:
                continue
            bid, ask = _f(m.get("bestBid")), _f(m.get("bestAsk"))
            x = {"times": times, "bid": bid, "ask": ask, "ultimo": _f(m.get("lastTradePrice")),
                 "vol": _f(m.get("volumeNum")) or 0, "aberto": bool(m.get("acceptingOrders")) and not m.get("closed"),
                 "inicio": _ts(m.get("gameStartTime")) or jogo["inicio"]}
            x["meio"] = (bid + ask) / 2 if bid is not None and ask is not None and 0 < ask - bid <= 0.2 else None
            if tipo == "moneyline":
                jogo["serie"] = x
                jogo["inicio"] = x["inicio"] or jogo["inicio"]
            else:
                n = re.search(r"Map (\d)", m.get("question") or "")
                if n:
                    jogo["mapas"][int(n.group(1))] = x
        if jogo["serie"]:
            out.append(jogo)
    return sorted(out, key=lambda j: j["inicio"] or 0)

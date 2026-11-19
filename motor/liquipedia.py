"""Liquipedia (Counter-Strike): partidas do dia e resultados por mapa para atualizar a força dos times.
Termos da API: programa identificado (User-Agent), gzip, no máximo 1 requisição a cada 2 s e
action=parse no máximo 1 a cada 30 s. Aqui: 1 parse por rodada (a página Liquipedia:Matches) e consultas
de texto em lotes de 50 páginas só a cada poucas horas.
"""
import html
import re
import time
import urllib.parse

from rede import get_json

API = "https://liquipedia.net/counterstrike/api.php"
UA = "CS2Painel/0.1 (https://github.com/maxmox/CS2; projeto pessoal de pesquisa)"
PAUSA = 2.5
TIERS = ("S-Tier Tournaments", "A-Tier Tournaments", "B-Tier Tournaments", "C-Tier Tournaments")
_ultimo = [0.0, 0.0]  # última requisição comum, último parse


def api(**p):
    parse = p.get("action") in ("parse", "expandtemplates")
    espera = max(PAUSA - (time.time() - _ultimo[0]), (31 - (time.time() - _ultimo[1])) if parse else 0)
    if espera > 0:
        time.sleep(espera)
    p.update(format="json", formatversion="2")
    try:
        return get_json(API + "?" + urllib.parse.urlencode(p), ua=UA, tentativas=3, espera=20)
    finally:
        _ultimo[0] = time.time()
        if parse:
            _ultimo[1] = time.time()


# ---------- partidas (Liquipedia:Matches) ----------

def _texto(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def partidas():
    """Cartões da página de partidas: [{inicio, bo, fase, a, b, a_pag, b_pag, placar_a, placar_b, venceu, torneio,
    torneio_pag}] (a_pag = título da página do time na Liquipedia = nome oficial; vazio para TBD)."""
    t = api(action="parse", page="Liquipedia:Matches", prop="text")["parse"]["text"]
    t = t.replace("&#95;", "_")
    out = []
    for c in t.split('class="match-ticker-card"')[1:]:
        c = re.sub(r"<img[^>]*>", "", c)
        ts = re.search(r'data-timestamp="(\d+)"', c)
        if not ts:
            continue
        cab = re.search(r'match-ticker-card__header">.*?</span></span><div>(.*?)</div>', c, re.S)
        cab = _texto(cab.group(1)) if cab else ""
        bo = re.search(r"Bo(\d)", cab)
        fase = re.sub(r"\s*-?\s*Bo\d\s*$", "", cab).strip(" -")
        marcas = list(re.finditer(r'class="match-ticker-card__opponent( winner)?"', c))
        ops = []
        for k, mk in enumerate(marcas[:2]):
            o = c[mk.end(): marcas[k + 1].start() if k + 1 < len(marcas) else len(c)]
            nome = re.search(r'<div class="team-name">(.*?)</div>', o)
            pag = re.search(r'team-name-dynamic"[^>]*><a href="[^"]*" title="([^"]*)"', o)
            pl = re.search(r'</span></div><div>([^<]*)</div>', o)
            ops.append({"winner": bool(mk.group(1)), "nome": _texto(nome.group(1)) if nome else "",
                        "pag": html.unescape(pag.group(1)) if pag else "", "placar": pl.group(1).strip() if pl else ""})
        if len(ops) != 2:
            continue
        tor = re.search(r'match-ticker-card-tournament-name"><a href="/counterstrike/([^"#]*)[^"]*"[^>]*>(.*?)</a>', c, re.S)
        venceu = 0 if ops[0]["winner"] else 1 if ops[1]["winner"] else None
        out.append({"inicio": int(ts.group(1)), "bo": int(bo.group(1)) if bo else None, "fase": fase,
                    "a": ops[0]["nome"], "b": ops[1]["nome"], "a_pag": ops[0]["pag"], "b_pag": ops[1]["pag"],
                    "placar_a": ops[0]["placar"], "placar_b": ops[1]["placar"], "venceu": venceu,
                    "torneio": _texto(tor.group(2)) if tor else "",
                    "torneio_pag": urllib.parse.unquote(tor.group(1)).replace("_", " ") if tor else ""})
    return out


# ---------- resultados por mapa (texto das páginas de torneio) ----------

def blocos(texto, nome):
    i, abre = 0, "{{" + nome
    while True:
        i = texto.find(abre, i)
        if i < 0:
            return
        if texto[i + len(abre): i + len(abre) + 1] not in ("|", "\n", " ", "}"):
            i += len(abre)
            continue
        n, j = 0, i
        while j < len(texto) - 1:
            if texto[j:j + 2] == "{{":
                n += 1
                j += 2
            elif texto[j:j + 2] == "}}":
                n -= 1
                j += 2
                if n == 0:
                    break
            else:
                j += 1
        yield texto[i:j]
        i = j


def campos(bloco):
    corpo, partes, n, atual = bloco[2:-2], [], 0, ""
    for k, ch in enumerate(corpo):
        if corpo[k:k + 2] in ("{{", "[["):
            n += 1
        elif corpo[k:k + 2] in ("}}", "]]"):
            n -= 1
        if ch == "|" and n <= 0:
            partes.append(atual)
            atual = ""
        else:
            atual += ch
    partes.append(atual)
    return {p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip() for p in partes[1:] if "=" in p}


def _int(v):
    v = re.sub(r"[^\d]", "", v or "")
    return int(v) if v else None


MESES = {m: i + 1 for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                                         "september", "october", "november", "december"))}


def data_iso(v):
    v = v or ""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", v)
    if m:
        return m.group(0)
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", v)
    if m and m.group(1).lower() in MESES:
        return f"{m.group(3)}-{MESES[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    return ""


def mapas_da_pagina(texto):
    """Cada {{Map}} jogado dentro de {{Match}}: data, apelidos dos times (TeamOpponent), mapa, rounds de cada lado."""
    out = []
    for mb in blocos(texto, "Match"):
        f = campos(mb)
        tm = [re.search(r"\{\{\s*TeamOpponent\s*\|\s*([^|}]+)", f.get(k) or "") for k in ("opponent1", "opponent2")]
        if not all(tm):
            continue
        t1, t2 = (x.group(1).strip().lower() for x in tm)
        data = data_iso(f.get("date"))
        for k, v in f.items():
            if not re.fullmatch(r"map\d+", k) or not v.startswith("{{Map"):
                continue
            g = campos(v)
            x = [_int(g.get(c)) for c in ("t1t", "t1ct", "t2t", "t2ct")]
            if None in x or g.get("t1firstside") not in ("t", "ct"):
                continue
            r1 = x[0] + x[1] + sum(_int(g.get(c)) or 0 for c in g if re.fullmatch(r"o\d+t1(t|ct)", c))
            r2 = x[2] + x[3] + sum(_int(g.get(c)) or 0 for c in g if re.fullmatch(r"o\d+t2(t|ct)", c))
            mapa = re.sub(r"[^a-z0-9]", "", (g.get("map") or "").lower()).replace("dustii", "dust2")
            if data and r1 != r2:
                out.append({"data": data, "time1": t1, "time2": t2, "mapa": mapa, "r1": r1, "r2": r2})
    return out


def subpaginas(titulos):
    """Página + subpáginas de cada torneio (1 consulta por torneio)."""
    out = set(titulos)
    for t in titulos:
        d = api(action="query", list="allpages", apprefix=t.replace(" ", "_") + "/", apnamespace=0, aplimit=200)
        out |= {p["title"] for p in d["query"]["allpages"]}
    return sorted(out)


def com_tier(titulos):
    """Quais páginas (ou uma página-mãe delas) estão nas categorias S/A/B/C-Tier (o mesmo recorte do treino)."""
    maes = {}
    for t in titulos:
        partes = t.split("/")
        maes[t] = ["/".join(partes[:k]) for k in range(len(partes), 0, -1)]
    todas = sorted({m for v in maes.values() for m in v})
    ok = set()
    for i in range(0, len(todas), 50):
        d = api(action="query", prop="categories", titles="|".join(todas[i:i + 50]), cllimit=500,
                clcategories="|".join("Category:" + c for c in TIERS))
        ok |= {p["title"] for p in d["query"]["pages"] if p.get("categories")}
    return {t for t, ms in maes.items() if any(m in ok for m in ms)}


def textos(titulos):
    out = {}
    for i in range(0, len(titulos), 50):
        d = api(action="query", prop="revisions", rvprop="content", rvslots="main", titles="|".join(titulos[i:i + 50]))
        for p in d["query"]["pages"]:
            if p.get("revisions"):
                out[p["title"]] = p["revisions"][0]["slots"]["main"]["content"]
    return out


def resolver_apelidos(nomes):
    """Apelido do TeamOpponent → página oficial do time ({{TeamPage|x}}), lotes de 100 (conta como parse)."""
    out = {}
    nomes = sorted(nomes)
    for i in range(0, len(nomes), 100):
        lote = nomes[i:i + 100]
        d = api(action="expandtemplates", prop="wikitext", text="§".join("{{TeamPage|%s}}" % n for n in lote))
        partes = d["expandtemplates"]["wikitext"].split("§")
        if len(partes) != len(lote):
            continue
        for n, p in zip(lote, partes):
            p = p.strip()
            out[n] = p if p and "<" not in p and "error" not in p.lower() else n
    return out

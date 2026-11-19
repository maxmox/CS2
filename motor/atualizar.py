"""Rodada do painel (Action a cada ~15 min, ou à mão):
  1) partidas da Liquipedia (1 parse) + jogos de CS2 abertos no Polymarket;
  2) casa os dois (horário ±3 h + nomes), preço do precificador (Elo) e mistura com o Polymarket;
  3) registro: o último preço antes do início de cada jogo (nosso e do Polymarket) e o resultado → data/registro/AAAA-MM.json;
  4) a cada 3 h: resultados novos por mapa (torneios S/A/B/C-Tier das partidas vistas) → força dos times (data/forca.json).
Saída do site: data/hoje.json.
  python motor/atualizar.py                 (rodada normal)
  python motor/atualizar.py resultados      (força a atualização da força dos times)
  DOH=1 python motor/atualizar.py           (no PC, no Brasil: Polymarket por DNS-over-HTTPS)
"""
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import forca as fz
import liquipedia as lq
import polymarket as pm
from rede import get_json

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA = os.path.join(RAIZ, "data")
ARQ_FORCA = os.path.join(DATA, "forca.json")
ARQ_APEL_LQ = os.path.join(DATA, "apelidos_liquipedia.json")  # apelido do TeamOpponent → página oficial
ARQ_APEL = os.path.join(DATA, "apelidos.json")                # nome no Polymarket → time da Liquipedia (à mão/aprendido)
ARQ_ESTADO = os.path.join(DATA, "estado.json")
ARQ_CONFIG = os.path.join(DATA, "config.json")
ARQ_HOJE = os.path.join(DATA, "hoje.json")
BRT = timezone(timedelta(hours=-3))
INTERVALO_RESULTADOS = 3 * 3600
JANELA = (-8 * 3600, 40 * 3600)  # o que aparece no painel: começou há até 8 h … começa em até 40 h
PUBLICADO = os.environ.get("PUBLICADO", "")  # na Action: https://maxmox.github.io/CS2 (estado e registro vivem no site)
ARQ_COMMIT = os.path.join(DATA, ".commit")    # existe = a Action deve guardar força/apelidos/registro no repositório


def ler(arq, padrao):
    try:
        return json.load(open(arq, encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def gravar(arq, obj, compacto=False):
    tmp = arq + ".tmp"
    json.dump(obj, open(tmp, "w", encoding="utf-8"), ensure_ascii=False,
              **({"separators": (",", ":")} if compacto else {"indent": 1}))
    os.replace(tmp, arq)


def mistura(p_pm, p_nosso, w):
    if p_pm is None:
        return p_nosso
    if p_nosso is None:
        return p_pm
    z = fz.logit(p_pm) + w * (fz.logit(p_nosso) - fz.logit(p_pm))
    return 1 / (1 + math.exp(-z))


# ---------- força dos times ----------

def atualizar_forca(F, partidas, estado, apel_lq):
    agora = int(time.time())
    vistos = estado.setdefault("torneios", {})
    for p in partidas:
        if p["torneio_pag"] and p["inicio"] <= agora + 3600:
            vistos[p["torneio_pag"]] = max(vistos.get(p["torneio_pag"], 0), min(p["inicio"], agora))
    lim = agora - 10 * 86400
    for t in [t for t, ts in vistos.items() if ts < lim]:
        del vistos[t]
    alvo = sorted(vistos)
    print(f"resultados: {len(alvo)} torneios recentes")
    paginas = lq.subpaginas(alvo)
    tier = sorted(lq.com_tier(paginas))
    print(f"  {len(paginas)} páginas, {len(tier)} de torneios S/A/B/C-Tier")
    mapas = [m for txt in lq.textos(tier).values() for m in lq.mapas_da_pagina(txt)]
    novos = {t for m in mapas for t in (m["time1"], m["time2"]) if t not in apel_lq}
    if novos:
        print(f"  {len(novos)} apelidos novos de time → nome oficial")
        apel_lq.update(lq.resolver_apelidos(novos))
        gravar(ARQ_APEL_LQ, dict(sorted(apel_lq.items())), compacto=True)
    corte = (datetime.fromisoformat(F.s["ate"]) - timedelta(days=21)).date().isoformat()
    n = 0
    for m in sorted(mapas, key=lambda m: m["data"]):
        m["time1"], m["time2"] = apel_lq.get(m["time1"], m["time1"]), apel_lq.get(m["time2"], m["time2"])
        if m["data"] > corte and m["time1"] != m["time2"] and F.aplicar(m):
            n += 1
    F.salvar()
    estado["resultados_em"] = agora
    print(f"  {n} mapas novos aplicados (dados até {F.s['ate']})")
    return n


# ---------- casar Polymarket × Liquipedia ----------

def casar(jogos_pm, partidas, N):
    """Para cada jogo do Polymarket, o cartão da Liquipedia do mesmo jogo (±3 h, os dois times) e a orientação."""
    usados = set()
    for j in jogos_pm:
        a, b = j["serie"]["times"]
        ca, cb = N.achar(a), N.achar(b)
        na, nb = fz.norm(a), fz.norm(b)
        melhor = None
        for i, p in enumerate(partidas):
            if i in usados or not j["inicio"] or abs(p["inicio"] - j["inicio"]) > 3 * 3600:
                continue
            pa, pb = p["a_pag"] or p["a"], p["b_pag"] or p["b"]

            def igual(x, cx, nx, y):
                return (cx and cx == y) or fz.nivel(nx, fz.norm(y)) < 9

            if igual(a, ca, na, pa) and igual(b, cb, nb, pb):
                melhor = (i, False)
            elif igual(a, ca, na, pb) and igual(b, cb, nb, pa):
                melhor = (i, True)
            if melhor:
                break
        if melhor:
            usados.add(melhor[0])
            j["liq"], j["inv"] = melhor
    return usados


def linha(F, N, w, agora, pj=None, card=None, inv=False):
    """Uma partida do painel (pj = jogo do Polymarket, card = cartão da Liquipedia; A = 1º time do Polymarket)."""
    if pj:
        a, b = pj["serie"]["times"]
    else:
        a, b = card["a"], card["b"]
    la = lb = None
    if card:
        pa, pb = (card["b_pag"], card["a_pag"]) if inv else (card["a_pag"], card["b_pag"])
        la, lb = (pa if pa in F.T else None), (pb if pb in F.T else None)
    nv_a = nv_b = 0
    if not la:
        la, nv_a = N.achar_nivel(a)
    if not lb:
        lb, nv_b = N.achar_nivel(b)
    bo = (card or {}).get("bo") or (pj or {}).get("bo") or 3
    inicio = (pj or {}).get("inicio") or card["inicio"]
    nosso = F.preco(la, lb, bo) if la and lb and la != lb else None
    ta, tb = F.T.get(la, {}), F.T.get(lb, {})
    out = {"inicio": inicio, "bo": bo, "a": a, "b": b, "a_liq": la, "b_liq": lb, "nivel": [nv_a, nv_b],
           "n_a": ta.get("n", 0), "n_b": tb.get("n", 0), "ult_a": ta.get("ult"), "ult_b": tb.get("ult"),
           "torneio": (card or {}).get("torneio") or (pj or {}).get("evento", ""), "fase": (card or {}).get("fase", ""),
           "nosso": nosso, "pm": None, "mapas": [], "slug": (pj or {}).get("slug")}
    if card:
        pa_, pb_ = (card["placar_b"], card["placar_a"]) if inv else (card["placar_a"], card["placar_b"])
        out["placar"] = [pa_, pb_] if (pa_ or pb_) else None
        v = card["venceu"]
        out["venceu"] = None if v is None else (1 - v if inv else v)
    st = "a começar" if inicio > agora else "ao vivo"
    if out.get("venceu") is not None:
        st = "encerrado"
    out["status"] = st
    if pj:
        s = pj["serie"]
        out["pm"] = {k: s[k] for k in ("meio", "bid", "ask", "ultimo", "vol", "aberto")}
        out["justa"] = mistura(s["meio"], nosso, w)
        out["fonte"] = "pm" if s["meio"] is not None else ("nosso" if nosso is not None else None)
        p_mapa = None
        if la and lb and la != lb:
            p_mapa = F.preco(la, lb, 1)
        for k, mm in sorted(pj["mapas"].items()):
            out["mapas"].append({"mapa": k, "meio": mm["meio"], "bid": mm["bid"], "ask": mm["ask"], "vol": mm["vol"],
                                 "aberto": mm["aberto"], "nosso": p_mapa, "justa": mistura(mm["meio"], p_mapa, w)})
    else:
        out["justa"] = nosso
        out["fonte"] = "nosso" if nosso is not None else None
    return out


# ---------- registro (para medir depois) ----------

def registrar(linhas, agora):
    """Guarda, de cada jogo, o último preço visto ANTES do início (até 2 h antes) e depois o resultado."""
    mudou = set()
    for l in linhas:
        if not (l["a_liq"] or l["pm"]):
            continue
        mes = datetime.fromtimestamp(l["inicio"], BRT).strftime("%Y-%m")
        arq = os.path.join(DATA, "registro", f"{mes}.json")
        reg = registrar.cache.get(arq)
        if reg is None:
            reg = registrar.cache[arq] = ler(arq, {})
        k = f"{l['inicio']}|{l['a']}|{l['b']}"
        r = reg.get(k)
        if l["status"] == "a começar" and l["inicio"] - agora <= 2 * 3600:
            novo = {"inicio": l["inicio"], "visto": agora, "bo": l["bo"], "a": l["a"], "b": l["b"],
                    "a_liq": l["a_liq"], "b_liq": l["b_liq"], "n_a": l["n_a"], "n_b": l["n_b"], "torneio": l["torneio"],
                    "nosso": l["nosso"], "pm_meio": (l["pm"] or {}).get("meio"), "pm_ask": (l["pm"] or {}).get("ask"),
                    "pm_bid": (l["pm"] or {}).get("bid"), "pm_vol": (l["pm"] or {}).get("vol"), "justa": l["justa"],
                    "venceu": None}
            if r != novo:
                reg[k] = novo
                mudou.add(arq)
        elif r and r.get("venceu") is None and l.get("venceu") is not None:
            r["venceu"] = l["venceu"]
            mudou.add(arq)
    for arq in mudou:
        os.makedirs(os.path.dirname(arq), exist_ok=True)
        gravar(arq, registrar.cache[arq])
    return len(mudou)


registrar.cache = {}


def sincronizar(agora):
    """Na Action: o estado rápido (partidas, hora da última atualização da força) e o registro do mês ficam no site
    publicado; o repositório só recebe commit a cada atualização da força (3 h). Junta o publicado com o do repositório."""
    if not PUBLICADO:
        return
    try:
        pub = get_json(f"{PUBLICADO}/data/estado.json?t={agora}", tentativas=2)
        loc = ler(ARQ_ESTADO, {})
        if pub.get("partidas_em", 0) >= loc.get("partidas_em", 0):
            gravar(ARQ_ESTADO, pub)
    except Exception as e:  # noqa: BLE001
        print("estado publicado não lido:", e)
    for d in (0, -20):  # mês de agora e o anterior (virada do mês)
        mes = datetime.fromtimestamp(agora + d * 86400, BRT).strftime("%Y-%m")
        arq = os.path.join(DATA, "registro", f"{mes}.json")
        try:
            pub = get_json(f"{PUBLICADO}/data/registro/{mes}.json?t={agora}", tentativas=2)
        except Exception:  # noqa: BLE001
            continue
        loc = ler(arq, {})
        for k, v in pub.items():
            r = loc.get(k)
            if r is None or (v.get("venceu") is not None and r.get("venceu") is None) or                     (r.get("venceu") is None and v.get("visto", 0) > r.get("visto", 0)):
                loc[k] = v
        os.makedirs(os.path.dirname(arq), exist_ok=True)
        gravar(arq, loc)


def main():
    agora = int(time.time())
    sincronizar(agora)
    estado = ler(ARQ_ESTADO, {})
    config = ler(ARQ_CONFIG, {"w_mistura": 0.0})
    apel_lq = ler(ARQ_APEL_LQ, {})
    F = fz.Forca(ARQ_FORCA)
    N = fz.Nomes(F, ler(ARQ_APEL, {}))
    erros = []
    try:
        partidas = lq.partidas()
        estado["partidas"] = partidas
        estado["partidas_em"] = agora
    except Exception as e:  # noqa: BLE001
        erros.append(f"Liquipedia: {e}")
        partidas = estado.get("partidas", [])
    try:
        jogos_pm = pm.jogos()
    except Exception as e:  # noqa: BLE001
        erros.append(f"Polymarket: {e}")
        jogos_pm = []
    if "resultados" in sys.argv or agora - estado.get("resultados_em", 0) >= INTERVALO_RESULTADOS:
        try:
            if atualizar_forca(F, partidas, estado, apel_lq):
                N = fz.Nomes(F, ler(ARQ_APEL, {}))
            open(ARQ_COMMIT, "w").write(str(agora))
        except Exception as e:  # noqa: BLE001
            erros.append(f"resultados: {e}")
    usados = casar(jogos_pm, partidas, N)
    w = config.get("w_mistura", 0.0)
    linhas = []
    for j in jogos_pm:
        card = partidas[j["liq"]] if "liq" in j else None
        linhas.append(linha(F, N, w, agora, j, card, j.get("inv", False)))
    for i, p in enumerate(partidas):
        if i in usados or not p["a_pag"] or not p["b_pag"]:
            continue  # TBD fica de fora
        linhas.append(linha(F, N, w, agora, None, p))
    linhas = [l for l in linhas if JANELA[0] <= l["inicio"] - agora <= JANELA[1]]
    linhas.sort(key=lambda l: (l["inicio"], l["a"]))
    n_reg = registrar(linhas, agora)
    gravar(ARQ_ESTADO, estado)
    gravar(ARQ_HOJE, {"gerado": agora, "forca_ate": F.s["ate"], "w_mistura": w, "erros": erros,
                      "parametros": F.par, "jogos": linhas})
    sem = sum(1 for l in linhas if l["nosso"] is None)
    print(f"painel: {len(linhas)} jogos ({sum(1 for l in linhas if l['pm'])} com Polymarket, "
          f"{len(usados)} casados com a Liquipedia, {sem} sem preço nosso) · registro: {n_reg} arquivo(s)")
    for e in erros:
        print("ERRO", e)


if __name__ == "__main__":
    main()

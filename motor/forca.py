"""Força dos times (Elo por mapa) e preço pré-jogo de uma série.
Mesma conta do precificador do projeto (validado: parâmetros em 2025, teste em 2026, BO3 log-loss 0,633):
  - K 24 (×(1 + 2·e^(−mapas/15)) para time novo), fator de margem de rounds (α 1), ajuste por mapa (K 8), novo 1400;
  - série por mapas independentes (BO3 = p²(3−2p), BO5 = p³(10−15p+6p²)) + calibração logística por formato.
Estado em data/forca.json: {parametros, calibracao, ate, aplicados: [chaves de mapas recentes], times: {nome: {r, n, ult, mp}}}
"""
import json
import math
import re
from datetime import date


def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def p_serie(p, bo):
    if bo == 1:
        return p
    if bo == 3:
        return p * p * (3 - 2 * p)
    if bo == 5:
        return p ** 3 * (10 - 15 * p + 6 * p * p)
    return p


def chave_mapa(m):
    return "|".join(str(x) for x in (m["data"], m["time1"], m["time2"], m["mapa"], m["r1"], m["r2"]))


class Forca:
    def __init__(self, arq):
        self.arq = arq
        self.s = json.load(open(arq, encoding="utf-8"))
        self.par = self.s["parametros"]
        self.T = self.s["times"]
        self.aplicados = set(self.s.get("aplicados", []))

    def salvar(self):
        lim = str(date.fromordinal(date.fromisoformat(self.s["ate"]).toordinal() - 30))
        self.s["aplicados"] = sorted(k for k in self.aplicados if k[:10] >= lim)
        json.dump(self.s, open(self.arq, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    def r(self, t):
        return self.T[t]["r"] if t in self.T else self.par["novo"]

    def p_mapa(self, a, b, mapa=None):
        d = self.r(a) - self.r(b)
        if mapa and a in self.T and b in self.T:
            d += self.T[a]["mp"].get(mapa, 0) - self.T[b]["mp"].get(mapa, 0)
        return 1 / (1 + 10 ** (-d / 400))

    def aplicar(self, m):
        """Atualiza com um mapa jogado {data, time1, time2, mapa, r1, r2} (nomes oficiais). Devolve False se já estava."""
        k = chave_mapa(m)
        if k in self.aplicados:
            return False
        a, b, P = m["time1"], m["time2"], self.par
        s = 1.0 if m["r1"] > m["r2"] else 0.0
        e = self.p_mapa(a, b, m["mapa"])
        marg = (1 + P["alfa"] * math.log1p(abs(m["r1"] - m["r2"]))) / (1 + P["alfa"] * math.log1p(6))
        for t, sinal in ((a, 1), (b, -1)):
            x = self.T.setdefault(t, {"r": P["novo"], "n": 0, "ult": None, "mp": {}})
            k_t = P["K"] * (1 + P["prov"] * math.exp(-x["n"] / 15))
            x["r"] = round(x["r"] + sinal * k_t * marg * (s - e), 2)
            if m["mapa"]:
                x["mp"][m["mapa"]] = round(x["mp"].get(m["mapa"], 0) + sinal * P["Kmapa"] * (s - e), 2)
            x["n"] += 1
            x["ult"] = max(x["ult"] or "", m["data"])
        self.aplicados.add(k)
        self.s["ate"] = max(self.s["ate"], m["data"])
        return True

    def preco(self, a, b, bo=3, mapa=None):
        """Chance de a vencer (série ou, com mapa, só aquele mapa), calibrada pelo formato."""
        p = p_serie(self.p_mapa(a, b, mapa), 1 if mapa else bo)
        cal = self.s["calibracao"].get(str(1 if mapa else bo))
        if cal:
            p = 1 / (1 + math.exp(-(cal[0] + cal[1] * logit(p))))
        return p


# ---------- nomes de outras fontes (Polymarket) → time da Liquipedia ----------

RUIDO = r"(esports?|e-sports|gaming|team|club|clan|fe|cs|gg)"


def norm(n):
    return re.sub(r"[^a-z0-9]", "", re.sub(RUIDO, " ", (n or "").lower()))


def subseq(curto, longo):
    if not curto or not longo or curto[0] != longo[0]:
        return False
    it = iter(longo)
    return all(c in it for c in curto)


def nivel(a, b):
    """0 igual, 1 um começa com o outro (3+ letras), 2 letras em sequência (3+), 9 diferente (a e b já normalizados)."""
    if not a or not b:
        return 9
    if a == b:
        return 0
    curto_, longo_ = sorted((a, b), key=len)
    if len(curto_) >= 4 and len(curto_) >= 0.5 * len(longo_) and longo_.startswith(curto_):
        return 1
    curto, longo = sorted((a, b), key=len)
    return 2 if len(curto) >= 3 and subseq(curto, longo) else 9


class Nomes:
    """Acha o time da Liquipedia: apelido manual (data/apelidos.json) > nome parecido, preferindo quem jogou nos
    últimos 120 dias e tem mais mapas."""

    def __init__(self, forca, manual=None):
        self.f = forca
        self.manual = manual or {}
        self.idx = {t: norm(t) for t in forca.T}
        hoje = forca.s["ate"]
        self.lim = str(date.fromordinal(date.fromisoformat(hoje).toordinal() - 120))
        self.cache = {}

    def achar(self, nome):
        return self.achar_nivel(nome)[0]

    def achar_nivel(self, nome):
        """(time, nível): 0 = nome igual ou apelido conhecido, 1 = começa igual, 2 = abreviação (conferir), None."""
        if nome in self.cache:
            return self.cache[nome]
        T = self.f.T
        if nome in self.manual:
            r = (self.manual[nome], 0) if self.manual[nome] in T else (None, None)
        elif nome in T:
            r = (nome, 0)
        else:
            alvo = norm(nome)
            cand = [(nivel(n, alvo), t) for t, n in self.idx.items()]
            # aproximado (1–2) só entre os times ativos (jogaram nos últimos 120 dias)
            # abreviação por letras em sequência (nível 2) errava mais do que acertava (ASTRON → ASTERIX DIVISION):
            # fica de fora; esses casos vão para data/apelidos.json
            cand = [c for c in cand if c[0] == 0 or (c[0] == 1 and (T[c[1]].get("ult") or "") >= self.lim)]
            r = (None, None)
            if cand:
                c = min(cand, key=lambda c: (c[0], (T[c[1]].get("ult") or "") < self.lim, -T[c[1]]["n"]))
                r = (c[1], c[0])
        self.cache[nome] = r
        return r

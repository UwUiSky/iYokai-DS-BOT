"""
tests/support/ai_finto.py
=========================
Fornitore AI finto per i test: nessuna rete, nessuna chiave vera. Le
chiavi dei fornitori finti si costruiscono a runtime (mai stringhe che
somigliano a una chiave reale).
"""

from __future__ import annotations

from core.ai_providers import ErroreFornitore, EsitoChiamata, Fornitore, LimitiFornitore
from core.ai_router import MotoreAI
from core.ai_servizio import ServizioAI

# Un PNG 1x1 valido.
PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a4"
    "0000000049454e44ae426082"
)


def chiave_finta(nome: str) -> str:
    return "-".join(["finta", nome, "x" * 3])


def fornitore(nome="alfa", tipi=("chat", "testo", "traduzione", "giudizio"), fascia="bassa", **kw) -> Fornitore:
    return Fornitore(
        nome=nome, url=f"https://{nome}.example/v1", chiave=chiave_finta(nome), modello="modello-finto",
        tipi=frozenset(tipi), fascia=fascia, limiti=kw.pop("limiti", LimitiFornitore()), **kw,
    )


class TrasportoFinto:
    """Risponde con `risposte[nome]` (testo) o solleva `errori[nome]`. Registra ogni chiamata."""

    def __init__(self, risposte: dict | None = None, errori: dict | None = None) -> None:
        self.risposte = risposte or {}
        self.errori = errori or {}
        self.chiamate: list[tuple[str, object]] = []
        self.chiavi_valide: dict[str, bool] = {}

    async def completa(self, f, messaggi, max_token):
        self.chiamate.append((f.nome, messaggi))
        if f.nome in self.errori:
            raise self.errori[f.nome]
        testo = self.risposte.get(f.nome, f"risposta di {f.nome}")
        return EsitoChiamata(testo=testo(messaggi) if callable(testo) else testo, token_in=10, token_out=5)

    async def immagine(self, f, prompt):
        self.chiamate.append((f.nome, prompt))
        if f.nome in self.errori:
            raise self.errori[f.nome]
        return EsitoChiamata(immagine=PNG_1X1)

    async def controlla(self, f):
        return self.chiavi_valide.get(f.nome, True)


def servizio_finto(repo, fornitori=None, trasporto=None) -> tuple[ServizioAI, TrasportoFinto]:
    trasporto = trasporto or TrasportoFinto()
    motore = MotoreAI(fornitori if fornitori is not None else [fornitore()], trasporto)
    return ServizioAI(motore, repo=repo), trasporto


__all__ = ["ErroreFornitore", "PNG_1X1", "TrasportoFinto", "fornitore", "servizio_finto", "chiave_finta"]

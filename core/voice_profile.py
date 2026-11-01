"""
core/voice_profile.py
=====================
La voce di Yokai: i profili di contesto (PUBLIC, WELCOME, MODERATION, ANNOUNCEMENT, NSFW) e i quattro toni che sceglie
l'admin (dolce, scherzosa, provocante, piccante). I profili cambiano solo l'espressione (lentezza, variazione, pause,
equalizzazione): il timbro e l'intonazione di base no. `piccante` vale solo nei canali segnati NSFW.
Funzioni coperte: SPEC §14.19, §25.102 (AI-R-109, D22)
"""

from __future__ import annotations

from dataclasses import dataclass, replace

CONTESTI = ("PUBLIC", "WELCOME", "MODERATION", "ANNOUNCEMENT", "NSFW")
TONI = ("dolce", "scherzosa", "provocante", "piccante")
TONO_PREDEFINITO = "scherzosa"


@dataclass(frozen=True)
class VoiceProfile:
    style: str = "PUBLIC"
    lentezza: float = 1.0      # 1.0 normale; più alto = più lenta
    variazione: float = 0.85   # quanto si muove l'intonazione
    ritmo: float = 1.0         # quanto varia la durata dei suoni
    pause: int = 270           # ms tra le frasi
    calore: float = 2.0        # dB attorno a 220 Hz
    naso: float = -1.5         # dB attorno a 1 kHz
    presenza: float = 2.5      # dB attorno a 4,5 kHz
    aria: float = 3.0          # dB sopra 7 kHz
    vicinanza: float = 3.0     # rapporto di compressione


BASE = VoiceProfile()
PROFILI = {
    "PUBLIC": replace(BASE, style="PUBLIC", lentezza=0.98, pause=250),
    "WELCOME": replace(BASE, style="WELCOME", lentezza=1.0, calore=2.5, pause=270),
    "MODERATION": replace(BASE, style="MODERATION", lentezza=1.06, variazione=0.6, ritmo=0.8, pause=380, aria=1.0, presenza=2.0, calore=2.5),
    "ANNOUNCEMENT": replace(BASE, style="ANNOUNCEMENT", lentezza=1.03, variazione=0.75, pause=330, presenza=3.0),
    "NSFW": replace(BASE, style="NSFW", lentezza=1.05, pause=340, calore=3.0, presenza=1.5, aria=3.5, vicinanza=4.0),
}
# Ritocchi del tono sopra il profilo del contesto (solo espressione, mai l'intonazione di base).
_TONO = {
    "dolce": dict(lentezza=0.02, variazione=-0.05, pause=20, calore=0.5),
    "scherzosa": dict(),
    "provocante": dict(lentezza=0.03, pause=40, calore=0.5, aria=0.5),
    "piccante": dict(),
}
# Limiti di sicurezza: nessun profilo esce da una voce di donna adulta, calma e comprensibile.
LIMITI = {"lentezza": (0.9, 1.15), "variazione": (0.4, 1.0), "ritmo": (0.6, 1.2), "pause": (150, 500)}


def tono_valido(tono: str | None) -> str:
    return tono if tono in TONI else TONO_PREDEFINITO


def tono_consentito(tono: str, canale_nsfw: bool) -> str:
    """`piccante` solo nei canali NSFW: altrove diventa `provocante`."""
    tono = tono_valido(tono)
    return tono if tono != "piccante" or canale_nsfw else "provocante"


def contesto_effettivo(contesto: str, tono: str, canale_nsfw: bool) -> str:
    """NSFW solo se il canale lo è e il tono è `piccante`; la moderazione resta sempre ferma."""
    contesto = contesto if contesto in CONTESTI else "PUBLIC"
    if contesto == "MODERATION":
        return "MODERATION"
    if tono_consentito(tono, canale_nsfw) == "piccante":
        return "NSFW"
    return "PUBLIC" if contesto == "NSFW" else contesto


def profilo(contesto: str, tono: str = TONO_PREDEFINITO, canale_nsfw: bool = False) -> VoiceProfile:
    """Il profilo da usare: contesto e tono già controllati; la moderazione ignora il tono."""
    effettivo = contesto_effettivo(contesto, tono, canale_nsfw)
    base = PROFILI[effettivo]
    if effettivo in ("MODERATION", "NSFW"):
        return base
    ritocco = _TONO[tono_consentito(tono, canale_nsfw)]
    campi = {k: getattr(base, k) + v for k, v in ritocco.items()}
    for k, (minimo, massimo) in LIMITI.items():
        if k in campi:
            campi[k] = min(massimo, max(minimo, campi[k]))
    return replace(base, **campi)


def firma(p: VoiceProfile) -> str:
    """Stringa stabile del profilo, per la chiave della cache."""
    return "|".join(f"{k}={v}" for k, v in sorted(p.__dict__.items()))

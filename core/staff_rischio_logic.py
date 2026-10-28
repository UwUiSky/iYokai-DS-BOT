"""
core/staff_rischio_logic.py
===========================
Il punteggio di rischio di un membro (unisce i segnali di sicurezza che il bot già ha) e
la misura del carico dello staff. Servono a chi decide, non decidono: nessuna sanzione
parte da qui e nessun premio. Funzioni pure.
Funzioni coperte: SPEC §23.17 (NF-41, D50)
"""

from __future__ import annotations

from dataclasses import dataclass

FASCIA_BASSA = "basso"
FASCIA_MEDIA = "medio"
FASCIA_ALTA = "alto"
SOGLIA_MEDIA = 25
SOGLIA_ALTA = 55

# Doppi trovati dalla verifica web (stesso server): alto = stessa rete e stesso browser.
PESO_DOPPIO = {"alto": 25, "medio": 12, "basso": 4}


@dataclass(frozen=True)
class SegnaliRischio:
    warn_attivi: int = 0
    timeout_90_giorni: int = 0
    kick: int = 0
    ban_o_tempban: int = 0  # azioni passate, anche revocate
    spam_trap: int = 0
    eta_account_giorni: int | None = None
    giorni_nel_server: int | None = None
    doppi: tuple[str, ...] = ()  # un livello per ogni doppio trovato


@dataclass(frozen=True)
class Rischio:
    punteggio: int
    fascia: str
    motivi: tuple[str, ...]


def _fascia(punteggio: int) -> str:
    if punteggio >= SOGLIA_ALTA:
        return FASCIA_ALTA
    return FASCIA_MEDIA if punteggio >= SOGLIA_MEDIA else FASCIA_BASSA


def calcola_rischio(s: SegnaliRischio) -> Rischio:
    """Somma di segnali con un tetto ciascuno, da 0 a 100. I motivi dicono cosa pesa."""
    voci: list[tuple[int, str]] = [
        (min(s.warn_attivi * 8, 40), f"{s.warn_attivi} warn attivi"),
        (min(s.timeout_90_giorni * 10, 30), f"{s.timeout_90_giorni} timeout negli ultimi 90 giorni"),
        (min(s.kick * 15, 30), f"{s.kick} espulsioni"),
        (min(s.ban_o_tempban * 25, 50), f"{s.ban_o_tempban} ban o tempban passati"),
        (30 if s.spam_trap else 0, "è caduto nella trappola anti-spam"),
    ]
    if s.eta_account_giorni is not None and s.eta_account_giorni < 7:
        voci.append((15, f"account di {s.eta_account_giorni} giorni"))
    elif s.eta_account_giorni is not None and s.eta_account_giorni < 30:
        voci.append((8, f"account di {s.eta_account_giorni} giorni"))
    if s.giorni_nel_server is not None and s.giorni_nel_server < 1:
        voci.append((5, "è entrato oggi"))
    if s.doppi:
        voci.append((min(sum(PESO_DOPPIO.get(liv, 4) for liv in s.doppi), 40), f"{len(s.doppi)} possibili doppi (verifica web)"))
    peso_totale = min(sum(p for p, _ in voci), 100)
    motivi = tuple(testo for peso, testo in sorted(voci, key=lambda v: -v[0]) if peso > 0)
    return Rischio(peso_totale, _fascia(peso_totale), motivi)


def testo_rischio(r: Rischio) -> str:
    base = f"Rischio **{r.punteggio}/100** ({r.fascia})."
    if not r.motivi:
        return base + "\nNessun segnale."
    return base + "\n" + "\n".join(f"• {m}" for m in r.motivi) + (
        "\n\nÈ un aiuto per decidere, non una prova: nessuna azione parte da sola."
    )


# ---------------------------------------------------------------- carico dello staff
@dataclass(frozen=True)
class CaricoStaff:
    staff_id: int
    casi: int
    appelli: int
    ticket: int

    @property
    def totale(self) -> int:
        return self.casi + self.appelli + self.ticket


def testo_carico(righe: list[CaricoStaff], giorni: int, massimo_righe: int = 20) -> str:
    """Una riga per persona dello staff con la sua quota del lavoro. Senza classifica a premi."""
    if not righe:
        return f"Nessuna attività dello staff negli ultimi {giorni} giorni."
    totale = sum(r.totale for r in righe) or 1
    ordinate = sorted(righe, key=lambda r: (-r.totale, r.staff_id))
    testo = [f"Ultimi {giorni} giorni: {totale} attività."]
    for r in ordinate[:massimo_righe]:
        quota = round(100 * r.totale / totale)
        testo.append(f"<@{r.staff_id}> · {r.totale} ({quota}%) — casi {r.casi}, appelli {r.appelli}, ticket {r.ticket}")
    if len(ordinate) > massimo_righe:
        testo.append(f"…e altre {len(ordinate) - massimo_righe} persone.")
    if len(ordinate) >= 3 and 100 * ordinate[0].totale / totale >= 60:
        testo.append("⚠️ Più della metà del lavoro è di una persona sola.")
    return "\n".join(testo)

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
    riaperti: int = 0  # ticket presi in carico da lui e poi riaperti
    annullati: int = 0  # sanzioni sue accettate in appello (cioè annullate)
    risposta_sec: float | None = None  # tempo medio alla prima risposta nei suoi ticket
    voto_medio: float | None = None  # soddisfazione media (1-5) dei suoi ticket votati

    @property
    def totale(self) -> int:
        return self.casi + self.appelli + self.ticket


def durata_breve(secondi: float) -> str:
    """«45 s», «12 min», «3 h 20», «2 g»."""
    s = int(secondi)
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min"
    if s < 86400:
        ore, resto = divmod(s // 60, 60)
        return f"{ore} h {resto:02d}" if resto else f"{ore} h"
    return f"{s // 86400} g"


def _dettagli_riga(r: CaricoStaff) -> str:
    pezzi = [f"casi {r.casi}", f"appelli {r.appelli}", f"ticket {r.ticket}"]
    if r.risposta_sec is not None:
        pezzi.append(f"risposta {durata_breve(r.risposta_sec)}")
    if r.riaperti:
        pezzi.append(f"riaperti {r.riaperti}")
    if r.annullati:
        pezzi.append(f"annullate in appello {r.annullati}")
    if r.voto_medio is not None:
        pezzi.append(f"voto {r.voto_medio:.1f}/5")
    return ", ".join(pezzi)


def testo_carico(righe: list[CaricoStaff], giorni: int, massimo_righe: int = 20) -> str:
    """Una riga per persona dello staff con la sua quota del lavoro. Senza classifica a premi."""
    if not righe:
        return f"Nessuna attività dello staff negli ultimi {giorni} giorni."
    totale = sum(r.totale for r in righe) or 1
    ordinate = sorted(righe, key=lambda r: (-r.totale, r.staff_id))
    testo = [f"Ultimi {giorni} giorni: {totale} attività."]
    for r in ordinate[:massimo_righe]:
        quota = round(100 * r.totale / totale)
        testo.append(f"<@{r.staff_id}> · {r.totale} ({quota}%) — {_dettagli_riga(r)}")
    if len(ordinate) > massimo_righe:
        testo.append(f"…e altre {len(ordinate) - massimo_righe} persone.")
    if len(ordinate) >= 3 and 100 * ordinate[0].totale / totale >= 60:
        testo.append("⚠️ Più della metà del lavoro è di una persona sola.")
    return "\n".join(testo)


# ---------------------------------------------------------------- proposta di turni
FASCE_TURNO = ((0, 6), (6, 12), (12, 18), (18, 24))  # ore UTC
PERSONE_PER_TURNO = 2


def proponi_turni(ore_attivita: dict[int, list[int]]) -> str:
    """
    Una proposta di turni dalle ore in cui ognuno ha già lavorato: per ogni fascia di 6 ore (UTC) le
    due persone più attive, e l'avviso se nessuno la copre. `ore_attivita`: staff -> 24 conteggi.
    È un suggerimento sulle abitudini, non un obbligo.
    """
    if not ore_attivita:
        return "Servono alcuni giorni di attività dello staff per proporre dei turni."
    righe = ["**Turni proposti** (ore UTC, dalle abitudini di chi c'è già)"]
    for inizio, fine in FASCE_TURNO:
        per_persona = {
            staff: sum(ore[inizio:fine]) for staff, ore in ore_attivita.items() if sum(ore[inizio:fine]) > 0
        }
        scelti = sorted(per_persona, key=lambda st: (-per_persona[st], st))[:PERSONE_PER_TURNO]
        fascia = f"{inizio:02d}-{fine:02d}"
        righe.append(
            f"{fascia}: " + (", ".join(f"<@{st}>" for st in scelti) if scelti else "⚠️ scoperta, nessuno ha lavorato a quest'ora")
        )
    return "\n".join(righe)

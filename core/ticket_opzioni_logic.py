"""
core/ticket_opzioni_logic.py
============================
Regole pure delle opzioni dei pannelli dei ticket (catalogo #120): chi può aprire,
limiti, pausa, orari, nome del canale, testi con segnaposto, permessi dell'utente.
Niente oggetti Discord: il cog passa numeri e stringhe.
Funzioni coperte: SPEC §13.14–§13.20
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_RUOLI_LISTA = 10
MAX_REGOLE_ACCESSO = 25
MAX_APERTI_PANNELLO = 500
MAX_PAUSA_SECONDI = 7 * 24 * 3600
MAX_TESTO = 1500  # testo scritto dall'admin; con i segnaposto sostituiti resta sotto 2000
MAX_NOME_CANALE = 100
MAX_LISTA_NERA = 500
MAX_REPERIBILI = 10
MAX_ORE_RICHIESTA_CHIUSURA = 168
MAX_CANALI_PER_CATEGORIA = 50
FUSO_PREDEFINITO = "Europe/Rome"

ESCLUSIVA = ("no", "scrivere", "vedere")

# TKT-041: permessi che il server può togliere all'utente dentro il suo ticket.
PERMESSI_UTENTE: dict[str, str] = {
    "allegati": "attach_files",
    "link": "embed_links",
    "reazioni": "add_reactions",
    "emoji": "use_external_emojis",
    "vocali": "send_voice_messages",
}


@dataclass(frozen=True)
class Opzioni:
    """Le opzioni di un pannello. I valori predefiniti valgono anche senza riga nel database."""

    panel_id: int = 0
    max_aperti: int | None = None
    ruoli_esenti: tuple[int, ...] = ()
    pausa_secondi: int = 0
    orari: str | None = None
    fuso: str = FUSO_PREDEFINITO
    fuori_orario_testo: str | None = None
    fuori_orario_apri: bool = False
    nome_modello: str | None = None
    categorie_riserva: tuple[int, ...] = ()
    ping_ruoli: tuple[int, ...] = ()
    ping_here: bool = False
    ping_cancella: bool = False
    fissa_primo: bool = False
    dm_apertura: str | None = None
    dm_chiusura: str | None = None
    permessi_negati: tuple[str, ...] = ()
    ruoli_osservatori: tuple[int, ...] = ()
    ruoli_durante: tuple[int, ...] = ()
    ruoli_staff: tuple[int, ...] = ()
    categoria_presi: int | None = None
    claim_esclusivo: str = "no"
    assegna_auto: bool = False
    testo_presa: str | None = None
    testo_rilascio: str | None = None
    conferma_chiusura: bool = False
    utente_chiude: bool = True
    transcript_dm: bool = True
    chiusura_due_passi: bool = False
    elimina_dopo_ore: int = 0
    categoria_chiusi: int | None = None
    prefisso_chiuso: str | None = None
    prefisso_preso: str | None = None


# ----------------------------------------------------------------------
# Liste di ruoli scritte dall'admin: "<@&1> <@&2>" o "1, 2"
# ----------------------------------------------------------------------
_ID = re.compile(r"\d{15,20}")


def leggi_ids(testo: str | None, massimo: int = MAX_RUOLI_LISTA) -> tuple[int, ...]:
    """Gli ID (o le menzioni) in un testo, senza doppioni. Testo vuoto o "nessuno" = lista vuota."""
    if not testo or testo.strip().lower() in {"nessuno", "-", "0"}:
        return ()
    trovati: dict[int, None] = {}
    for pezzo in _ID.findall(testo):
        trovati.setdefault(int(pezzo), None)
    if len(trovati) > massimo:
        raise ValueError(f"Al massimo {massimo} elementi.")
    return tuple(trovati)


# ----------------------------------------------------------------------
# TKT-020 — chi può aprire: regole lette dall'alto
# ----------------------------------------------------------------------
def accesso_consentito(regole: list[tuple[int, bool]], ruoli_utente: set[int]) -> bool:
    """La prima regola che tocca un ruolo dell'utente decide; nessuna regola toccata = permesso."""
    for role_id, permetti in regole:
        if role_id in ruoli_utente:
            return permetti
    return True


# ----------------------------------------------------------------------
# TKT-022 — orari di apertura: "lun-ven 09:00-18:00; sab 10:00-12:30"
# ----------------------------------------------------------------------
GIORNI = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")
_FASCIA = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")


def _giorni(pezzo: str) -> list[int]:
    if "-" in pezzo:
        inizio, fine = pezzo.split("-", 1)
        if inizio not in GIORNI or fine not in GIORNI:
            raise ValueError(f"Giorno sconosciuto in «{pezzo}»: usa lun, mar, mer, gio, ven, sab, dom.")
        a, b = GIORNI.index(inizio), GIORNI.index(fine)
        if a > b:
            raise ValueError(f"«{pezzo}»: il primo giorno viene dopo il secondo.")
        return list(range(a, b + 1))
    giorni = []
    for g in pezzo.split(","):
        if g not in GIORNI:
            raise ValueError(f"Giorno sconosciuto «{g}»: usa lun, mar, mer, gio, ven, sab, dom.")
        giorni.append(GIORNI.index(g))
    return giorni


def leggi_orari(testo: str) -> dict[int, list[tuple[int, int]]]:
    """
    Le fasce per giorno (0 = lunedì), in minuti dalla mezzanotte. Ogni parte è
    "giorni fascia[, fascia]" e le parti si separano con ";". 24:00 vale come fine giornata.
    """
    orari: dict[int, list[tuple[int, int]]] = {}
    parti = [p.strip().lower() for p in testo.split(";") if p.strip()]
    if not parti:
        raise ValueError("Scrivi almeno un giorno con la sua fascia, per esempio «lun-ven 09:00-18:00».")
    for parte in parti:
        pezzi = parte.split()
        if len(pezzi) < 2:
            raise ValueError(f"«{parte}»: servono i giorni e almeno una fascia (09:00-18:00).")
        giorni = _giorni(pezzi[0])
        for fascia in " ".join(pezzi[1:]).replace(" ", "").split(","):
            m = _FASCIA.match(fascia)
            if not m:
                raise ValueError(f"Fascia non valida «{fascia}»: scrivila come 09:00-18:00.")
            h1, m1, h2, m2 = (int(x) for x in m.groups())
            inizio, fine = h1 * 60 + m1, h2 * 60 + m2
            if m1 > 59 or m2 > 59 or inizio >= 24 * 60 or fine > 24 * 60 or inizio >= fine:
                raise ValueError(f"Fascia non valida «{fascia}»: l'inizio va prima della fine, entro le 24:00.")
            for g in giorni:
                orari.setdefault(g, []).append((inizio, fine))
    return orari


def fuso_valido(nome: str) -> ZoneInfo:
    try:
        return ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"Fuso orario sconosciuto «{nome[:50]}»: usa un nome come Europe/Rome.") from None


def in_orario(testo_orari: str | None, fuso: str, adesso_utc: datetime) -> bool:
    """Senza orari si apre sempre. Un orario salvato e poi non più leggibile non blocca nessuno."""
    if not testo_orari:
        return True
    try:
        orari = leggi_orari(testo_orari)
        locale = adesso_utc.astimezone(fuso_valido(fuso))
    except ValueError:
        return True
    minuti = locale.hour * 60 + locale.minute
    return any(a <= minuti < b for a, b in orari.get(locale.weekday(), []))


def orari_come_testo(testo_orari: str | None, fuso: str) -> str:
    return f"{testo_orari} ({fuso})" if testo_orari else "sempre"


# ----------------------------------------------------------------------
# TKT-019 — pausa tra un'apertura e l'altra
# ----------------------------------------------------------------------
def secondi_di_pausa(
    ultima_apertura: datetime | None, azzerata_at: datetime | None, pausa_secondi: int, adesso: datetime
) -> int:
    """Quanti secondi mancano prima di poter aprire di nuovo (0 = può aprire)."""
    if not pausa_secondi or ultima_apertura is None:
        return 0
    if azzerata_at is not None and azzerata_at >= ultima_apertura:
        return 0
    fine = ultima_apertura + timedelta(seconds=pausa_secondi)
    return max(0, int((fine - adesso).total_seconds() + 0.999))


def durata_leggibile(secondi: int) -> str:
    if secondi < 60:
        return f"{secondi} secondi"
    minuti = (secondi + 59) // 60
    if minuti < 120:
        return f"{minuti} minuti"
    ore = (minuti + 59) // 60
    return f"{ore} ore"


# ----------------------------------------------------------------------
# TKT-025 — nome del canale
# ----------------------------------------------------------------------
SEGNAPOSTO_NOME = ("{numero}", "{num}", "{utente}", "{nickname}")
_SEGNAPOSTO = re.compile(r"\{[^{}]*\}")
_NON_VALIDI = re.compile(r"[^a-z0-9\-_À-ɏ]+")


def controlla_modello_nome(modello: str) -> str:
    modello = modello.strip()
    sconosciuti = [s for s in _SEGNAPOSTO.findall(modello) if s not in SEGNAPOSTO_NOME]
    if sconosciuti:
        raise ValueError(f"Segnaposto sconosciuto {sconosciuti[0][:30]}: usa {', '.join(SEGNAPOSTO_NOME)}.")
    if not modello or len(nome_canale(modello, 9999, "u" * 32, "n" * 32)) == 0:
        raise ValueError("Il modello darebbe un nome vuoto.")
    return modello


PREFISSO_MAX = 20


def prefisso_valido(prefisso: str) -> bool:
    """Un prefisso di nome serve se, ripulito, resta almeno una lettera o un numero."""
    return bool(_pulisci(prefisso))


def nome_con_prefisso(nome: str, prefisso: str | None, prefissi_noti: tuple[str | None, ...] = ()) -> str:
    """
    Il nome del canale con un prefisso davanti (TKT-026): un prefisso già messo dallo stesso
    meccanismo (`prefissi_noti`) si toglie prima, non si somma. Senza prefisso restituisce il
    nome senza i prefissi noti. Al massimo 100 caratteri.
    """
    base = nome
    for noto in prefissi_noti:
        pulito = _pulisci(noto or "")
        if pulito and base.startswith(pulito + "-"):
            base = base[len(pulito) + 1:]
    nuovo = _pulisci(prefisso or "")
    if not nuovo:
        return base
    return f"{nuovo}-{base}"[:MAX_NOME_CANALE].strip("-")


def _pulisci(testo: str) -> str:
    return _NON_VALIDI.sub("-", testo.lower()).strip("-")


def nome_canale(modello: str | None, numero: int, utente: str, nickname: str | None = None) -> str:
    """Il nome del canale dal modello: minuscole, trattini al posto degli spazi, al massimo 100 caratteri."""
    if not modello:
        return f"ticket-{numero:04d}"
    nome = (
        modello.replace("{numero}", f"{numero:04d}")
        .replace("{num}", str(numero))
        .replace("{utente}", _pulisci(utente) or "utente")
        .replace("{nickname}", _pulisci(nickname or utente) or "utente")
    )
    nome = re.sub(r"-{2,}", "-", _pulisci(nome))[:MAX_NOME_CANALE].strip("-")
    return nome or f"ticket-{numero:04d}"


# ----------------------------------------------------------------------
# TKT-039, TKT-053 — testi con segnaposto
# ----------------------------------------------------------------------
SEGNAPOSTO_TESTO = ("{utente}", "{server}", "{numero}", "{staff}")


def riempi(testo: str, *, utente: str = "", server: str = "", numero: int = 0, staff: str = "") -> str:
    return (
        testo.replace("{utente}", utente)
        .replace("{server}", server)
        .replace("{numero}", f"{numero:04d}")
        .replace("{staff}", staff)
    )


def controlla_testo(testo: str | None) -> str | None:
    """Un testo dell'admin, controllato al salvataggio: entro 2000 caratteri anche con i segnaposto pieni."""
    if testo is None or not testo.strip() or testo.strip().lower() == "nessuno":
        return None
    testo = testo.strip()
    pieno = riempi(testo, utente="<@" + "9" * 20 + ">", server="s" * 100, numero=9999, staff="<@" + "9" * 20 + ">")
    if len(pieno) > 2000:
        raise ValueError("Il testo, con i segnaposto sostituiti, supera i 2000 caratteri.")
    return testo


# ----------------------------------------------------------------------
# TKT-041 — permessi dell'utente
# ----------------------------------------------------------------------
def leggi_permessi_negati(testo: str | None) -> tuple[str, ...]:
    if not testo or testo.strip().lower() in {"nessuno", "-"}:
        return ()
    scelti: dict[str, None] = {}
    for pezzo in re.split(r"[,\s]+", testo.strip().lower()):
        if not pezzo:
            continue
        if pezzo not in PERMESSI_UTENTE:
            raise ValueError(f"Permesso sconosciuto «{pezzo[:30]}»: usa {', '.join(PERMESSI_UTENTE)}.")
        scelti.setdefault(pezzo, None)
    return tuple(scelti)


def permessi_utente(negati: tuple[str, ...]) -> dict[str, bool]:
    """Gli argomenti per l'overwrite dell'utente: vede, scrive, legge; i permessi tolti a False."""
    permessi = {"view_channel": True, "send_messages": True, "read_message_history": True}
    for nome in negati:
        attributo = PERMESSI_UTENTE.get(nome)
        if attributo:
            permessi[attributo] = False
    return permessi


# ----------------------------------------------------------------------
# TKT-030 — categoria con posto
# ----------------------------------------------------------------------
def prima_con_posto(candidate: list[tuple[int, int]]) -> int | None:
    """(id categoria, canali dentro) in ordine: la prima sotto i 50 canali, o None."""
    for categoria_id, canali in candidate:
        if canali < MAX_CANALI_PER_CATEGORIA:
            return categoria_id
    return None


# ----------------------------------------------------------------------
# Ordine dei controlli all'apertura (TKT-017…TKT-024)
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class Richiedente:
    user_id: int
    ruoli: frozenset[int]
    staff: bool = False


@dataclass
class Situazione:
    """Quello che il cog ha letto dal database, per decidere senza Discord."""

    opzioni: Opzioni = field(default_factory=Opzioni)
    in_lista_nera: bool = False
    sospesa_motivo: str | None = None
    sospesa_fino: datetime | None = None
    regole_accesso: list[tuple[int, bool]] = field(default_factory=list)
    aperti_nel_pannello: int = 0
    ultima_apertura: datetime | None = None
    azzerata_at: datetime | None = None


@dataclass(frozen=True)
class Esito:
    permesso: bool
    messaggio: str | None = None
    fuori_orario: bool = False  # TKT-023: aperto lo stesso, con l'avviso nel ticket
    tetto_pannello: int | None = None  # TKT-017: da ricontrollare sotto blocco quando si registra il ticket


def decidi_apertura(r: Richiedente, s: Situazione, adesso: datetime) -> Esito:
    o = s.opzioni
    if s.in_lista_nera and not r.staff:
        return Esito(False, "Non puoi aprire ticket su questo server.")
    esente = r.staff or bool(r.ruoli & set(o.ruoli_esenti))
    if s.sospesa_motivo is not None and not esente:
        fino = f" fino al <t:{int(s.sospesa_fino.timestamp())}:f>" if s.sospesa_fino else ""
        return Esito(False, f"L'apertura dei ticket è sospesa{fino}. Motivo: {s.sospesa_motivo}")
    if not r.staff and not accesso_consentito(s.regole_accesso, set(r.ruoli)):
        return Esito(False, "Non hai un ruolo che può aprire ticket da questo pannello.")
    fuori = False
    if not esente and not in_orario(o.orari, o.fuso, adesso):
        if not o.fuori_orario_apri:
            testo = o.fuori_orario_testo or (
                f"I ticket di questo pannello si aprono solo in questi orari: {orari_come_testo(o.orari, o.fuso)}."
            )
            return Esito(False, testo)
        fuori = True
    if not esente and o.max_aperti is not None and s.aperti_nel_pannello >= o.max_aperti:
        return Esito(False, "Questo pannello ha già il massimo di ticket aperti: riprova più tardi.")
    if not esente:
        attesa = secondi_di_pausa(s.ultima_apertura, s.azzerata_at, o.pausa_secondi, adesso)
        if attesa:
            return Esito(False, f"Hai aperto un ticket da poco: riprova tra {durata_leggibile(attesa)}.")
    return Esito(True, fuori_orario=fuori, tetto_pannello=None if esente else o.max_aperti)


# ----------------------------------------------------------------------
# TKT-009 — ticket da un messaggio: il link del messaggio
# ----------------------------------------------------------------------
_LINK = re.compile(r"https?://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/channels/(\d{1,20})/(\d{1,20})/(\d{1,20})")


def leggi_link_messaggio(testo: str | None) -> tuple[int, int, int] | None:
    """(server, canale, messaggio) da un link "Copia link del messaggio"; None se non è un link valido."""
    m = _LINK.search(testo or "")
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


# ----------------------------------------------------------------------
# Riassunto per /ticket opzioni mostra (campi entro 1024 caratteri)
# ----------------------------------------------------------------------
def _ruoli(ids: tuple[int, ...]) -> str:
    return " ".join(f"<@&{r}>" for r in ids) or "nessuno"


def _si(valore: bool) -> str:
    return "sì" if valore else "no"


def riassunto(o: Opzioni) -> list[tuple[str, str]]:
    """Le opzioni in campi (nome, valore) pronti per un embed: al massimo 8 campi."""
    pausa = durata_leggibile(o.pausa_secondi) if o.pausa_secondi else "nessuna"
    righe = [
        ("Limiti", f"Aperti nel pannello: {o.max_aperti or 'senza tetto'} · pausa: {pausa}\n"
                   f"Esenti: {_ruoli(o.ruoli_esenti)}"),
        ("Orari", f"{orari_come_testo(o.orari, o.fuso)} · fuori orario: "
                  f"{'si apre con avviso' if o.fuori_orario_apri else 'non si apre'}"),
        ("Canale", f"Nome: {o.nome_modello or 'ticket-{numero}'} · riserva: "
                   + (" ".join(f"<#{c}>" for c in o.categorie_riserva) or "nessuna")),
        ("Avvisi", f"Ping: {_ruoli(o.ping_ruoli)}{' + @here' if o.ping_here else ''} · cancellato: "
                   f"{_si(o.ping_cancella)} · primo messaggio fissato: {_si(o.fissa_primo)}"),
        ("Messaggi", f"DM apertura: {_si(bool(o.dm_apertura))} · DM chiusura: {_si(bool(o.dm_chiusura))} · "
                     f"transcript in DM: {_si(o.transcript_dm)} · testo presa: {_si(bool(o.testo_presa))} · "
                     f"testo rilascio: {_si(bool(o.testo_rilascio))}"),
        ("Permessi", f"Tolti all'utente: {', '.join(o.permessi_negati) or 'nessuno'}\n"
                     f"Osservatori: {_ruoli(o.ruoli_osservatori)}\nRuoli durante: {_ruoli(o.ruoli_durante)}\n"
                     f"Squadra: {_ruoli(o.ruoli_staff) if o.ruoli_staff else 'i ruoli di supporto'}"),
        ("Presa in carico", f"Categoria: {f'<#{o.categoria_presi}>' if o.categoria_presi else 'la stessa'} · "
                            f"esclusiva: {o.claim_esclusivo} · al primo che risponde: {_si(o.assegna_auto)}"),
        ("Chiusura", f"Conferma: {_si(o.conferma_chiusura)} · l'utente può chiudere: {_si(o.utente_chiude)}\n"
                     f"In due passi: {_si(o.chiusura_due_passi)} · elimina dopo: "
                     f"{f'{o.elimina_dopo_ore} ore' if o.elimina_dopo_ore else 'mai'} · categoria dei chiusi: "
                     f"{f'<#{o.categoria_chiusi}>' if o.categoria_chiusi else 'nessuna'}\n"
                     f"Nome da chiuso: {o.prefisso_chiuso or 'invariato'} · da preso: {o.prefisso_preso or 'invariato'}"),
    ]
    return [(nome, valore[:1024]) for nome, valore in righe]

"""
core/automod_pannello_logic.py
==============================
Logica pura del pannello delle regole AutoMod: categorie, lettura dei testi scritti nelle finestre (intervalli,
orari, durate, menzioni), parametri di base delle azioni, permessi che mancano al bot, campi dell'embed (testi
del catalogo). Niente discord.py: si prova con semplici input e output.
Funzioni coperte: SPEC §6 (AMD-029..056, AMD-067), D63
"""

from __future__ import annotations

import re
from typing import Any

from core.automod_regole_logic import (
    AZIONI_CANALE_STAFF_MENU,
    AZIONI_UTENTE_MENU,
    Azione,
    Orari,
    Regola,
    RegolaNonValida,
    azione_da_json,
    azione_a_json,
    azioni_da_json,
)
from core.duration_logic import MAX_DURATION_SECONDS, parse_duration

CATEGORIE = ("testo", "link", "spam", "allegati", "nomi", "vocali", "eventi", "personali")
FILTRI_PER_CATEGORIA = {
    "testo": ("anti_caps", "anti_zalgo", "anti_a_capo", "anti_lunghezza", "anti_corto", "anti_spoiler", "parole_vietate"),
    "link": ("anti_link", "anti_phishing", "anti_accorciatori", "anti_inviti_adulti", "anti_link_tempo"),
    "spam": ("anti_spam_messages", "anti_spam_emoji", "anti_spam_sticker", "anti_mass_mention", "anti_ripetuti",
             "anti_menzioni_tempo"),
    "allegati": ("anti_attachment_spam", "anti_estensioni", "solo_media", "senza_allegati"),
}
EVENTI_PER_CATEGORIA = {
    "nomi": ("nome", "stato"),
    "vocali": ("vocale", "thread"),
    "eventi": ("ingresso", "uscita", "ruolo_dato", "ruolo_tolto", "caso"),
}
PAGINA = 25  # voci per menu (limite di Discord)

# Parametri di base quando un'azione si sceglie dal menu senza passare dalla finestra.
PARAMETRI_BASE: dict[str, dict[str, Any]] = {
    "cancella_ultimi": {"n": 10, "minuti": 10},
    "timeout": {"secondi": 600},
    "mute_ruolo": {"secondi": 3600},
    "ban_tempo": {"giorni": 7},
    "avviso_canale": {"testo": "{utente}, questo messaggio non è permesso.", "dopo_s": 10},
    "slowmode": {"secondi": 10, "durata_s": 600},
    "permessi": {"modello": "blocca_scrittura", "durata_s": 600},
    "thread_apri": {"nome": "Segnalazione di {utente}"},
}
# Azioni che da sole non bastano (serve una scelta): si compilano dalla finestra, non dal menu.
SOLO_DA_FINESTRA = ("ruolo", "dm_staff")

_PERMESSI_AZIONE = {
    "cancella": ("manage_messages",), "cancella_ultimi": ("manage_messages",), "timeout": ("moderate_members",),
    "mute_ruolo": ("manage_roles",), "kick": ("kick_members",), "ban": ("ban_members",),
    "ban_tempo": ("ban_members",), "ruolo": ("manage_roles",), "nickname": ("manage_nicknames",),
    "slowmode": ("manage_channels",), "permessi": ("manage_roles", "manage_channels"),
    "thread_archivia": ("manage_threads",), "thread_apri": ("create_public_threads",),
}


# ---------------------------------------------------------------- categorie

def categoria_di_regola(regola: Regola) -> str:
    if regola.tipo == "filtro":
        for categoria, chiavi in FILTRI_PER_CATEGORIA.items():
            if regola.chiave in chiavi:
                return categoria
        return "testo"
    for categoria, eventi in EVENTI_PER_CATEGORIA.items():
        if regola.evento in eventi:
            return categoria
    return "personali"


def pagina_di(voci: list, pagina: int) -> tuple[list, int]:
    """(voci della pagina, numero di pagine). Una pagina fuori misura torna all'ultima."""
    pagine = max(1, -(-len(voci) // PAGINA))
    pagina = min(max(pagina, 0), pagine - 1)
    return voci[pagina * PAGINA:(pagina + 1) * PAGINA], pagine


# ---------------------------------------------------------------- testi delle finestre

def leggi_intervallo(testo: str, massimo: int = 36_500) -> tuple[int | None, int | None]:
    """«3-7» → (3, 7); «-7» → (None, 7); «3-» → (3, None); «5» → (5, 5); vuoto → (None, None)."""
    testo = (testo or "").strip().replace(" ", "")
    if not testo:
        return None, None
    m = re.fullmatch(r"(\d*)-(\d*)", testo)
    if m:
        minimo, alto = (int(x) if x else None for x in m.groups())
    elif testo.isdigit():
        minimo = alto = int(testo)
    else:
        raise RegolaNonValida("usa il formato 3-7, -7 oppure 3-")
    for v in (minimo, alto):
        if v is not None and v > massimo:
            raise RegolaNonValida(f"il numero massimo è {massimo}")
    if minimo is not None and alto is not None and minimo > alto:
        raise RegolaNonValida("il primo numero supera il secondo")
    return minimo, alto


def leggi_orario(orario: str, giorni: str, fuso: str = "Europe/Rome") -> Orari | None:
    """«23:00-08:00» + «1,2,3» (lunedì=1). Orario vuoto: nessun limite d'orario."""
    orario = (orario or "").strip().replace(" ", "")
    if not orario:
        return None
    m = re.fullmatch(r"(\d{1,2}:\d{2})-(\d{1,2}:\d{2})", orario)
    if not m:
        raise RegolaNonValida("l'orario si scrive 23:00-08:00")
    try:
        elenco = tuple(sorted({int(g) for g in re.split(r"[,\s]+", giorni.strip()) if g})) if giorni and giorni.strip() else tuple(range(1, 8))
    except ValueError:
        raise RegolaNonValida("i giorni sono numeri da 1 (lunedì) a 7") from None
    if not elenco or any(g < 1 or g > 7 for g in elenco):
        raise RegolaNonValida("i giorni sono numeri da 1 (lunedì) a 7")
    return Orari(fuso, m.group(1).zfill(5), m.group(2).zfill(5), elenco)


def leggi_durata(testo: str, minimo: int = 1, massimo: int = MAX_DURATION_SECONDS) -> int | None:
    """«10m», «7d»… in secondi; vuoto → None. Errore se fuori dai limiti."""
    testo = (testo or "").strip()
    if not testo:
        return None
    try:
        secondi = parse_duration(testo)
    except ValueError as errore:
        raise RegolaNonValida(str(errore)) from None
    if not minimo <= secondi <= massimo:
        raise RegolaNonValida("durata fuori dai limiti")
    return secondi


def leggi_id(testo: str) -> int | None:
    """Un ID, anche scritto come menzione (<@123>, <@&123>, <#123>). Vuoto → None."""
    testo = (testo or "").strip()
    if not testo:
        return None
    m = re.fullmatch(r"<[@#][&!]?(\d{15,20})>|(\d{15,20})", testo)
    if not m:
        raise RegolaNonValida("scrivi un ID o una menzione")
    return int(m.group(1) or m.group(2))


def leggi_ids(testo: str, massimo: int) -> list[int]:
    voci = [v for v in re.split(r"[,\s]+", (testo or "").strip()) if v]
    ids = list(dict.fromkeys(leggi_id(v) for v in voci))
    if len(ids) > massimo:
        raise RegolaNonValida(f"al massimo {massimo}")
    return ids


def leggi_azione_soglia(testo: str) -> Azione:
    """Per il contatore: «timeout 10m», «kick», «ban», «ban_tempo 7»…"""
    parti = (testo or "").split()
    if not parti:
        raise RegolaNonValida("scrivi l'azione, ad esempio timeout 10m")
    tipo, resto = parti[0].lower(), parti[1:]
    if tipo == "timeout":
        return azione_da_json({"t": "timeout", "secondi": leggi_durata(" ".join(resto) or "10m")})
    if tipo == "ban_tempo":
        return azione_da_json({"t": "ban_tempo", "giorni": int(resto[0]) if resto and resto[0].isdigit() else 7})
    if tipo in ("kick", "ban", "cancella", "warn"):
        return azione_da_json({"t": tipo})
    raise RegolaNonValida("azioni ammesse: timeout, ban_tempo, kick, ban, cancella, warn")


# ---------------------------------------------------------------- azioni nella bozza

def imposta_azioni(regola_azioni: tuple[Azione, ...], tipi: set[str], gruppo: tuple[str, ...]) -> tuple[Azione, ...]:
    """
    Applica la scelta di un menu a scelta multipla: tra le azioni del `gruppo` restano (con i loro parametri)
    quelle ancora scelte, quelle nuove entrano con i parametri di base, le altre escono. Le azioni fuori dal
    gruppo non cambiano. Quelle che vogliono una scelta (ruolo, dm_staff) si compilano dalla finestra.
    """
    nuove: list[Azione] = []
    visti: set[str] = set()
    for a in regola_azioni:
        if a.t not in gruppo:
            nuove.append(a)
        elif a.t in tipi or a.t in SOLO_DA_FINESTRA and a.t in tipi:
            nuove.append(a)
            visti.add(a.t)
    for t in gruppo:
        if t in tipi and t not in visti and t not in SOLO_DA_FINESTRA:
            nuove.append(azione_da_json({"t": t, **PARAMETRI_BASE.get(t, {})}))
    return azioni_da_json([azione_a_json(a) for a in nuove])


def metti_azione(azioni: tuple[Azione, ...], nuova: Azione) -> tuple[Azione, ...]:
    """Sostituisce l'azione dello stesso tipo (o la aggiunge)."""
    resto = [a for a in azioni if a.t != nuova.t]
    return azioni_da_json([azione_a_json(a) for a in (*resto, nuova)])


def togli_azione(azioni: tuple[Azione, ...], tipo: str) -> tuple[Azione, ...]:
    return tuple(a for a in azioni if a.t != tipo)


def permessi_mancanti(azioni: tuple[Azione, ...], permessi_bot: Any) -> list[str]:
    """Nomi dei permessi che servono alle azioni e al bot mancano (il pannello avvisa prima di salvare)."""
    if getattr(permessi_bot, "administrator", False):
        return []
    mancanti: list[str] = []
    for a in azioni:
        for p in _PERMESSI_AZIONE.get(a.t, ()):
            if not getattr(permessi_bot, p, False) and p not in mancanti:
                mancanti.append(p)
    return mancanti


# ---------------------------------------------------------------- embed

def _taglia(testo: str, massimo: int = 1024) -> str:
    return testo if len(testo) <= massimo else testo[: massimo - 1] + "…"


def _ids(titolo: str, ids: tuple[int, ...], prefisso: str, tutti: str) -> str:
    return f"{titolo}: " + (", ".join(f"<{prefisso}{i}>" for i in ids[:25]) if ids else tutti)


def descrivi_azione(a: Azione) -> str:
    p = dict(a.parametri)
    extra = ", ".join(f"{k}={str(v)[:40]}" for k, v in p.items())
    return f"`{a.t}`" + (f" ({extra})" if extra else "")


def campi_embed(regola: Regola, lingua: str = "it") -> list[tuple[str, str]]:
    """I campi dell'embed di una regola (testi del catalogo `amregole_e_*`). Ognuno ≤ 1024 caratteri."""
    from core.i18n import t

    def tx(chiave: str, **valori) -> str:
        return t(f"amregole_e_{chiave}", lingua, **valori)

    c, tutti = regola.condizioni, tx("tutti")
    righe = [
        _ids(tx("canali_inclusi"), c.canali_inclusi, "#", tutti),
        _ids(tx("canali_esclusi"), c.canali_esclusi, "#", tutti) if c.canali_esclusi else "",
        _ids(tx("ruoli_inclusi"), c.ruoli_inclusi, "@&", tutti) + (f" ({c.ruoli_modo})" if c.ruoli_inclusi else ""),
        _ids(tx("ruoli_esclusi"), c.ruoli_esclusi, "@&", tutti) if c.ruoli_esclusi else "",
        tx("senza_ruoli") if c.senza_ruoli else "",
        _ids(tx("utenti_esclusi"), c.utenti_esclusi, "@", tutti) if c.utenti_esclusi else "",
    ]
    for nome, (mn, mx) in (("eta", c.eta_account_giorni), ("nel_server", c.nel_server_giorni), ("livello", c.livello)):
        if (mn, mx) != (None, None):
            righe.append(f"{tx(nome)}: {'' if mn is None else mn}-{'' if mx is None else mx}")
    if c.orari:
        righe.append(tx("orario", dalle=c.orari.dalle, alle=c.orari.alle, fuso=c.orari.fuso,
                        giorni=",".join(map(str, c.orari.giorni))))
    righe.append(tx("riga_base", thread=c.thread, autori=", ".join(c.autori),
                    esenzioni=tx("si") if c.esenzioni_globali else tx("no")))
    campi = [(tx("condizioni"), _taglia("\n".join(r for r in righe if r)))]
    campi.append((tx("azioni"), _taglia("\n".join(descrivi_azione(a) for a in regola.azioni) or tx("nessuna"))))
    if regola.contatore:
        ct = regola.contatore
        soglie = "; ".join(tx("soglia", n=s.violazioni, minuti=s.minuti, azioni=", ".join(a.t for a in s.azioni))
                           for s in ct.soglie) or tx("nessuna_soglia")
        scade = f" {tx('scade', giorni=ct.scadenza_giorni)}" if ct.scadenza_giorni else ""
        campi.append((tx("contatore"), _taglia(f"{ct.nome}{scade}\n{soglie}")))
    campi.append((tx("gruppo_calore"), tx("riga_gruppo", gruppo=regola.gruppo or "-", calore=regola.calore,
                                          stato=tx("accesa") if regola.attiva else tx("spenta"))[:1024]))
    if regola.innesco:
        campi.insert(0, (tx("innesco"), _taglia(", ".join(f"{k}={str(v)[:80]}" for k, v in regola.innesco.items()))))
    return campi


__all__ = [n for n in dir() if not n.startswith("_")]

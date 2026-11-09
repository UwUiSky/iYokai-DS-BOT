"""
core/moderation_opzioni.py
==========================
Opzioni di moderazione del server, in un solo punto (D16): giorni di
messaggi cancellati al ban, durata predefinita del timeout, DM per tipo
di azione, ruoli immuni alla moderazione manuale e casi per le azioni fatte
fuori da iYokai, avvisi allo staff (troppi warn, rientro di chi ha casi).
Funzioni coperte: SPEC §5.13 (MOD-010, MOD-017, MOD-057, MOD-068), §5.2 (MOD-047),
§5.3 (MOD-036, MOD-064), §5.13 (MOD-066, MOD-067)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.database import db
from core.moderation_casi_esterni_logic import SETTING_CASI_ESTERNI
from core.moderation_risposte import MODI as MODI_RISPOSTE
from core.moderation_risposte import MODO_NORMALE, SECONDI_BASE, SECONDI_MAX, SECONDI_MIN, modo_valido, secondi_validi

SETTING_GIORNI_BAN = "mod_ban_giorni_messaggi"
SETTING_DURATA_TIMEOUT = "mod_timeout_predefinito"
SETTING_DM_SPENTI = "mod_dm_spenti"
SETTING_RUOLI_IMMUNI = "mod_ruoli_immuni"
SETTING_AVVISO_WARN = "mod_avviso_warn_soglia"
SETTING_AVVISO_RIENTRO = "mod_avviso_rientro"
SETTING_SCADENZA_AUTOMOD = "mod_scadenza_automod_giorni"
SETTING_MOTIVO_OBBLIGATORIO = "mod_motivo_obbligatorio"
SETTING_ANONIMO = "mod_anonimo"
SETTING_UTENTE_VEDE_CASI = "mod_utente_vede_casi"
SETTING_CONFERMA = "mod_conferma"
SETTING_RISPOSTE = "mod_risposte"
SETTING_RISPOSTE_SECONDI = "mod_risposte_secondi"
MAX_TESTO_DM = 1500
MAX_SCADENZA_AUTOMOD = 200

# Azioni che mandano un DM all'utente; per ognuna il server può spegnerlo.
AZIONI_CON_DM = ("warn", "kick", "ban", "tempban", "softban", "timeout", "mute")


def setting_testo_dm(azione: str) -> str:
    """La chiave dell'impostazione col testo del DM per `azione` (MOD-059)."""
    return f"mod_dm_testo_{azione}"

MAX_RUOLI_IMMUNI = 25
MAX_SOGLIA_WARN = 200
# Timeout di Discord: da 1 minuto a 28 giorni.
MIN_TIMEOUT = 60
MAX_TIMEOUT = 28 * 86400


@dataclass(frozen=True)
class OpzioniModerazione:
    giorni_ban: int = 0
    durata_timeout: int | None = None
    dm_spenti: frozenset[str] = field(default_factory=frozenset)
    ruoli_immuni: tuple[int, ...] = ()
    casi_esterni: bool = False
    avviso_warn: int = 0  # 0 = spento
    avviso_rientro: bool = False
    scadenza_automod: int = 0  # giorni; 0 = i casi AutoMod non scadono
    motivo_obbligatorio: bool = True  # MOD-065: base sì, come prima
    anonimo: bool = False  # MOD-050: il DM dice «Staff di <server>» invece del nome del moderatore
    dm_testi: dict[str, str] = field(default_factory=dict)  # MOD-059: testo del server per ogni azione
    utente_vede_casi: bool = True  # MOD-114: /utility mie-sanzioni (base sì)
    conferma: bool = False  # MOD-066: prima di sanzionare, due tasti Conferma/Annulla (base no)
    risposte: str = MODO_NORMALE  # MOD-067: normale, compatta o cancella-dopo
    risposte_secondi: int = SECONDI_BASE  # MOD-067: attesa di cancella-dopo (5-300)


async def leggi(guild_id: int) -> OpzioniModerazione:
    giorni = await db.get_guild_setting(guild_id, SETTING_GIORNI_BAN, 0)
    durata = await db.get_guild_setting(guild_id, SETTING_DURATA_TIMEOUT)
    spenti = await db.get_guild_setting(guild_id, SETTING_DM_SPENTI, [])
    immuni = await db.get_guild_setting(guild_id, SETTING_RUOLI_IMMUNI, [])
    esterni = await db.get_guild_setting(guild_id, SETTING_CASI_ESTERNI, False)
    soglia = await db.get_guild_setting(guild_id, SETTING_AVVISO_WARN, 0)
    rientro = await db.get_guild_setting(guild_id, SETTING_AVVISO_RIENTRO, False)
    scadenza = await db.get_guild_setting(guild_id, SETTING_SCADENZA_AUTOMOD, 0)
    obbligatorio = await db.get_guild_setting(guild_id, SETTING_MOTIVO_OBBLIGATORIO, True)
    anonimo = await db.get_guild_setting(guild_id, SETTING_ANONIMO, False)
    vede = await db.get_guild_setting(guild_id, SETTING_UTENTE_VEDE_CASI, True)
    conferma = await db.get_guild_setting(guild_id, SETTING_CONFERMA, False)
    risposte = await db.get_guild_setting(guild_id, SETTING_RISPOSTE, MODO_NORMALE)
    risposte_s = await db.get_guild_setting(guild_id, SETTING_RISPOSTE_SECONDI, SECONDI_BASE)
    testi = {}
    for azione in AZIONI_CON_DM:
        testo = await db.get_guild_setting(guild_id, setting_testo_dm(azione))
        if isinstance(testo, str) and testo.strip():
            testi[azione] = testo[:MAX_TESTO_DM]
    return OpzioniModerazione(
        giorni_ban=int(giorni) if isinstance(giorni, int) and 0 <= giorni <= 7 else 0,
        durata_timeout=durata if isinstance(durata, int) and MIN_TIMEOUT <= durata <= MAX_TIMEOUT else None,
        dm_spenti=frozenset(a for a in spenti if a in AZIONI_CON_DM),
        ruoli_immuni=tuple(r for r in immuni if isinstance(r, int)),
        casi_esterni=esterni is True,
        avviso_warn=soglia if isinstance(soglia, int) and 0 <= soglia <= MAX_SOGLIA_WARN else 0,
        avviso_rientro=rientro is True,
        scadenza_automod=giorni_scadenza_validi(scadenza),
        motivo_obbligatorio=obbligatorio is not False,
        anonimo=anonimo is True,
        dm_testi=testi,
        utente_vede_casi=vede is not False,
        conferma=conferma is True,
        risposte=modo_valido(risposte),
        risposte_secondi=secondi_validi(risposte_s),
    )


async def imposta_giorni_ban(guild_id: int, giorni: int, autore_id: int) -> None:
    if not 0 <= giorni <= 7:
        raise ValueError("I giorni vanno da 0 a 7.")
    await db.set_guild_setting(guild_id, SETTING_GIORNI_BAN, giorni, changed_by=autore_id)


async def imposta_durata_timeout(guild_id: int, secondi: int | None, autore_id: int) -> None:
    """None toglie la durata predefinita."""
    if secondi is not None and not MIN_TIMEOUT <= secondi <= MAX_TIMEOUT:
        raise ValueError("La durata va da 1 minuto a 28 giorni.")
    await db.set_guild_setting(guild_id, SETTING_DURATA_TIMEOUT, secondi, changed_by=autore_id)


async def imposta_dm(guild_id: int, azione: str, attivo: bool, autore_id: int) -> None:
    if azione not in AZIONI_CON_DM:
        raise ValueError(f"Azione sconosciuta: {azione}")
    spenti = set((await leggi(guild_id)).dm_spenti)
    if attivo:
        spenti.discard(azione)
    else:
        spenti.add(azione)
    await db.set_guild_setting(
        guild_id, SETTING_DM_SPENTI, sorted(spenti), changed_by=autore_id
    )


async def imposta_casi_esterni(guild_id: int, attivo: bool, autore_id: int) -> None:
    await db.set_guild_setting(guild_id, SETTING_CASI_ESTERNI, attivo, changed_by=autore_id)


async def imposta_avviso_warn(guild_id: int, soglia: int, autore_id: int) -> None:
    """Con `soglia` warn già dati lo staff riceve un avviso al warn successivo. 0 = spento."""
    if not 0 <= soglia <= MAX_SOGLIA_WARN:
        raise ValueError(f"La soglia va da 0 a {MAX_SOGLIA_WARN}.")
    await db.set_guild_setting(guild_id, SETTING_AVVISO_WARN, soglia, changed_by=autore_id)


async def imposta_avviso_rientro(guild_id: int, attivo: bool, autore_id: int) -> None:
    await db.set_guild_setting(guild_id, SETTING_AVVISO_RIENTRO, attivo, changed_by=autore_id)


def giorni_scadenza_validi(valore) -> int:
    """Giorni di scadenza dei casi AutoMod da un valore salvato (anche testo dal JSON); 0 se non valido."""
    if isinstance(valore, str) and valore.isdigit():
        valore = int(valore)
    return valore if isinstance(valore, int) and not isinstance(valore, bool) and 0 <= valore <= MAX_SCADENZA_AUTOMOD else 0


async def imposta_scadenza_automod(guild_id: int, giorni: int, autore_id: int) -> None:
    """MOD-048: dopo `giorni` giorni i casi AutoMod non contano più. 0 = mai."""
    if not 0 <= giorni <= MAX_SCADENZA_AUTOMOD:
        raise ValueError(f"I giorni vanno da 0 a {MAX_SCADENZA_AUTOMOD}.")
    await db.set_guild_setting(guild_id, SETTING_SCADENZA_AUTOMOD, giorni, changed_by=autore_id)


async def imposta_motivo_obbligatorio(guild_id: int, obbligatorio: bool, autore_id: int) -> None:
    """MOD-065: il motivo dei comandi di sanzione è obbligatorio (base) o facoltativo."""
    await db.set_guild_setting(guild_id, SETTING_MOTIVO_OBBLIGATORIO, obbligatorio, changed_by=autore_id)


async def imposta_anonimo(guild_id: int, attivo: bool, autore_id: int) -> None:
    """MOD-050: nei DM delle sanzioni il moderatore non si nomina. Log e casi tengono il nome."""
    await db.set_guild_setting(guild_id, SETTING_ANONIMO, attivo, changed_by=autore_id)


async def imposta_utente_vede_casi(guild_id: int, attivo: bool, autore_id: int) -> None:
    """MOD-114: ogni utente vede i propri casi con `/utility mie-sanzioni` (base sì)."""
    await db.set_guild_setting(guild_id, SETTING_UTENTE_VEDE_CASI, attivo, changed_by=autore_id)


async def imposta_conferma(guild_id: int, attivo: bool, autore_id: int) -> None:
    """MOD-066: warn, timeout, kick, ban e simili chiedono prima «Conferma» o «Annulla» (base no)."""
    await db.set_guild_setting(guild_id, SETTING_CONFERMA, attivo, changed_by=autore_id)


async def imposta_risposte(guild_id: int, modo: str, secondi: int | None, autore_id: int) -> None:
    """MOD-067: come risponde il bot dopo una sanzione; `secondi` (5-300) conta solo per cancella-dopo."""
    if modo not in MODI_RISPOSTE:
        raise ValueError("Modo sconosciuto: " + ", ".join(MODI_RISPOSTE) + ".")
    if secondi is not None and not SECONDI_MIN <= secondi <= SECONDI_MAX:
        raise ValueError(f"I secondi vanno da {SECONDI_MIN} a {SECONDI_MAX}.")
    await db.set_guild_setting(guild_id, SETTING_RISPOSTE, modo, changed_by=autore_id)
    if secondi is not None:
        await db.set_guild_setting(guild_id, SETTING_RISPOSTE_SECONDI, secondi, changed_by=autore_id)


async def imposta_dm_testo(guild_id: int, azione: str, testo: str | None, autore_id: int) -> None:
    """MOD-059: il testo del DM per `azione`; vuoto o None torna al messaggio di base."""
    if azione not in AZIONI_CON_DM:
        raise ValueError(f"Azione sconosciuta: {azione}")
    testo = (testo or "").strip()
    if len(testo) > MAX_TESTO_DM:
        raise ValueError(f"Il testo va fino a {MAX_TESTO_DM} caratteri.")
    await db.set_guild_setting(guild_id, setting_testo_dm(azione), testo or None, changed_by=autore_id)


def avviso_warn_scatta(warn_attivi: int, soglia: int) -> bool:
    """MOD-036: True se, con questo warn, chi lo riceve ne ha più di `soglia` (cioè ne aveva già `soglia`)."""
    return soglia > 0 and warn_attivi > soglia


async def dm_attivo(guild_id: int, azione: str) -> bool:
    return azione not in (await leggi(guild_id)).dm_spenti


async def cambia_ruolo_immune(guild_id: int, ruolo_id: int, aggiungi: bool, autore_id: int) -> str | None:
    """Aggiunge o toglie un ruolo immune. Restituisce l'errore da mostrare, o None."""
    immuni = list((await leggi(guild_id)).ruoli_immuni)
    if aggiungi:
        if ruolo_id in immuni:
            return "Il ruolo è già immune."
        if len(immuni) >= MAX_RUOLI_IMMUNI:
            return f"Al massimo {MAX_RUOLI_IMMUNI} ruoli immuni."
        immuni.append(ruolo_id)
    else:
        if ruolo_id not in immuni:
            return "Il ruolo non è tra gli immuni."
        immuni.remove(ruolo_id)
    await db.set_guild_setting(guild_id, SETTING_RUOLI_IMMUNI, immuni, changed_by=autore_id)
    return None


def motivo_immune(ruoli_immuni, ruoli_bersaglio, *, attore_proprietario: bool) -> str | None:
    """
    MOD-068: chi ha un ruolo immune non si modera a mano. Il proprietario
    del server resta libero (può sempre togliere il ruolo). None = si può.
    """
    if attore_proprietario or not ruoli_immuni:
        return None
    if set(ruoli_immuni) & set(ruoli_bersaglio):
        return "Ha un ruolo immune alla moderazione (lo decide il proprietario del server)."
    return None

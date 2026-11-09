"""
core/config_impostazioni.py
===========================
Il punto unico (D16) per le impostazioni interne di un modulo che il pannello web mostra in una pagina per modulo:
quali chiavi di `guild_config.settings` appartengono a ogni modulo, come si leggono dal modulo, come si controllano
(gli stessi controlli di `SETTINGS_SCHEMA`) e come si scrivono (con lo storico). Le chiavi che decidono chi può fare
cosa (`CHIAVI_SOLO_PROPRIETARIO`) e le liste non sono qui: restano ai comandi.
Funzioni coperte: SPEC §24.2 (NF-20, issue #91)
Dipende da: core/database.py, cogs/utility/config_history.py (schema e controlli, caricati al bisogno)
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass

import discord

from core.config_schema import ImpostazioneNonValida
from core.database import db
from core.role_safety import check_role_assignable

BOOL, NUMERO, TESTO, SCELTA, CANALE, CANALE_VOCE, RUOLO = "bool", "numero", "testo", "scelta", "canale", "canale_voce", "ruolo"
# Ruoli che il bot dà da solo a chiunque entri: stesso controllo del comando (`/verify opzioni`).
RUOLI_DATI_DAL_BOT = frozenset({"verify_unverified_role_id"})
SCELTE = {
    "captcha_tipo": ("testo", "immagine"),
    "azione_verifica": ("niente", "quarantena", "kick", "ban"),
    "azione_eta": ("attendi", "kick"),
    "azione_immagini": ("cancella", "avvisa", "timeout"),
    "modalita_risposte_mod": ("normale", "compatta", "cancella-dopo"),
    "modalita_link_inviti": ("tutti", "crea_invito", "ruolo", "spento"),
}


# Valore che vale quando il server non ha scelto: la pagina lo mostra, non resta «non impostato».
VALORI_DI_BASE = {"verify_blocca_vpn": True}


@dataclass(frozen=True)
class Campo:
    chiave: str
    etichetta: str
    tipo: str  # BOOL, NUMERO, TESTO, SCELTA, CANALE, CANALE_VOCE, RUOLO


def _c(chiave: str, etichetta: str, tipo: str) -> Campo:
    return Campo(chiave, etichetta, tipo)


SCHEDE: dict[str, tuple[Campo, ...]] = {
    "verify": (
        _c("verify_unverified_role_id", "Ruolo dei non verificati", RUOLO),
        _c("verify_captcha_tipo", "Tipo di captcha", SCELTA),
        _c("verify_log_compatto", "Registro compatto", BOOL),
        _c("verify_promemoria_minuti", "Promemoria dopo (minuti, 0 = mai)", NUMERO),
        _c("verify_scadenza_minuti", "Scadenza (minuti, 0 = mai)", NUMERO),
        _c("verify_azione_scadenza", "Se scade il tempo", SCELTA),
        _c("verify_azione_fallita", "Se sbaglia il captcha", SCELTA),
        _c("verify_solo_sospetti", "Verifica solo gli account sospetti", BOOL),
        _c("verify_azione_eta", "Account troppo nuovo", SCELTA),
        _c("verify_blocca_vpn", "Blocca chi si verifica con VPN o proxy", BOOL),
        _c("verify_condividi_nome", "Fatti nominare negli avvisi degli altri server (storico VPN)", BOOL),
        _c("verify_paesi", "Paesi del server (codici di 2 lettere, es. IT, CH)", TESTO),
        _c("verify_paesi_soglia", "Verifiche da fuori paese prima dell'attesa (0 = spento)", NUMERO),
        _c("verify_paesi_minuti", "Finestra della soglia (minuti, 1-1440)", NUMERO),
        _c("verify_paesi_canale_id", "Canale dove lo staff approva o rifiuta", CANALE),
    ),
    "music": (
        _c("music_max_volume", "Volume massimo (0-200)", NUMERO),
        _c("music_max_track_minutes", "Durata massima di un brano (minuti, 0 = senza limite)", NUMERO),
        _c("music_stay_when_queue_ends", "Resta nel canale a coda finita", BOOL),
        _c("music_allowed_voice_channel_id", "Canale vocale consentito", CANALE_VOCE),
        _c("music_banned_words", "Parole vietate nei titoli", TESTO),
        _c("music_idle_minutes", "Esci dopo (minuti di silenzio, 0 = mai)", NUMERO),
        _c("music_known_sites_only", "Solo siti conosciuti", BOOL),
    ),
    "tickets": (
        _c("ticket_support_role_id", "Ruolo del supporto", RUOLO),
        _c("ticket_max_per_utente", "Ticket aperti per persona (1-5)", NUMERO),
    ),
    "moderation_actions": (
        _c("mod_log_channel_id", "Canale del registro di moderazione", CANALE),
        _c("mod_ban_giorni_messaggi", "Giorni di messaggi cancellati con un ban (0-7)", NUMERO),
        _c("mod_timeout_predefinito", "Timeout di base (secondi, da 60 a 2419200)", NUMERO),
        _c("mod_casi_esterni", "Registra anche le azioni fatte fuori dal bot", BOOL),
        _c("mod_avviso_warn_soglia", "Avvisi prima della sanzione automatica (0 = spenta)", NUMERO),
        _c("mod_avviso_rientro", "Avvisa chi rientra con avvisi attivi", BOOL),
        _c("mod_motivo_obbligatorio", "Il motivo delle sanzioni è obbligatorio (altrimenti si può omettere)", BOOL),
        _c("mod_scadenza_automod_giorni", "Giorni dopo i quali i casi AutoMod non contano più (0 = mai)", NUMERO),
        _c("mod_utente_vede_casi", "Ogni utente vede i propri casi con /utility mie-sanzioni", BOOL),
        _c("mod_conferma", "Chiede «Conferma» o «Annulla» prima di ogni sanzione", BOOL),
        _c("mod_risposte", "Come risponde il bot dopo una sanzione (normale, compatta, cancella-dopo)", SCELTA),
        _c("mod_risposte_secondi", "Secondi prima di cancellare la risposta (5-300, solo cancella-dopo)", NUMERO),
        _c("mod_anonimo", "Nei DM delle sanzioni non nominare il moderatore (Staff di <server>)", BOOL),
        _c("mod_dm_testo_warn", "Testo del DM per il warn", TESTO),
        _c("mod_dm_testo_kick", "Testo del DM per il kick", TESTO),
        _c("mod_dm_testo_ban", "Testo del DM per il ban", TESTO),
        _c("mod_dm_testo_tempban", "Testo del DM per il tempban", TESTO),
        _c("mod_dm_testo_softban", "Testo del DM per il softban", TESTO),
        _c("mod_dm_testo_timeout", "Testo del DM per il timeout", TESTO),
        _c("mod_dm_testo_mute", "Testo del DM per il mute", TESTO),
    ),
    "moderation_report": (_c("report_channel_id", "Canale delle segnalazioni", CANALE),),
    "custom_commands": (_c("custom_command_requests_channel_id", "Canale delle richieste di comandi", CANALE),),
    "suggestions": (
        _c("suggestions_channel_id", "Canale dei suggerimenti", CANALE),
        _c("suggestions_decided_channel_id", "Canale dei suggerimenti decisi", CANALE),
    ),
    "spam_trap": (_c("spam_trap_punizione", "Punizione", SCELTA),),
    "automod": (
        _c("automod_parole_nick", "Controlla anche i soprannomi", BOOL),
        _c("odio_blocco_attivo", "Blocca le parole d'odio", BOOL),
        _c("odio_blocco_messaggio", "Messaggio di blocco", TESTO),
        _c("odio_richiami_soglia", "Richiami prima del timeout (1-20)", NUMERO),
        _c("odio_richiami_minuti", "Finestra dei richiami (minuti, 1-1440)", NUMERO),
        _c("odio_timeout_minuti", "Durata del timeout (minuti, 1-40320)", NUMERO),
        _c("immagini_filtro_attivo", "Filtro immagini sospette", BOOL),
        _c("immagini_azione", "Azione sulle immagini sospette", SCELTA),
        _c("immagini_timeout_minuti", "Timeout per le immagini sospette (minuti, 1-40320)", NUMERO),
        _c("immagini_canale_log_id", "Canale del registro delle immagini sospette", CANALE),
        _c("account_rubato_attivo", "Difesa dagli account rubati", BOOL),
        _c("account_rubato_minuti_uguali", "Account rubato: timeout per i messaggi uguali (minuti, 1-40320)", NUMERO),
        _c("account_rubato_minuti_malevole", "Account rubato: timeout per le immagini malevole (minuti, 1-40320)", NUMERO),
    ),
    "invites": (
        _c("inviti_log_channel_id", "Canale del registro degli inviti", CANALE),
        _c("inviti_link_mode", "Chi può creare un link", SCELTA),
    ),
}


def _storia():
    """Lo schema e i controlli stanno nel cog della configurazione (unica fonte): si caricano al bisogno."""
    return importlib.import_module("cogs.utility.config_history")


def campi_modulo(nome: str) -> tuple[Campo, ...]:
    """I campi del modulo, senza quelli che decidono chi può fare cosa. Vuoto se il modulo non ne ha."""
    riservate = set(_storia().CHIAVI_SOLO_PROPRIETARIO)
    return tuple(c for c in SCHEDE.get(nome, ()) if c.chiave not in riservate)


def _scelte(tipo_schema: str) -> tuple[str, ...]:
    if tipo_schema == "punizione_trappola":
        return tuple(_storia().PUNIZIONI_TRAPPOLA)
    return SCELTE.get(tipo_schema, ())


def _candidati(guild: discord.Guild, tipo: str) -> list:
    """Ruoli (senza @everyone né ruoli gestiti), canali vocali o di testo: gli stessi tipi delle opzioni dei comandi."""
    if tipo == RUOLO:
        return [r for r in guild.roles if not r.is_default() and not r.managed]
    return list(guild.voice_channels if tipo == CANALE_VOCE else guild.text_channels)


def _opzioni(guild: discord.Guild, tipo: str) -> list[tuple[int, str]]:
    """Tutte le voci: la pagina web non ha il tetto di 25 dei menu di Discord."""
    return [(v.id, v.name) for v in _candidati(guild, tipo)]


async def valori_modulo(guild: discord.Guild, nome: str) -> list[dict]:
    """Per la pagina: ogni campo con il valore attuale e le opzioni possibili."""
    schema = _storia().SETTINGS_SCHEMA
    righe = []
    for campo in campi_modulo(nome):
        riga = {"chiave": campo.chiave, "etichetta": campo.etichetta, "tipo": campo.tipo,
                "valore": await db.get_guild_setting(guild.id, campo.chiave, VALORI_DI_BASE.get(campo.chiave))}
        if campo.tipo == SCELTA:
            riga["scelte"] = _scelte(schema[campo.chiave])
        elif campo.tipo in (CANALE, CANALE_VOCE, RUOLO):
            riga["opzioni"] = _opzioni(guild, campo.tipo)
        righe.append(riga)
    return righe


def _converti(campo: Campo, testo: str, guild: discord.Guild, changed_by: int | None):
    """Dal testo del modulo al valore da salvare; None = togliere l'impostazione. Storto = ImpostazioneNonValida."""
    testo = (testo or "").strip()
    if campo.tipo == BOOL:
        if testo not in ("0", "1"):
            raise ImpostazioneNonValida("Scegli sì o no.")
        return testo == "1"
    if testo == "" and campo.tipo in (TESTO, CANALE, CANALE_VOCE, RUOLO):
        return None
    if campo.tipo == NUMERO:
        try:
            return int(testo)
        except ValueError:
            raise ImpostazioneNonValida("Scrivi un numero intero.") from None
    if campo.tipo in (CANALE, CANALE_VOCE, RUOLO):
        try:
            identificativo = int(testo)
        except ValueError:
            raise ImpostazioneNonValida("Scelta non valida.") from None
        scelto = next((v for v in _candidati(guild, campo.tipo) if v.id == identificativo), None)
        if scelto is None:
            raise ImpostazioneNonValida("Questo canale o ruolo non esiste in questo server (o è di un altro tipo).")
        if campo.chiave in RUOLI_DATI_DAL_BOT:
            autore = guild.get_member(changed_by) if changed_by else None
            motivo = "Non ti trovo in questo server." if autore is None else check_role_assignable(
                guild, scelto, autore, self_service=True
            )
            if motivo is not None:
                raise ImpostazioneNonValida(motivo)
        return identificativo
    return testo


async def imposta_impostazione(guild: discord.Guild, nome: str, chiave: str, testo: str, changed_by: int | None) -> bool:
    """
    Scrive un'impostazione del modulo con gli stessi controlli dello schema e lo storico. True se è cambiata.
    Una chiave che non è nella scheda del modulo (o è riservata al proprietario) è rifiutata.
    """
    campo = next((c for c in campi_modulo(nome) if c.chiave == chiave), None)
    if campo is None:
        raise ImpostazioneNonValida("Questa impostazione non esiste.")
    nuovo = _converti(campo, testo, guild, changed_by)
    storia = _storia()
    if nuovo is not None:
        tipo_schema = storia.SETTINGS_SCHEMA[chiave]
        controllo, descrizione = storia.CONTROLLI_PER_TIPO[tipo_schema]
        if campo.tipo == SCELTA and nuovo not in _scelte(tipo_schema):
            raise ImpostazioneNonValida("Scelta non valida.")
        if not controllo(nuovo):
            raise ImpostazioneNonValida(f"Valore non valido: deve essere {descrizione}.")
    attuale = await db.get_guild_setting(guild.id, chiave)
    if attuale == nuovo:
        return False
    if nuovo is None:
        await db.remove_guild_setting(guild.id, chiave, changed_by)
    else:
        await db.set_guild_setting(guild.id, chiave, nuovo, changed_by=changed_by)
    return True

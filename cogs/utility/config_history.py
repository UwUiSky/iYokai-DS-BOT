"""
cogs/utility/config_history.py
==================================
Comandi /admin config: storico (con filtri, vista prima/dopo e CSV) e rollback
delle modifiche, reset, esporta/importa (con controllo dello schema prima di
scrivere) e lingua del server. È solo l'interfaccia comandi: legge e scrive con i metodi di
core/database.py. Nessun controllo "modulo attivo": deve funzionare
anche prima che qualunque modulo sia acceso, come /admin setup attiva.
Funzioni coperte: SPEC §2.1, §2.3 (solo infrastruttura), §2.5, §2.6,
§2.7; REVIEW.md BUG-6, BUG-31, BUG-32; catalogo #122 (CFG-004, CFG-005).
"""

from __future__ import annotations

import json
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.command_access import (
    CHIAVI_RUOLI,
    SETTING_ADMIN_ROLE,
    TipoRuolo,
    errore_ruolo_admin,
    leggi_ruolo,
    ruolo_valido_per_server,
)
from core.database import db
from core.config_schema import imposta_lingua_server
from core.config_history_logic import (
    MAX_RIGHE_CSV,
    TIPI_MODIFICA,
    csv_storico,
    dettaglio_prima_dopo,
    fine_giornata,
    leggi_data,
)
from core.i18n import LINGUE, lingua_interazione, t as tr, testo_per
from core.invio_file import FileTroppoGrande, invia_file_su_interazione
from core.modules_updated_logic import emetti_modules_updated, stato_moduli
from core.backup_permessi_logic import LIVELLI as LIVELLI_BACKUP, SETTING_LIVELLO as SETTING_LIVELLO_BACKUP
from core.premium import registry
from core.moderation_opzioni import AZIONI_CON_DM, MAX_TIMEOUT, MIN_TIMEOUT, SETTING_RUOLI_IMMUNI
from core.spam_trap_logic import PUNIZIONI as PUNIZIONI_TRAPPOLA
from core.restore_batch_logic import MODE_CLASSIC_INVITE, MODE_ON_DEMAND_OAUTH, MODE_VERIFY_OAUTH
from core.ui_base import BaseView

SUPPORTED_LANGUAGES = LINGUE


# Un export reale pesa pochi KB: oltre questo limite il file non è nostro.
MAX_IMPORT_BYTES = 256 * 1024

# Tipo atteso per ogni chiave di `guild_config.settings` (le chiavi sono
# le costanti SETTING_* dei cog). Una chiave nuova va aggiunta qui: un test
# controlla che non ne manchi nessuna. Le chiavi che decidono chi può fare cosa
# vanno anche in CHIAVI_SOLO_PROPRIETARIO.
SETTINGS_SCHEMA = {
    "log_channel_id": "id",
    "log_webhook": "bool",
    "progressi_attivi": "bool",
    "progressi_obiettivo_server": "int_50_100000",
    "mod_log_channel_id": "id",
    "report_channel_id": "id",
    "custom_command_requests_channel_id": "id",
    "suggestions_channel_id": "id",
    "suggestions_decided_channel_id": "id",
    "ticket_category_id": "id",
    "ticket_support_role_id": "id",
    "ticket_support_role_ids": "lista_id",
    "spam_trap_staff_role_ids": "lista_id",
    "spam_trap_canali_extra": "lista_id",
    "appelli_channel_id": "id",
    "isolamento_role_id": "id",
    "isolamento_channel_id": "id",
    "verify_unverified_role_id": "id",
    "verify_extra_role_ids": "lista_id",
    "verify_captcha_tipo": "captcha_tipo",
    "verify_log_compatto": "bool",
    "verify_promemoria_minuti": "int_0_1440",
    "verify_scadenza_minuti": "int_0_1440",
    "verify_azione_scadenza": "azione_verifica",
    "verify_azione_fallita": "azione_verifica",
    "verify_solo_sospetti": "bool",
    "verify_azione_eta": "azione_eta",
    "verify_sospesa_fino": "epoch",
    "mute_role_id": "id",
    "admin_role_id": "id",
    "mod_role_id": "id",
    "modban_role_id": "id",
    "backup_restore_mode": "modalita_restore",
    "backup_auto_invite_on_join": "bool",
    "backup_livello_permessi": "livello_backup",
    "logging_soundboard_watermark": "data_iso",
    "music_max_volume": "int_0_200",
    "ticket_max_per_utente": "int_1_5",
    "music_max_track_minutes": "int_0_1440",
    "music_stay_when_queue_ends": "bool",
    "music_allowed_voice_channel_id": "id",
    "music_banned_words": "testo_300",
    "music_idle_minutes": "int_0_60",
    "music_known_sites_only": "bool",
    # Politica dei comandi (core/command_policy.py)
    "policy_comandi_off": "lista_comandi",
    "policy_canali_ok": "lista_id",
    "policy_canali_no": "lista_id",
    "policy_ignora_ruoli": "lista_id",
    "policy_ignora_utenti": "lista_id",
    # Opzioni di moderazione (core/moderation_opzioni.py)
    "mod_ban_giorni_messaggi": "int_0_7",
    "mod_timeout_predefinito": "durata_timeout",
    "mod_dm_spenti": "azioni_dm",
    "mod_ruoli_immuni": "lista_id",
    "mod_casi_esterni": "bool",
    "mod_avviso_warn_soglia": "int_0_200",
    "mod_avviso_rientro": "bool",
    "spam_trap_punizione": "punizione_trappola",
    # Parole vietate dell'AutoMod (core/automod_parole_opzioni.py)
    "automod_parole_base": "bool",
    "automod_parole_nick": "bool",
    "automod_parole_proprie": "lista_parole",
    "automod_parole_lecite": "lista_parole",
    # Difesa dalle parole d'odio (core/odio_opzioni.py, D35)
    "odio_blocco_attivo": "bool",
    "odio_blocco_messaggio": "testo_150",
    "odio_richiami_soglia": "int_1_20",
    "odio_richiami_minuti": "int_1_1440",
    "odio_timeout_minuti": "int_1_40320",
    # Inviti e link personali (core/invite_links_logic.py)
    "inviti_log_channel_id": "id",
    "inviti_link_role_id": "id",
    "inviti_link_mode": "modalita_link_inviti",
}


MAX_ID_DISCORD = 2**63 - 1  # gli ID stanno in un BIGINT
MAX_ID_IN_LISTA = 250  # un server non ha più di 250 ruoli
MAX_NOMI_NEL_MESSAGGIO = 5


def _e_un_id(valore) -> bool:
    # bool è sottoclasse di int: True non è un ID.
    return isinstance(valore, int) and not isinstance(valore, bool) and 0 < valore <= MAX_ID_DISCORD


def _e_una_lista_di_id(valore) -> bool:
    return (
        isinstance(valore, list)
        and len(valore) <= MAX_ID_IN_LISTA
        and all(_e_un_id(elemento) for elemento in valore)
    )


def _e_una_data_iso(valore) -> bool:
    if not isinstance(valore, str) or not valore.isascii():
        return False
    try:
        datetime.fromisoformat(valore)
    except ValueError:
        return False
    return True


def _intero_tra(minimo: int, massimo: int):
    # bool è sottoclasse di int: True non è un numero valido.
    return lambda valore: (
        isinstance(valore, int) and not isinstance(valore, bool) and minimo <= valore <= massimo
    )


# Per ogni tipo di SETTINGS_SCHEMA: il controllo e come descriverlo.
CONTROLLI_PER_TIPO = {
    "id": (_e_un_id, "un ID numerico"),
    "lista_id": (_e_una_lista_di_id, "un elenco di ID numerici"),
    "lista_comandi": (
        lambda valore: isinstance(valore, list)
        and len(valore) <= MAX_ID_IN_LISTA
        and all(isinstance(v, str) and 0 < len(v) <= 100 for v in valore),
        "un elenco di percorsi di comandi",
    ),
    "bool": (lambda valore: isinstance(valore, bool), "true oppure false"),
    "modalita_link_inviti": (
        lambda valore: valore in ("tutti", "crea_invito", "ruolo", "spento"),
        "tutti, crea_invito, ruolo oppure spento",
    ),
    "modalita_restore": (
        lambda valore: valore in (MODE_VERIFY_OAUTH, MODE_ON_DEMAND_OAUTH, MODE_CLASSIC_INVITE),
        "una modalità di restore valida",
    ),
    "livello_backup": (lambda valore: valore in LIVELLI_BACKUP, "admin_tutto, admin_crea oppure solo_owner"),
    "captcha_tipo": (lambda valore: valore in ("testo", "immagine"), "«testo» oppure «immagine»"),
    "azione_verifica": (
        lambda valore: valore in ("niente", "quarantena", "kick", "ban"), "niente, quarantena, kick oppure ban"
    ),
    "azione_eta": (lambda valore: valore in ("attendi", "kick"), "attendi oppure kick"),
    "epoch": (_intero_tra(0, 4_102_444_800), "un istante in secondi, tra 0 e il 2100"),
    "data_iso": (_e_una_data_iso, "una data in formato ISO"),
    "int_0_200": (_intero_tra(0, 200), "un intero tra 0 e 200"),
    "int_1_5": (_intero_tra(1, 5), "un intero tra 1 e 5"),
    "int_0_60": (_intero_tra(0, 60), "un intero tra 0 e 60"),
    "testo_300": (lambda valore: isinstance(valore, str) and len(valore) <= 300, "un testo fino a 300 caratteri"),
    "testo_150": (lambda valore: isinstance(valore, str) and len(valore) <= 150, "un testo fino a 150 caratteri"),
    "int_1_20": (_intero_tra(1, 20), "un intero tra 1 e 20"),
    "int_1_1440": (_intero_tra(1, 1440), "un intero tra 1 e 1440"),
    "int_1_40320": (_intero_tra(1, 40320), "un intero tra 1 e 40320"),
    "int_0_1440": (_intero_tra(0, 1440), "un intero tra 0 e 1440"),
    "int_0_7": (_intero_tra(0, 7), "un intero tra 0 e 7"),
    "int_50_100000": (_intero_tra(50, 100_000), "un intero tra 50 e 100000"),
    "punizione_trappola": (lambda valore: valore in PUNIZIONI_TRAPPOLA, ", ".join(PUNIZIONI_TRAPPOLA)),
    "durata_timeout": (_intero_tra(MIN_TIMEOUT, MAX_TIMEOUT), "secondi tra 60 e 2419200 (28 giorni)"),
    "lista_parole": (
        lambda valore: isinstance(valore, list)
        and len(valore) <= 100
        and all(isinstance(v, str) and 0 < len(v) <= 60 for v in valore),
        "un elenco di al massimo 100 parole (60 caratteri l'una)",
    ),
    "azioni_dm": (
        lambda valore: isinstance(valore, list) and all(v in AZIONI_CON_DM for v in valore),
        "un elenco di azioni tra " + ", ".join(AZIONI_CON_DM),
    ),
}


def _elenco_nomi(nomi) -> str:
    """
    Primi nomi di un elenco, resi innocui per un messaggio Discord: solo
    ASCII (niente \\u0000 o surrogati isolati), accorciati, senza backtick.
    """
    nomi = list(nomi)
    mostrati = [
        ascii(str(nome)[:40]).replace("`", "'") for nome in nomi[:MAX_NOMI_NEL_MESSAGGIO]
    ]
    altri = len(nomi) - len(mostrati)
    return ", ".join(mostrati) + (f" e altri {altri}" if altri > 0 else "")


def _errore_settings(settings: dict) -> str | None:
    sconosciute = [chiave for chiave in settings if chiave not in SETTINGS_SCHEMA]
    if sconosciute:
        return f"`settings` contiene chiavi sconosciute: {_elenco_nomi(sconosciute)}."
    for chiave, valore in settings.items():
        controllo, descrizione = CONTROLLI_PER_TIPO[SETTINGS_SCHEMA[chiave]]
        if not controllo(valore):
            return f"Il valore di `{chiave}` non è valido: deve essere {descrizione}."
    return None


def errore_ruoli_del_bot(guild: discord.Guild, settings: dict) -> str | None:
    """
    Le chiavi dei ruoli admin/mod/modban devono essere ruoli veri di
    QUESTO server: l'id del server (@everyone) farebbe passare tutti.
    """
    for chiave in CHIAVI_RUOLI:
        if chiave in settings and not ruolo_valido_per_server(guild, settings[chiave]):
            return (
                f"Il valore di `{chiave}` non è valido: deve essere "
                f"un ruolo esistente di questo server."
            )
    return None


async def errore_cambio_ruolo_admin(guild: discord.Guild, autore, settings: dict) -> str | None:
    """D28: un ruolo admin del bot nuovo lo sceglie solo chi ha «Amministratore» o il proprietario."""
    nuovo = settings.get(SETTING_ADMIN_ROLE)
    if nuovo is None:
        return None  # nessun ruolo admin nel file: si toglie, e toglierlo non apre nulla
    return errore_ruolo_admin(guild, autore, await leggi_ruolo(guild.id, TipoRuolo.ADMIN), nuovo)


# Chiavi che decidono chi può fare cosa: le cambia solo il proprietario del server,
# altrimenti un admin potrebbe alzarsi i permessi con un import o un rollback.
CHIAVI_SOLO_PROPRIETARIO = (SETTING_LIVELLO_BACKUP, SETTING_RUOLI_IMMUNI, "automod_parole_base")


async def errore_chiavi_solo_proprietario(guild: discord.Guild, autore, settings: dict) -> str | None:
    """Rifiuta il cambio di una chiave riservata al proprietario se chi lo chiede non lo è."""
    if getattr(autore, "id", None) == guild.owner_id:
        return None
    for chiave in CHIAVI_SOLO_PROPRIETARIO:
        if chiave in settings and settings[chiave] != await db.get_guild_setting(guild.id, chiave):
            return f"`{chiave}` lo può cambiare solo il proprietario del server."
    return None


def errore_schema_import(dati) -> str | None:
    """
    Controlla lo schema di un file per /admin config import PRIMA di scrivere.
    Restituisce il motivo del rifiuto in italiano, oppure None se valido.
    Moduli e chiavi sconosciuti fanno rifiutare tutto il file (non
    vengono ignorati): meglio nessuna modifica che un import a metà.
    """
    if not isinstance(dati, dict) or not {"modules", "settings", "language"} <= dati.keys():
        return "Il file non ha il formato atteso (mancano modules/settings/language)."
    modules, settings, language = dati["modules"], dati["settings"], dati["language"]
    if not isinstance(modules, dict) or not all(
        isinstance(attivo, bool) for attivo in modules.values()
    ):
        return "`modules` deve essere un elenco nome → true/false."
    sconosciuti = [nome for nome in modules if registry.get(nome) is None]
    if sconosciuti:
        return f"`modules` contiene moduli sconosciuti: {_elenco_nomi(sconosciuti)}."
    if not isinstance(settings, dict):
        return "`settings` deve essere un elenco chiave → valore."
    if not isinstance(language, str) or language not in SUPPORTED_LANGUAGES:
        return f"Lingua non supportata. Ammesse: {', '.join(SUPPORTED_LANGUAGES)}."
    return _errore_settings(settings)


def _rifiuta_costante(nome: str):
    """json.loads accetta NaN e Infinity, che non sono JSON e PostgreSQL rifiuta."""
    raise ValueError(f"costante non ammessa: {nome}")


def leggi_json_import(grezzo: bytes):
    """
    Decodifica il file di /admin config import (UTF-8, BOM ammesso). Solleva
    ValueError o RecursionError se non è un JSON accettabile: NaN,
    interi smisurati, annidamento troppo profondo, byte non UTF-8.
    """
    return json.loads(grezzo.decode("utf-8-sig"), parse_constant=_rifiuta_costante)


# Limiti di Discord: 2000 caratteri per un messaggio, 4096 per la
# descrizione di un embed. Si resta un po' sotto.
MAX_CARATTERI_VALORE = 80
MAX_CARATTERI_CONFERMA = 1900
MAX_CARATTERI_STORICO = 3900


def _tronca(testo: str, massimo: int) -> str:
    return testo if len(testo) <= massimo else testo[: massimo - 1] + "…"


def _e_una_configurazione_intera(value) -> bool:
    """Il valore salvato nello storico da reset/import: tutta la configurazione."""
    return (
        isinstance(value, dict)
        and isinstance(value.get("modules"), dict)
        and isinstance(value.get("settings"), dict)
    )


def _format_value(value) -> str:
    """Un valore dello storico in poche parole: mai l'elenco intero."""
    if value is None:
        return "*(mai impostato)*"
    if _e_una_configurazione_intera(value):
        return f"*({len(value['modules'])} moduli, {len(value['settings'])} impostazioni)*"
    testo = str(value).replace("`", "'")  # un backtick chiuderebbe il blocco
    return f"`{_tronca(testo, MAX_CARATTERI_VALORE)}`"


def _chiavi_diverse(prima: dict, dopo: dict) -> list[str]:
    tutte = prima.keys() | dopo.keys()
    return sorted(chiave for chiave in tutte if prima.get(chiave) != dopo.get(chiave))


def _riassunto_cambi(nome: str, prima: dict, dopo: dict) -> str:
    """Es. "32 moduli ('anti_nuke', 'automod' e altri 30)"."""
    diverse = _chiavi_diverse(prima, dopo)
    if not diverse:
        return f"0 {nome}"
    return f"{len(diverse)} {nome} ({_elenco_nomi(diverse)})"


def testo_conferma_rollback(entry) -> str:
    """Domanda di conferma di /admin config rollback, sempre sotto il limite di Discord."""
    vecchio, nuovo = entry.old_value, entry.new_value
    if _e_una_configurazione_intera(vecchio) and _e_una_configurazione_intera(nuovo):
        testo = (
            f"Confermi di voler ripristinare l'intera configurazione a com'era prima di "
            f"questo `{entry.change_type}`? Cambiano "
            f"{_riassunto_cambi('moduli', nuovo['modules'], vecchio['modules'])} e "
            f"{_riassunto_cambi('impostazioni', nuovo['settings'], vecchio['settings'])}; "
            f"lingua: {_format_value(nuovo.get('language'))} → "
            f"{_format_value(vecchio.get('language'))}."
        )
    else:
        testo = (
            f"Confermi di voler ripristinare `{_tronca(entry.key_name, MAX_CARATTERI_VALORE)}` a "
            f"{_format_value(vecchio)} (era {_format_value(nuovo)})?"
        )
    return _tronca(testo, MAX_CARATTERI_CONFERMA)


def righe_storico(voci) -> str:
    """
    Una riga per voce, dalla più recente. Se non stanno tutte nella
    descrizione di un embed ci si ferma prima e lo si dice.
    """
    righe, lunghezza = [], 0
    for voce in voci:
        autore = f"<@{voce.changed_by}>" if voce.changed_by else "sconosciuto"
        riga = (
            f"`#{voce.id}` **{voce.change_type}** "
            f"`{_tronca(voce.key_name, MAX_CARATTERI_VALORE)}`: "
            f"{_format_value(voce.old_value)} → {_format_value(voce.new_value)} — {autore}"
        )
        if lunghezza + len(riga) + 1 > MAX_CARATTERI_STORICO:
            righe.append(f"… e altre {len(voci) - len(righe)} voci più vecchie.")
            break
        righe.append(riga)
        lunghezza += len(riga) + 1
    return "\n".join(righe)


class RollbackConfirmView(BaseView):
    """
    Conferma a due passaggi (non persistente — è un'interazione breve
    legata a un singolo comando, non un pannello a vita lunga come i
    ticket o il verify: stesso ragionamento già fatto per
    AppealActionsView in cogs/security/spam_trap.py).
    """

    def __init__(self, entry_id: int, requested_by_id: int) -> None:
        super().__init__(timeout=60)
        self.entry_id = entry_id
        self.requested_by_id = requested_by_id

    async def _errore_ruoli_da_ripristinare(self, guild, autore) -> str | None:
        """
        Il rollback non deve rimettere un ruolo del bot non valido (vedi
        errore_ruoli_del_bot), né un ruolo admin scelto da chi non può (D28).
        """
        entry = await db.get_config_history_entry(self.entry_id)
        if entry is None or guild is None:
            return None
        if entry.change_type == "setting" and entry.old_value is not None:
            da_ripristinare = {entry.key_name: entry.old_value}
        elif entry.change_type in ("reset", "import") and isinstance(entry.old_value, dict):
            impostazioni = entry.old_value.get("settings")
            da_ripristinare = impostazioni if isinstance(impostazioni, dict) else {}
        else:
            return None
        return (
            errore_ruoli_del_bot(guild, da_ripristinare)
            or await errore_cambio_ruolo_admin(guild, autore, da_ripristinare)
            or await errore_chiavi_solo_proprietario(guild, autore, da_ripristinare)
        )

    @discord.ui.button(label="Conferma rollback", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.requested_by_id:
            await interaction.response.send_message(
                await testo_per(interaction, "cfg_solo_chi_chiede_rollback_conferma"), ephemeral=True
            )
            return

        errore = await self._errore_ruoli_da_ripristinare(interaction.guild, interaction.user)
        if errore is not None:
            for child in self.children:
                child.disabled = True
            self.stop()
            await interaction.response.edit_message(content=f"❌ {errore}", view=self)
            return

        # M 10.13: il rollback può cambiare più moduli (reset/import): si
        # confronta lo stato prima e dopo per emettere `modules_updated`.
        guild_id = interaction.guild.id if interaction.guild else None
        prima = await stato_moduli(db, guild_id) if guild_id else {}
        riuscito = await db.rollback_config_change(
            self.entry_id, rolled_back_by=interaction.user.id
        )
        if riuscito and guild_id:
            emetti_modules_updated(
                interaction.client, guild_id, prima, await stato_moduli(db, guild_id),
                interaction.user.id,
            )
        for child in self.children:
            child.disabled = True
        self.stop()

        if riuscito:
            await interaction.response.edit_message(
                content=await testo_per(interaction, "cfg_rollback_fatto"), view=self
            )
        else:
            await interaction.response.edit_message(
                content=await testo_per(interaction, "cfg_rollback_impossibile"), view=self
            )

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.requested_by_id:
            await interaction.response.send_message(
                await testo_per(interaction, "cfg_solo_chi_chiede_rollback_annulla"), ephemeral=True
            )
            return
        for child in self.children:
            child.disabled = True
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "cfg_rollback_annullato"), view=self)


class ResetConfirmView(BaseView):
    """
    SPEC.md §2.1: conferma a due passaggi, stesso schema di
    RollbackConfirmView — un reset disattiva TUTTI i moduli e
    svuota tutte le settings, non un'azione da eseguire per errore
    con un solo click.
    """

    def __init__(self, guild_id: int, requested_by_id: int) -> None:
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.requested_by_id = requested_by_id

    @discord.ui.button(label="Conferma reset", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.requested_by_id:
            await interaction.response.send_message(
                await testo_per(interaction, "cfg_solo_chi_chiede_reset_conferma"), ephemeral=True
            )
            return

        prima = await stato_moduli(db, self.guild_id)
        await db.reset_guild_config(self.guild_id, changed_by=interaction.user.id)
        emetti_modules_updated(
            interaction.client, self.guild_id, prima, await stato_moduli(db, self.guild_id),
            interaction.user.id,
        )
        for child in self.children:
            child.disabled = True
        self.stop()
        await interaction.response.edit_message(
            content=await testo_per(interaction, "cfg_reset_fatto"),
            view=self,
        )

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.requested_by_id:
            await interaction.response.send_message(
                await testo_per(interaction, "cfg_solo_chi_chiede_reset_annulla"), ephemeral=True
            )
            return
        for child in self.children:
            child.disabled = True
        self.stop()
        await interaction.response.edit_message(content=await testo_per(interaction, "cfg_reset_annullato"), view=self)


class ConfigHistoryCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "admin",
        nome="history",
        descrizione="Mostra le ultime modifiche alla configurazione.",
        sottogruppo=("config", "Configurazione: canali, storico, ripristino ed esportazione"),
    )
    @app_commands.describe(
        limit="Quante voci mostrare (default 10, massimo 25)",
        chi="Solo le modifiche fatte da questa persona",
        tipo="Solo questo tipo di modifica",
        dal="Dal giorno (es. 2026-10-01 o 01/10/2026)",
        al="Fino al giorno compreso (stesso formato)",
        voce="Numero di una voce: mostra il valore prima e dopo",
        come_csv="Scarica le voci trovate (fino a 5000) come file CSV",
    )
    @app_commands.choices(tipo=[app_commands.Choice(name=n, value=n) for n in TIPI_MODIFICA])
    async def history(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 25] = 10,
        chi: discord.Member | None = None,
        tipo: app_commands.Choice[str] | None = None,
        dal: app_commands.Range[str, 1, 20] | None = None,
        al: app_commands.Range[str, 1, 20] | None = None,
        voce: app_commands.Range[int, 1, 2**53 - 1] | None = None,
        come_csv: bool = False,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "accesso_solo_server"), ephemeral=True
            )
            return

        if voce is not None:
            entry = await db.get_config_history_entry(voce)
            if entry is None or entry.guild_id != guild.id:  # mai la voce di un altro server
                await interaction.response.send_message(await testo_per(interaction, "cfg_voce_non_trovata"), ephemeral=True)
                return
            await interaction.response.send_message(dettaglio_prima_dopo(entry), ephemeral=True)
            return

        data_dal, data_al = leggi_data(dal), leggi_data(al)
        if (dal and data_dal is None) or (al and data_al is None):
            await interaction.response.send_message(
                await testo_per(interaction, "cfg_data_non_valida"), ephemeral=True
            )
            return
        voci = await db.get_config_history_filtrato(
            guild.id,
            limit=MAX_RIGHE_CSV if come_csv else limit,
            changed_by=chi.id if chi else None,
            change_type=tipo.value if tipo else None,
            dal=data_dal,
            prima_del=fine_giornata(data_al) if data_al else None,
        )
        if not voci:
            await interaction.response.send_message(
                await testo_per(interaction, "cfg_nessuna_modifica"), ephemeral=True
            )
            return

        if come_csv:
            try:
                await invia_file_su_interazione(
                    interaction,
                    csv_storico(voci),
                    f"iyokai-storico-{guild.id}.csv",
                    contenuto=f"{len(voci)} modifiche.",
                    dividi=True,
                    ephemeral=True,
                )
            except FileTroppoGrande:
                await interaction.response.send_message(
                    await testo_per(interaction, "cfg_file_troppo_grande_filtri"), ephemeral=True
                )
            return

        embed = discord.Embed(
            title="📜 Storico configurazione",
            description=righe_storico(voci),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="/admin config rollback <id> annulla una voce; voce:<id> mostra prima e dopo.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo(
        "admin",
        nome="rollback",
        descrizione="Ripristina il valore precedente di una modifica.",
        sottogruppo=("config", "Configurazione: canali, storico, ripristino ed esportazione"),
    )
    @app_commands.describe(entry_id="ID della voce di storico (mostrato da /admin config history)")
    async def rollback(self, interaction: discord.Interaction, entry_id: int) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "accesso_solo_server"), ephemeral=True
            )
            return

        entry = await db.get_config_history_entry(entry_id)
        if entry is None or entry.guild_id != guild.id:
            await interaction.response.send_message(
                await testo_per(interaction, "cfg_voce_id_non_trovata"),
                ephemeral=True,
            )
            return

        view = RollbackConfirmView(entry_id, interaction.user.id)
        await interaction.response.send_message(
            testo_conferma_rollback(entry),
            view=view,
            ephemeral=True,
        )

    @comando_di_gruppo(
        "admin",
        nome="reset",
        descrizione="Azzera la configurazione di questo server.",
        sottogruppo=("config", "Configurazione: canali, storico, ripristino ed esportazione"),
    )
    async def reset(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "accesso_solo_server"), ephemeral=True
            )
            return

        view = ResetConfirmView(guild.id, interaction.user.id)
        await interaction.response.send_message(
            await testo_per(interaction, "cfg_reset_chiedi"),
            view=view,
            ephemeral=True,
        )

    @comando_di_gruppo(
        "admin",
        nome="export",
        descrizione="Esporta la configurazione di questo server in un file.",
        sottogruppo=("config", "Configurazione: canali, storico, ripristino ed esportazione"),
    )
    async def export(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "accesso_solo_server"), ephemeral=True
            )
            return

        config = await db.get_full_config(guild.id)
        # #136: l'import rifiuta `null` (anche dentro le liste) e le chiavi
        # fuori schema: l'export le toglie, "vuota" e "assente" sono uguali.
        config["settings"] = {
            chiave: ([e for e in valore if e is not None] if isinstance(valore, list) else valore)
            for chiave, valore in config["settings"].items()
            if valore is not None and chiave in SETTINGS_SCHEMA
        }
        contenuto = json.dumps(config, indent=2, ensure_ascii=False)
        try:
            # Un export che non sta in un file non si divide: l'import vuole un file solo.
            await invia_file_su_interazione(
                interaction,
                contenuto.encode("utf-8"),
                f"iyokai-config-{guild.id}.json",
                contenuto=(
                    "Configurazione esportata. Usa /admin config import su un altro server "
                    "per applicarla (SOVRASCRIVE tutto ciò che c'è già)."
                ),
                dividi=False,
                ephemeral=True,
            )
        except FileTroppoGrande:
            await interaction.response.send_message(
                await testo_per(interaction, "cfg_export_troppo_grande"),
                ephemeral=True,
            )

    @comando_di_gruppo(
        "admin",
        nome="import",
        descrizione="Importa una configurazione da un file esportato con /admin config export.",
        sottogruppo=("config", "Configurazione: canali, storico, ripristino ed esportazione"),
    )
    @app_commands.describe(file="Il file .json prodotto da /admin config export")
    async def import_config(
        self, interaction: discord.Interaction, file: discord.Attachment
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "accesso_solo_server"), ephemeral=True
            )
            return

        if file.size > MAX_IMPORT_BYTES:
            await interaction.response.send_message(
                await testo_per(interaction, "cfg_import_troppo_grande"),
                ephemeral=True,
            )
            return

        grezzo = await file.read()
        try:
            dati = leggi_json_import(grezzo)
        except (ValueError, RecursionError):
            await interaction.response.send_message(
                await testo_per(interaction, "cfg_import_json_non_valido"),
                ephemeral=True,
            )
            return

        errore = errore_schema_import(dati)
        if errore is not None:
            await interaction.response.send_message(f"❌ {errore}", ephemeral=True)
            return

        errore = (
            errore_ruoli_del_bot(guild, dati["settings"])
            or await errore_cambio_ruolo_admin(guild, interaction.user, dati["settings"])
            or await errore_chiavi_solo_proprietario(guild, interaction.user, dati["settings"])
        )
        if errore is not None:
            await interaction.response.send_message(f"❌ {errore}", ephemeral=True)
            return

        prima = await stato_moduli(db, guild.id)
        await db.import_full_config(
            guild.id,
            modules=dati["modules"],
            settings=dati["settings"],
            language=dati["language"],
            changed_by=interaction.user.id,
        )
        emetti_modules_updated(
            interaction.client, guild.id, prima, await stato_moduli(db, guild.id),
            interaction.user.id,
        )
        await interaction.response.send_message(
            await testo_per(
                interaction, "cfg_import_fatto",
                moduli=len(dati["modules"]), impostazioni=len(dati["settings"]), lingua=dati["language"],
            ),
            ephemeral=True,
        )

    # ================================================================
    # SPEC.md §2.3 — Lingua per server
    # ================================================================
    @comando_di_gruppo(
        "admin",
        nome="show",
        descrizione="Mostra la lingua impostata per questo server.",
        sottogruppo=("lingua", "Lingua del server"),
    )
    async def language_show(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        lingua = await db.get_guild_language(interaction.guild.id)
        mia = await lingua_interazione(interaction)
        await interaction.response.send_message(tr("lingua_attuale_server", mia, lingua=lingua), ephemeral=True)

    @comando_di_gruppo(
        "admin",
        nome="set",
        descrizione="Imposta la lingua di questo server.",
        sottogruppo=("lingua", "Lingua del server"),
    )
    @app_commands.describe(language="Codice lingua")
    @app_commands.choices(
        language=[app_commands.Choice(name=n, value=v) for n, v in (("Italiano", "it"), ("English", "en"))]
    )
    async def language_set(
        self, interaction: discord.Interaction, language: app_commands.Choice[str]
    ) -> None:
        if interaction.guild is None:
            return
        await imposta_lingua_server(interaction.guild.id, language.value, interaction.user.id)
        await interaction.response.send_message(
            tr("lingua_server_impostata", language.value, lingua=language.value), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConfigHistoryCog(bot))

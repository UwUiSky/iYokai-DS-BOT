"""
cogs/utility/config_history.py
==================================
Comandi /config: storico e rollback delle modifiche, reset, esporta/
importa (con controllo dello schema prima di scrivere) e lingua del
server. È solo l'interfaccia comandi: legge e scrive con i metodi di
core/database.py. Nessun controllo "modulo attivo": deve funzionare
anche prima che qualunque modulo sia acceso, come /setup.
Funzioni coperte: SPEC §2.1, §2.3 (solo infrastruttura), §2.5, §2.6,
§2.7; REVIEW.md BUG-6, BUG-31, BUG-32.
"""

from __future__ import annotations

import io
import json
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.premium import registry
from core.restore_batch_logic import MODE_CLASSIC_INVITE, MODE_ON_DEMAND_OAUTH, MODE_VERIFY_OAUTH
from core.ui_base import BaseView

SUPPORTED_LANGUAGES = ("it", "en")


# Un export reale pesa pochi KB: oltre questo limite il file non è nostro.
MAX_IMPORT_BYTES = 256 * 1024

# Tipo atteso per ogni chiave di `guild_config.settings` (le chiavi sono
# le costanti SETTING_* dei cog). Una chiave nuova va aggiunta qui: un
# test controlla che non ne manchi nessuna.
SETTINGS_SCHEMA = {
    "log_channel_id": "id",
    "mod_log_channel_id": "id",
    "report_channel_id": "id",
    "custom_command_requests_channel_id": "id",
    "suggestions_channel_id": "id",
    "ticket_category_id": "id",
    "ticket_support_role_id": "id",
    "ticket_support_role_ids": "lista_id",
    "spam_trap_staff_role_ids": "lista_id",
    "mute_role_id": "id",
    "admin_role_id": "id",
    "mod_role_id": "id",
    "modban_role_id": "id",
    "backup_restore_mode": "modalita_restore",
    "backup_auto_invite_on_join": "bool",
    "logging_soundboard_watermark": "data_iso",
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


# Per ogni tipo di SETTINGS_SCHEMA: il controllo e come descriverlo.
CONTROLLI_PER_TIPO = {
    "id": (_e_un_id, "un ID numerico"),
    "lista_id": (_e_una_lista_di_id, "un elenco di ID numerici"),
    "bool": (lambda valore: isinstance(valore, bool), "true oppure false"),
    "modalita_restore": (
        lambda valore: valore in (MODE_VERIFY_OAUTH, MODE_ON_DEMAND_OAUTH, MODE_CLASSIC_INVITE),
        "una modalità di restore valida",
    ),
    "data_iso": (_e_una_data_iso, "una data in formato ISO"),
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


def errore_schema_import(dati) -> str | None:
    """
    Controlla lo schema di un file per /config import PRIMA di scrivere.
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
    Decodifica il file di /config import (UTF-8, BOM ammesso). Solleva
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
    """Domanda di conferma di /config rollback, sempre sotto il limite di Discord."""
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

    @discord.ui.button(label="Conferma rollback", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.requested_by_id:
            await interaction.response.send_message(
                "Solo chi ha richiesto il rollback può confermarlo.", ephemeral=True
            )
            return

        riuscito = await db.rollback_config_change(
            self.entry_id, rolled_back_by=interaction.user.id
        )
        for child in self.children:
            child.disabled = True
        self.stop()

        if riuscito:
            await interaction.response.edit_message(
                content="✅ Rollback eseguito.", view=self
            )
        else:
            await interaction.response.edit_message(
                content="❌ Questa voce di storico non esiste più o non si può ripristinare.", view=self
            )

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.requested_by_id:
            await interaction.response.send_message(
                "Solo chi ha richiesto il rollback può annullarlo.", ephemeral=True
            )
            return
        for child in self.children:
            child.disabled = True
        self.stop()
        await interaction.response.edit_message(content="Rollback annullato.", view=self)


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
                "Solo chi ha richiesto il reset può confermarlo.", ephemeral=True
            )
            return

        await db.reset_guild_config(self.guild_id, changed_by=interaction.user.id)
        for child in self.children:
            child.disabled = True
        self.stop()
        await interaction.response.edit_message(
            content="✅ Configurazione azzerata: nessun modulo attivo, nessuna "
            "impostazione, lingua tornata a italiano. Usa /config rollback per "
            "annullare se necessario.",
            view=self,
        )

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.requested_by_id:
            await interaction.response.send_message(
                "Solo chi ha richiesto il reset può annullarlo.", ephemeral=True
            )
            return
        for child in self.children:
            child.disabled = True
        self.stop()
        await interaction.response.edit_message(content="Reset annullato.", view=self)


class ConfigHistoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    config_group = app_commands.Group(
        name="config", description="Storico delle modifiche di configurazione del server."
    )

    @config_group.command(
        name="history", description="[Admin] Mostra le ultime modifiche alla configurazione."
    )
    @app_commands.describe(limit="Quante voci mostrare (default 10, massimo 25)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def history(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 25] = 10,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        voci = await db.get_config_history(guild.id, limit=limit)
        if not voci:
            await interaction.response.send_message(
                "Nessuna modifica registrata finora.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📜 Storico configurazione",
            description=righe_storico(voci),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Usa /config rollback <id> per annullare una voce specifica.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config_group.command(
        name="rollback", description="[Admin] Ripristina il valore precedente di una modifica."
    )
    @app_commands.describe(entry_id="ID della voce di storico (mostrato da /config history)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def rollback(self, interaction: discord.Interaction, entry_id: int) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        entry = await db.get_config_history_entry(entry_id)
        if entry is None or entry.guild_id != guild.id:
            await interaction.response.send_message(
                "Nessuna voce di storico trovata con questo ID in questo server.",
                ephemeral=True,
            )
            return

        view = RollbackConfirmView(entry_id, interaction.user.id)
        await interaction.response.send_message(
            testo_conferma_rollback(entry),
            view=view,
            ephemeral=True,
        )

    @config_group.command(
        name="reset", description="[Admin] Azzera la configurazione di questo server."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reset(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        view = ResetConfirmView(guild.id, interaction.user.id)
        await interaction.response.send_message(
            "⚠️ Confermi di voler disattivare **tutti** i moduli e azzerare "
            "**tutte** le impostazioni di questo server? L'operazione è "
            "annullabile con /config rollback.",
            view=view,
            ephemeral=True,
        )

    @config_group.command(
        name="export", description="[Admin] Esporta la configurazione di questo server in un file."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def export(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
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
        file = discord.File(
            io.BytesIO(contenuto.encode("utf-8")),
            filename=f"iyokai-config-{guild.id}.json",
        )
        await interaction.response.send_message(
            "Configurazione esportata. Usa /config import su un altro server "
            "per applicarla (SOVRASCRIVE tutto ciò che c'è già).",
            file=file,
            ephemeral=True,
        )

    @config_group.command(
        name="import", description="[Admin] Importa una configurazione da un file esportato con /config export."
    )
    @app_commands.describe(file="Il file .json prodotto da /config export")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def import_config(
        self, interaction: discord.Interaction, file: discord.Attachment
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        if file.size > MAX_IMPORT_BYTES:
            await interaction.response.send_message(
                "Il file è troppo grande per essere una configurazione esportata.",
                ephemeral=True,
            )
            return

        grezzo = await file.read()
        try:
            dati = leggi_json_import(grezzo)
        except (ValueError, RecursionError):
            await interaction.response.send_message(
                "Il file non è un JSON valido (probabilmente non prodotto da /config export).",
                ephemeral=True,
            )
            return

        errore = errore_schema_import(dati)
        if errore is not None:
            await interaction.response.send_message(f"❌ {errore}", ephemeral=True)
            return

        await db.import_full_config(
            guild.id,
            modules=dati["modules"],
            settings=dati["settings"],
            language=dati["language"],
            changed_by=interaction.user.id,
        )
        await interaction.response.send_message(
            f"✅ Configurazione importata: {len(dati['modules'])} moduli, "
            f"{len(dati['settings'])} impostazioni, lingua `{dati['language']}`. "
            f"Annullabile con /config rollback.",
            ephemeral=True,
        )

    # ================================================================
    # SPEC.md §2.3 — Lingua per server
    # ================================================================
    language_group = app_commands.Group(
        name="language", description="Lingua del server (infrastruttura, vedi SPEC.md §2.3).", parent=config_group
    )

    @language_group.command(name="show", description="Mostra la lingua impostata per questo server.")
    async def language_show(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        lingua = await db.get_guild_language(interaction.guild.id)
        await interaction.response.send_message(f"Lingua attuale: `{lingua}`.", ephemeral=True)

    @language_group.command(name="set", description="[Admin] Imposta la lingua di questo server.")
    @app_commands.describe(language="Codice lingua")
    @app_commands.choices(
        language=[app_commands.Choice(name=l, value=l) for l in SUPPORTED_LANGUAGES]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def language_set(
        self, interaction: discord.Interaction, language: app_commands.Choice[str]
    ) -> None:
        if interaction.guild is None:
            return
        await db.set_guild_language(interaction.guild.id, language.value, changed_by=interaction.user.id)
        await interaction.response.send_message(
            f"Lingua impostata su `{language.value}`. Nota: solo una parte "
            f"limitata dei messaggi del bot usa questa impostazione per ora.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConfigHistoryCog(bot))

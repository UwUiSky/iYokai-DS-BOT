"""
cogs/voice_temp/voice_temp.py
================================
Vocali temporanei: modalità automatica (entra nel canale generatore
-> il bot crea un canale e ti sposta dentro) e modalità manuale
(pannello con bottone, nessuno spostamento forzato). ENTRAMBE SEMPRE
VISIBILI a tutti gli utenti — decisione già presa in fase di
progettazione: i problemi di disconnessione su spostamento forzato
in vocale riguardano sia PlayStation sia mobile, quindi non ha senso
nascondere una modalità in base alla piattaforma dichiarata
dall'utente (che comunque non sappiamo con certezza).

Il bottone della modalità manuale è un altro pannello "a vita
lunga": stessa esigenza di persistenza già affrontata in
cogs/tickets/tickets.py — vedi TicketPanelView per il precedente,
qui si applica lo stesso pattern (timeout=None, custom_id esplicito,
bot.add_view() in setup()).

SPEC.md §12.4 + §12.5: alla creazione del canale (automatica o
manuale) viene inviato un messaggio nella chat testuale del canale
vocale stesso (un VoiceChannel è Messageable) con la notifica "il tuo
canale è pronto" e, SE il server ha configurato almeno un ruolo
piattaforma, dei bottoni PC/Console/Mobile — vedi PlatformRoleView.
Restano SOLO informativi (nessun filtro di visibilità), per la stessa
ragione già registrata sopra sulle due modalità sempre visibili.
Anche questi bottoni sono persistenti.

Gestione del canale (/voice …): la rinomina rispetta il limite di
Discord di 2 ogni 10 minuti (core/channel_rename.py); /voice transfer
sposta anche i permessi del canale; all'avvio i canali rimasti vuoti
mentre il bot era spento vengono cancellati.
Funzioni coperte: SPEC §12, §22 (claim, permit, deny, bitrate, nascondi, invita,
stato, opzioni, aspetto del pannello, copia del generatore e altri generatori di
/gestione voice: catalogo #127; blocco salvato nel database, #144)

SPEC.md §12.8: il cap per categoria (/gestione voice cap) è sempre
troncato al limite hard di Discord di 50 canali per categoria — vedi
core/voice_temp_logic.py:effective_category_cap/is_category_full.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.channel_rename import (
    RenameRateLimited,
    rename_channel,
    rename_limit_message,
    rename_tracker,
)
from cogs.moderation._shared import actor_from_member
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.permissions import can_moderate
from core.repositories.blacklist_repo import blacklist_repo
from core.repositories.voice_temp_repo import voice_temp_repo
from core.role_safety import check_role_assignable
from core.voice_temp_logic import (
    MAX_MODELLO_NOME,
    MAX_PANNELLO_TESTO,
    MAX_PANNELLO_TITOLO,
    colore_da_testo,
    impostazioni_da_generatore,
    can_manage_voice_channel,
    errore_modello_nome,
    is_category_full,
    is_generator_join,
    is_old_enough_for_startup_cleanup,
    nome_da_modello,
    primo_numero_libero,
    should_delete_after_leave,
)
from core.premium import PremiumModule, registry
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.voice_temp")

MODULE_VOICE_TEMP = "voice_temp"

# Sotto-gruppo di /gestione con i comandi degli admin.
GESTIONE_VOICE = ("voice", "Vocali temporanei: generatore, pannello, limite, ruoli piattaforma")

CREATE_VOICE_CUSTOM_ID = "iyokai_voice_temp_create"

# Generatori in più oltre a quello principale (VOC-016).
GENERATORI_EXTRA_MAX = 5

# Il nome di un canale Discord va da 1 a 100 caratteri (LIM-3).
MAX_CHANNEL_NAME_LENGTH = 100

# I permessi che il proprietario ha sul suo canale. /voice transfer li
# sposta al nuovo proprietario.
OWNER_PERMISSIONS = {"manage_channels": True, "move_members": True, "mute_members": True}

MESSAGGIO_ERRORE_DISCORD = (
    "Non sono riuscito a farlo: controlla i miei permessi sul canale e riprova."
)

# SPEC.md §12.5: selezione piattaforma, SOLO informativa (nessun
# filtro di visibilità — decisione già presa in fase di progettazione,
# vedi il docstring del modulo). I custom_id sono fissi e la view è
# persistente (LIM-26): un canale vive ore, i bottoni devono funzionare
# anche dopo 5 minuti e dopo un riavvio del bot.
PLATFORM_CHOICES = (
    ("pc", "PC", "🖥️"),
    ("console", "Console", "🎮"),
    ("mobile", "Mobile", "📱"),
)


def _platform_roles(config) -> dict[str, int | None]:
    """Chiave della piattaforma -> id del ruolo configurato (None se manca)."""
    return {
        "pc": config.role_pc_id,
        "console": config.role_console_id,
        "mobile": config.role_mobile_id,
    }


class PlatformRoleView(BaseView):
    """
    Bottoni PC/Console/Mobile mostrati insieme alla notifica di
    creazione del canale (SPEC.md §12.4 + §12.5 insieme: la notifica
    esiste comunque, i bottoni compaiono solo se il server ha
    configurato almeno un ruolo piattaforma). Selezionare una
    piattaforma assegna QUEL ruolo e rimuove gli altri due — è un
    indicatore mutuamente esclusivo ("sto giocando da..."), non un
    filtro su cosa il membro può vedere o fare.

    View PERSISTENTE (timeout=None, custom_id fissi, bot.add_view() in
    setup()): i ruoli non stanno nella view ma si leggono dalla
    configurazione del server a ogni clic, così il bottone di un
    messaggio vecchio funziona anche dopo un riavvio. Con `config` la
    view mostra solo le piattaforme configurate (è quella che va nel
    messaggio); senza, le ha tutte e tre (è quella registrata
    all'avvio, che riceve i clic di ogni messaggio).
    """

    def __init__(self, config=None) -> None:
        super().__init__(timeout=None)
        for key, label, emoji in PLATFORM_CHOICES:
            if config is not None and _platform_roles(config).get(key) is None:
                continue
            self.add_item(self._make_button(key, label, emoji))

    def _make_button(self, key: str, label: str, emoji: str) -> discord.ui.Button:
        button = discord.ui.Button(
            label=label, emoji=emoji, style=discord.ButtonStyle.secondary,
            custom_id=f"iyokai_voice_temp_platform_{key}",
        )

        async def callback(interaction: discord.Interaction) -> None:
            if not isinstance(interaction.user, discord.Member):
                return
            guild = interaction.guild
            if guild is None:
                return

            roles_by_key = _platform_roles(await voice_temp_repo.get_config(guild.id))
            if roles_by_key[key] is None:
                await interaction.response.send_message(
                    "Questa piattaforma non è più configurata su questo server.",
                    ephemeral=True,
                )
                return

            ruolo_scelto = guild.get_role(roles_by_key[key])
            if ruolo_scelto is None:
                await interaction.response.send_message(
                    "Il ruolo configurato per questa piattaforma non esiste più.",
                    ephemeral=True,
                )
                return

            # SEC-4/SEC-17: assegnazione self-service, ricontrolla il
            # ruolo scelto — può aver preso permessi pericolosi dopo
            # /gestione voice piattaforme.
            motivo_rifiuto = check_role_assignable(guild, ruolo_scelto, guild.me, self_service=True)
            if motivo_rifiuto is not None:
                await interaction.response.send_message(motivo_rifiuto, ephemeral=True)
                return

            altri_ruoli_id = {
                rid for rid in roles_by_key.values() if rid is not None and rid != ruolo_scelto.id
            }
            da_rimuovere = [
                r for r in interaction.user.roles if r.id in altri_ruoli_id
            ]
            try:
                if da_rimuovere:
                    await interaction.user.remove_roles(*da_rimuovere, reason="Cambio piattaforma vocale temporaneo")
                if ruolo_scelto not in interaction.user.roles:
                    await interaction.user.add_roles(ruolo_scelto, reason="Selezione piattaforma vocale temporaneo")
            except (discord.Forbidden, discord.HTTPException):
                await interaction.response.send_message(
                    "Non ho i permessi per assegnare il ruolo piattaforma.",
                    ephemeral=True,
                )
                return

            await interaction.response.send_message(
                f"Piattaforma impostata: {ruolo_scelto.mention}.", ephemeral=True
            )

        button.callback = callback
        return button


async def _registra(guild: discord.Guild, testo: str, config=None) -> None:
    """VOC-018: una riga nel canale di registro dei vocali, se il server ne ha scelto uno."""
    if config is None:
        config = await voice_temp_repo.get_config(guild.id)
    if config.canale_registro_id is None:
        return
    canale = guild.get_channel(config.canale_registro_id)
    if not isinstance(canale, discord.TextChannel):
        return
    try:
        await canale.send(testo[:2000], allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        logger.warning("Registro dei vocali non scritto nel canale %s", canale.id)


# Un blocco per server: due canali creati insieme non prendono lo stesso
# numero (scelta del numero, creazione e registrazione in fila).
_blocchi_numero: dict[int, asyncio.Lock] = {}


async def _create_temp_channel(
    guild: discord.Guild,
    owner: discord.Member,
    category: discord.CategoryChannel,
    config,
    limite_utenti: int = 0,
) -> discord.VoiceChannel | None:
    """
    Crea il canale vocale temporaneo, lo registra nel repository, e
    lo restituisce. None se la creazione fallisce (permessi mancanti,
    categoria al cap configurato, o limite hard Discord di 50 canali)
    — il chiamante decide come comunicarlo, dato che i due punti di
    ingresso (evento vocale automatico, bottone manuale) rispondono
    in modo diverso.
    """
    if is_category_full(len(category.channels), config.category_cap):
        logger.info(
            "Categoria %s piena (cap effettivo raggiunto), vocale temporaneo per %s non creato",
            category.id,
            owner.id,
        )
        return None

    # VOC-015: il canale può nascere bloccato (lo apre il proprietario
    # con /voice unlock); il proprietario entra comunque.
    everyone = discord.PermissionOverwrite(connect=False) if config.nasce_bloccato else discord.PermissionOverwrite()
    proprietario = discord.PermissionOverwrite(**OWNER_PERMISSIONS)
    if config.nasce_bloccato:
        proprietario.update(connect=True)
    overwrites = {guild.default_role: everyone, owner: proprietario}
    extra: dict = {}
    generatore = guild.get_channel(config.generator_channel_id) if config.generator_channel_id else None
    if config.clona_generatore and isinstance(generatore, discord.VoiceChannel):
        # VOC-013: permessi, limite e qualità del generatore; il blocco e il proprietario
        # restano quelli di sopra.
        overwrites = {**generatore.overwrites, **overwrites}
        if guild.default_role in generatore.overwrites:
            # Il @everyone del generatore resta (un generatore privato dà vocali privati);
            # se nascono bloccati, in più «Connetti» negato.
            tutti = discord.PermissionOverwrite.from_pair(*generatore.overwrites[guild.default_role].pair())
            if config.nasce_bloccato:
                tutti.update(connect=False)
            overwrites[guild.default_role] = tutti
        extra = impostazioni_da_generatore(generatore.bitrate, generatore.user_limit, int(guild.bitrate_limit))
    if limite_utenti:
        extra["user_limit"] = limite_utenti
    async with _blocchi_numero.setdefault(guild.id, asyncio.Lock()):
        numero = primo_numero_libero(await voice_temp_repo.numeri_usati(guild.id))
        try:
            channel = await category.create_voice_channel(
                name=nome_da_modello(config.nome_modello, owner.display_name, numero),
                overwrites=overwrites,
                reason=f"Vocale temporaneo per {owner}",
                **extra,
            )
        except (discord.Forbidden, discord.HTTPException):
            logger.warning(
                "Impossibile creare il vocale temporaneo per %s nel server %s",
                owner.id,
                guild.id,
            )
            return None

        await voice_temp_repo.register_channel(channel.id, guild.id, owner.id, numero)
    if config.nasce_bloccato:
        # Prima del blocco «Connetti» era ereditato: unlock lo rimette così.
        await voice_temp_repo.segna_bloccato(channel.id, None)

    # SPEC.md §12.4: notifica personale alla creazione del canale —
    # richiesta esplicitamente perché la modalità automatica sposta
    # l'utente in totale silenzio. Un canale vocale è Messageable
    # (ha una sua chat testuale), quindi il messaggio va dritto lì.
    embed = discord.Embed(
        title="🔊 Canale vocale creato",
        description=f"{owner.mention}, il tuo canale **{channel.name}** è pronto.",
        color=discord.Color.blurple(),
    )
    view = PlatformRoleView(config)
    try:
        if view.children:
            await channel.send(embed=embed, view=view)
        else:
            await channel.send(embed=embed)
    except discord.HTTPException:
        logger.warning("Impossibile inviare la notifica di creazione nel canale %s", channel.id)
    # I clic li riceve la view registrata all'avvio (stessi custom_id):
    # questa, legata al singolo messaggio, si ferma subito, altrimenti
    # ne resterebbe una in memoria per ogni canale creato.
    view.stop()
    await _registra(guild, f"🔊 {owner.mention} ha creato {channel.mention}.", config)

    return channel


class CreateVoiceView(BaseView):
    """Persistente — stesso motivo di TicketPanelView (vedi cogs/tickets/tickets.py)."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Crea canale vocale",
        style=discord.ButtonStyle.primary,
        emoji="🔊",
        custom_id=CREATE_VOICE_CUSTOM_ID,
    )
    async def create_voice(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_VOICE_TEMP):
            await interaction.response.send_message(
                "I vocali temporanei non sono attivi su questo server.",
                ephemeral=True,
            )
            return

        config = await voice_temp_repo.get_config(guild.id)
        if config.category_id is None:
            await interaction.response.send_message(
                "Il sistema non è ancora configurato. Un amministratore "
                "deve usare /gestione voice setup.",
                ephemeral=True,
            )
            return

        category = guild.get_channel(config.category_id)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "La categoria configurata non esiste più. Un "
                "amministratore deve riconfigurarla.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        channel = await _create_temp_channel(guild, interaction.user, category, config)
        if channel is None:
            await interaction.followup.send(
                "Non sono riuscito a creare il canale (permessi mancanti "
                "o categoria piena).",
                ephemeral=True,
            )
            return

        # Modalità MANUALE: nessuno spostamento forzato, a differenza
        # della modalità automatica — è esattamente la differenza tra
        # le due modalità richiesta in fase di progettazione.
        await interaction.followup.send(
            f"Canale creato: {channel.mention}. Entra quando vuoi.",
            ephemeral=True,
        )


class VoiceTempCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ================================================================
    # Configurazione
    # ================================================================
    @comando_di_gruppo(
        "gestione",
        nome="setup",
        descrizione="Configura il canale generatore e la categoria dei vocali temporanei.",
        sottogruppo=GESTIONE_VOICE,
    )
    @app_commands.describe(
        generator="Il canale vocale che, se raggiunto, crea un vocale temporaneo",
        category="La categoria dove verranno creati i vocali temporanei",
    )
    async def voicetemp_setup(
        self,
        interaction: discord.Interaction,
        generator: discord.VoiceChannel,
        category: discord.CategoryChannel,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.",
                ephemeral=True,
            )
            return

        await voice_temp_repo.set_config(interaction.guild.id, generator.id, category.id)
        await interaction.response.send_message(
            f"Configurato: entrando in {generator.mention} verrà creato "
            f"un vocale temporaneo dentro **{category.name}**.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "gestione",
        nome="generatore",
        descrizione="Altri canali generatori con regole proprie.",
        sottogruppo=GESTIONE_VOICE,
    )
    @app_commands.describe(
        azione="Cosa fare",
        canale="Il generatore",
        categoria="Dove nascono i canali",
        nome="Modello del nome ({utente}, {numero})",
        limite="Limite di utenti (0 = nessuno)",
    )
    @app_commands.choices(
        azione=[
            app_commands.Choice(name="Aggiungi", value="aggiungi"),
            app_commands.Choice(name="Togli", value="rimuovi"),
            app_commands.Choice(name="Elenco", value="elenco"),
        ]
    )
    async def voicetemp_generatore(
        self,
        interaction: discord.Interaction,
        azione: str,
        canale: discord.VoiceChannel | None = None,
        categoria: discord.CategoryChannel | None = None,
        nome: app_commands.Range[str, 1, MAX_MODELLO_NOME] | None = None,
        limite: app_commands.Range[int, 0, 99] = 0,
    ) -> None:
        """#127 VOC-016."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        guild_id = interaction.guild.id
        if azione == "elenco":
            altri = await voice_temp_repo.lista_generatori(guild_id)
            righe = [
                f"<#{g.channel_id}> → <#{g.category_id}>"
                f" · nome: {discord.utils.escape_markdown(g.nome_modello or 'come il server')}"
                f" · limite: {g.limite_utenti or 'nessuno'}"
                for g in altri
            ]
            await interaction.response.send_message(
                "\n".join(righe) if righe else "Nessun generatore in più: c'è solo quello di /gestione voice setup.",
                ephemeral=True,
            )
            return
        if canale is None:
            await interaction.response.send_message("Scegli il canale generatore.", ephemeral=True)
            return
        if azione == "rimuovi":
            tolto = await voice_temp_repo.rimuovi_generatore(guild_id, canale.id)
            await interaction.response.send_message(
                "Generatore tolto." if tolto else "Quel canale non era un generatore in più.", ephemeral=True
            )
            return
        config = await voice_temp_repo.get_config(guild_id)
        if config.category_id is None:
            await interaction.response.send_message(
                "Configura prima generatore e categoria con /gestione voice setup.", ephemeral=True
            )
            return
        if categoria is None:
            await interaction.response.send_message("Scegli la categoria dei nuovi canali.", ephemeral=True)
            return
        if canale.id == config.generator_channel_id:
            await interaction.response.send_message(
                "Quello è già il generatore principale: cambialo con /gestione voice setup.", ephemeral=True
            )
            return
        if nome is not None and (errore := errore_modello_nome(nome)):
            await interaction.response.send_message(errore, ephemeral=True)
            return
        if not await voice_temp_repo.aggiungi_generatore(
            guild_id, canale.id, categoria.id, nome, limite, GENERATORI_EXTRA_MAX
        ):
            await interaction.response.send_message(
                f"Hai già {GENERATORI_EXTRA_MAX} generatori in più: toglierne uno prima.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"Fatto: entrando in {canale.mention} nasce un vocale in **{categoria.name}**.", ephemeral=True
        )

    @comando_di_gruppo(
        "gestione",
        nome="panel",
        descrizione="Pubblica il pannello per la creazione manuale di un vocale.",
        sottogruppo=GESTIONE_VOICE,
    )
    async def voicetemp_panel(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        config = await voice_temp_repo.get_config(interaction.guild.id)
        embed = discord.Embed(
            title=config.pannello_titolo or "🔊 Vocali temporanei",
            description=config.pannello_testo
            or (
                "Premi il bottone per crearti un canale vocale personale "
                "senza essere spostato automaticamente."
            ),
            color=(
                discord.Color(config.pannello_colore)
                if config.pannello_colore is not None
                else discord.Color.blurple()
            ),
        )
        await interaction.response.send_message(embed=embed, view=CreateVoiceView())

    @comando_di_gruppo(
        "gestione",
        nome="cap",
        descrizione="Imposta il numero massimo di vocali temporanei per categoria.",
        sottogruppo=GESTIONE_VOICE,
    )
    @app_commands.describe(
        cap="Canali massimi nella categoria (max 50, limite di Discord). Vuoto: nessun limite."
    )
    async def voicetemp_cap(
        self,
        interaction: discord.Interaction,
        cap: app_commands.Range[int, 1, 50] | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        config = await voice_temp_repo.get_config(interaction.guild.id)
        if config.category_id is None:
            await interaction.response.send_message(
                "Configura prima generatore e categoria con /gestione voice setup.",
                ephemeral=True,
            )
            return

        await voice_temp_repo.set_category_cap(interaction.guild.id, cap)
        testo = f"massimo **{cap}** canali" if cap is not None else "nessun limite (oltre a quello di Discord, 50)"
        await interaction.response.send_message(
            f"Cap per categoria impostato: {testo}.", ephemeral=True
        )

    @comando_di_gruppo(
        "gestione",
        nome="piattaforme",
        descrizione="Configura i ruoli informativi PC/Console/Mobile per i vocali temporanei.",
        sottogruppo=GESTIONE_VOICE,
    )
    @app_commands.describe(
        pc="Ruolo per chi gioca da PC (facoltativo)",
        console="Ruolo per chi gioca da Console (facoltativo)",
        mobile="Ruolo per chi gioca da Mobile (facoltativo)",
    )
    async def voicetemp_platform_setup(
        self,
        interaction: discord.Interaction,
        pc: discord.Role | None = None,
        console: discord.Role | None = None,
        mobile: discord.Role | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        config = await voice_temp_repo.get_config(interaction.guild.id)
        if config.category_id is None:
            await interaction.response.send_message(
                "Configura prima generatore e categoria con /gestione voice setup.",
                ephemeral=True,
            )
            return

        if not isinstance(interaction.user, discord.Member):
            return

        for ruolo in (pc, console, mobile):
            if ruolo is None:
                continue
            motivo_rifiuto = check_role_assignable(
                interaction.guild, ruolo, interaction.user, self_service=True
            )
            if motivo_rifiuto is not None:
                await interaction.response.send_message(motivo_rifiuto, ephemeral=True)
                return

        await voice_temp_repo.set_platform_roles(
            interaction.guild.id,
            role_pc_id=pc.id if pc else None,
            role_console_id=console.id if console else None,
            role_mobile_id=mobile.id if mobile else None,
        )
        await interaction.response.send_message(
            "Ruoli piattaforma aggiornati. Sono puramente informativi: non "
            "filtrano la visibilità del canale.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "gestione",
        nome="opzioni",
        descrizione="Nome dei nuovi canali, blocco, registro, copia, pannello.",
        sottogruppo=GESTIONE_VOICE,
    )
    @app_commands.describe(
        nome="Modello del nome: {utente} e {numero} (es. Stanza {numero}). Vuoto: com'è ora",
        chiusi="I nuovi canali nascono bloccati: li apre il proprietario con /voice unlock",
        registro="Canale dove scrivere le azioni sui vocali (creazione, blocco, espulsioni…)",
        predefiniti="Torna ai valori di partenza",
        copia_generatore="Copia permessi, limite e qualità del generatore",
        pannello_titolo="Titolo del pannello",
        pannello_testo="Testo del pannello",
        pannello_colore="Colore esadecimale (5865F2)",
    )
    async def voicetemp_opzioni(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, MAX_MODELLO_NOME] | None = None,
        chiusi: bool | None = None,
        registro: discord.TextChannel | None = None,
        predefiniti: bool = False,
        copia_generatore: bool | None = None,
        pannello_titolo: app_commands.Range[str, 1, MAX_PANNELLO_TITOLO] | None = None,
        pannello_testo: app_commands.Range[str, 1, MAX_PANNELLO_TESTO] | None = None,
        pannello_colore: app_commands.Range[str, 3, 7] | None = None,
    ) -> None:
        """#127 VOC-010, 011, 012, 013, 015, 018."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        config = await voice_temp_repo.get_config(interaction.guild.id)
        if config.category_id is None:
            await interaction.response.send_message(
                "Configura prima generatore e categoria con /gestione voice setup.",
                ephemeral=True,
            )
            return
        if nome is not None and (errore := errore_modello_nome(nome)):
            await interaction.response.send_message(errore, ephemeral=True)
            return
        colore = config.pannello_colore
        if pannello_colore is not None:
            colore = colore_da_testo(pannello_colore)
            if colore is None:
                await interaction.response.send_message(
                    "Il colore va scritto in esadecimale, per esempio 5865F2.", ephemeral=True
                )
                return
        modello = None if predefiniti else (nome or config.nome_modello)
        canale_registro = None if predefiniti else (registro.id if registro else config.canale_registro_id)
        bloccati = config.nasce_bloccato if chiusi is None else chiusi
        await voice_temp_repo.set_opzioni(interaction.guild.id, modello, bloccati, canale_registro)
        clona = config.clona_generatore if copia_generatore is None else copia_generatore
        titolo = pannello_titolo or config.pannello_titolo
        testo = pannello_testo or config.pannello_testo
        if predefiniti:
            clona, titolo, testo, colore = False, None, None, None
        await voice_temp_repo.set_aspetto(interaction.guild.id, titolo, testo, colore, clona)
        await interaction.response.send_message(
            f"Nome dei nuovi canali: **{discord.utils.escape_markdown(modello or 'Canale di {utente}')}**\n"
            f"Nascono bloccati: **{'sì' if bloccati else 'no'}**\n"
            f"Copiano il generatore: **{'sì' if clona else 'no'}**\n"
            f"Registro: {f'<#{canale_registro}>' if canale_registro else 'nessuno'}\n"
            f"Pannello: {'personalizzato' if (titolo or testo or colore is not None) else 'di serie'}",
            ephemeral=True,
        )

    # ================================================================
    # Gestione del proprio canale
    # ================================================================
    async def _get_managed_channel_or_reply(
        self, interaction: discord.Interaction
    ) -> discord.VoiceChannel | None:
        if not isinstance(interaction.user, discord.Member) or interaction.user.voice is None:
            await interaction.response.send_message(
                "Devi essere connesso al tuo canale vocale temporaneo "
                "per usare questo comando.",
                ephemeral=True,
            )
            return None

        channel = interaction.user.voice.channel
        owner_id = await voice_temp_repo.get_owner(channel.id)
        if owner_id is None:
            await interaction.response.send_message(
                "Questo non è un canale vocale temporaneo gestito da iYokai.",
                ephemeral=True,
            )
            return None

        actor_has_manage_channels = interaction.user.guild_permissions.manage_channels
        if not can_manage_voice_channel(interaction.user.id, owner_id, actor_has_manage_channels):
            await interaction.response.send_message(
                "Solo il proprietario del canale (o lo staff) può gestirlo.",
                ephemeral=True,
            )
            return None

        return channel

    @comando_di_gruppo("voice", nome="rename", descrizione="Rinomina il tuo canale vocale.")
    @app_commands.describe(name="Il nuovo nome del canale")
    async def rename(
        self,
        interaction: discord.Interaction,
        name: app_commands.Range[str, 1, MAX_CHANNEL_NAME_LENGTH],
    ) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return

        # Discord permette 2 rinomine ogni 10 minuti per canale (LIM-3):
        # alla terza si risponde subito, senza restare in attesa.
        attesa = rename_tracker.seconds_until_allowed(channel.id)
        if attesa > 0:
            await interaction.response.send_message(
                rename_limit_message(attesa), ephemeral=True
            )
            return

        await interaction.response.defer()
        try:
            await rename_channel(
                channel, name, reason=f"Vocale rinominato da {interaction.user}"
            )
        except RenameRateLimited as limite:
            await interaction.followup.send(
                rename_limit_message(limite.retry_after), ephemeral=True
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Non sono riuscito a rinominare il canale: controlla i miei "
                "permessi e che il nome sia ammesso da Discord.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Canale rinominato in **{name}**.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo("voice", nome="limit", descrizione="Imposta il limite di utenti del canale.")
    @app_commands.describe(limit="Numero massimo di utenti (0 per nessun limite)")
    async def limit(
        self, interaction: discord.Interaction, limit: app_commands.Range[int, 0, 99]
    ) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        try:
            await channel.edit(user_limit=limit)
        except discord.HTTPException:
            await interaction.response.send_message(MESSAGGIO_ERRORE_DISCORD, ephemeral=True)
            return
        testo = "nessun limite" if limit == 0 else f"{limit} utenti"
        await interaction.response.send_message(f"Limite impostato: {testo}.")

    @comando_di_gruppo("voice", nome="lock", descrizione="Blocca il canale (nessun nuovo ingresso).")
    async def lock(self, interaction: discord.Interaction) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        try:
            # Si cambia solo "Connetti": gli altri permessi di @everyone
            # su questo canale restano com'erano.
            overwrite = channel.overwrites_for(interaction.guild.default_role)
            # Il valore di prima va nel database (solo al primo lock):
            # unlock lo ripristina anche dopo un riavvio del bot.
            await voice_temp_repo.segna_bloccato(channel.id, overwrite.connect)
            overwrite.update(connect=False)
            await channel.set_permissions(
                interaction.guild.default_role, overwrite=overwrite
            )
        except discord.HTTPException:
            await interaction.response.send_message(MESSAGGIO_ERRORE_DISCORD, ephemeral=True)
            return
        await interaction.response.send_message("Canale bloccato.")
        await _registra(interaction.guild, f"🔒 {interaction.user.mention} ha bloccato {channel.mention}.")

    @comando_di_gruppo("voice", nome="unlock", descrizione="Sblocca il canale.")
    async def unlock(self, interaction: discord.Interaction) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        try:
            overwrite = channel.overwrites_for(interaction.guild.default_role)
            era_bloccato, prima = await voice_temp_repo.togli_blocco(channel.id)
            overwrite.update(connect=prima)
            await channel.set_permissions(
                interaction.guild.default_role,
                overwrite=None if overwrite.is_empty() else overwrite,
            )
        except discord.HTTPException:
            # Il canale resta com'era: se era bloccato si rimette il
            # ricordo di prima; se non lo era, non lo si segna bloccato
            # (un lock dopo deve salvare il valore vero).
            if era_bloccato:
                await voice_temp_repo.segna_bloccato(channel.id, prima)
            await interaction.response.send_message(MESSAGGIO_ERRORE_DISCORD, ephemeral=True)
            return
        await interaction.response.send_message("Canale sbloccato.")
        await _registra(interaction.guild, f"🔓 {interaction.user.mention} ha sbloccato {channel.mention}.")

    @staticmethod
    def _puo_espellere(
        interaction: discord.Interaction, member: discord.Member
    ) -> tuple[bool, str]:
        """
        Gerarchia dei ruoli (stessa regola della moderazione) più una
        protezione per amministratori e moderatori: chi non è staff non
        può espellerli dal proprio canale, qualunque sia il suo ruolo.
        """
        guild = interaction.guild
        autore = interaction.user
        permesso, motivo = can_moderate(
            actor_from_member(autore),
            actor_from_member(member),
            bot_top_role_position=guild.me.top_role.position,
        )
        if not permesso:
            return False, motivo
        e_staff = autore.guild_permissions.manage_channels
        perm = member.guild_permissions
        if not e_staff and (
            perm.administrator or perm.moderate_members or perm.kick_members or perm.ban_members
        ):
            return False, "Non puoi espellere un amministratore o un moderatore dal tuo canale."
        return True, ""

    @comando_di_gruppo("voice", nome="kick", descrizione="Espelli un utente dal tuo canale.")
    @app_commands.describe(member="L'utente da espellere dal canale")
    async def kick(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        if member.voice is None or member.voice.channel is None or member.voice.channel.id != channel.id:
            await interaction.response.send_message(
                f"{member.mention} non è nel canale: non c'è nessuno da espellere.",
                ephemeral=True,
            )
            return
        permesso, motivo = self._puo_espellere(interaction, member)
        if not permesso:
            await interaction.response.send_message(motivo, ephemeral=True)
            return
        try:
            await member.move_to(None, reason="Espulso dal proprietario del canale")
        except discord.HTTPException:
            await interaction.response.send_message(MESSAGGIO_ERRORE_DISCORD, ephemeral=True)
            return
        await interaction.response.send_message(f"{member.mention} espulso dal canale.")
        await _registra(
            interaction.guild, f"👢 {interaction.user.mention} ha espulso {member.mention} da {channel.mention}."
        )

    async def _assegna_proprieta(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
        member: discord.Member,
        vecchio_id: int | None,
    ) -> bool:
        """Passa la proprietà a `member`. False (dopo aver risposto) se Discord rifiuta."""
        # Prima il database, in modo atomico (due richieste insieme: vince una sola),
        # poi i permessi su Discord; se Discord rifiuta la proprietà torna com'era.
        if not await voice_temp_repo.cambia_proprietario(channel.id, vecchio_id, member.id):
            await interaction.response.send_message(
                "Il canale ha già cambiato proprietario: riprova.", ephemeral=True
            )
            return False
        try:
            await channel.set_permissions(
                member, reason="Nuovo proprietario del vocale temporaneo", **OWNER_PERMISSIONS
            )
        except discord.HTTPException:
            await voice_temp_repo.cambia_proprietario(channel.id, member.id, vecchio_id)
            await interaction.response.send_message(MESSAGGIO_ERRORE_DISCORD, ephemeral=True)
            return False

        # Al vecchio proprietario i permessi vanno tolti. Se è uscito
        # dal server non c'è più niente da togliere.
        vecchio = interaction.guild.get_member(vecchio_id)
        if vecchio is not None:
            try:
                await channel.set_permissions(
                    vecchio, overwrite=None, reason="Non è più il proprietario del vocale"
                )
            except discord.HTTPException:
                logger.warning(
                    "Permessi del vecchio proprietario %s non tolti dal canale %s",
                    vecchio_id,
                    channel.id,
                )
        return True

    @comando_di_gruppo("voice", nome="claim", descrizione="Prendi il canale se il proprietario non c'è più.")
    async def claim(self, interaction: discord.Interaction) -> None:
        """VOC-001: il proprietario è uscito ma il canale resta (altri dentro): si può rilevare."""
        if not isinstance(interaction.user, discord.Member) or interaction.user.voice is None:
            await interaction.response.send_message(
                "Devi essere connesso a un canale vocale temporaneo per usare questo comando.",
                ephemeral=True,
            )
            return
        channel = interaction.user.voice.channel
        vecchio_id = await voice_temp_repo.get_owner(channel.id)
        if vecchio_id is None:
            await interaction.response.send_message(
                "Questo non è un canale vocale temporaneo gestito da iYokai.", ephemeral=True
            )
            return
        if vecchio_id == interaction.user.id:
            await interaction.response.send_message("Sei già il proprietario del canale.", ephemeral=True)
            return
        if any(m.id == vecchio_id for m in channel.members):
            await interaction.response.send_message(
                "Il proprietario è ancora nel canale: chiedi a lui di usare `/voice transfer`.",
                ephemeral=True,
            )
            return
        if not await self._assegna_proprieta(interaction, channel, interaction.user, vecchio_id):
            return
        await interaction.response.send_message(
            f"{interaction.user.mention} è il nuovo proprietario del canale.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await _registra(interaction.guild, f"👑 {interaction.user.mention} ha preso {channel.mention}.")

    @comando_di_gruppo("voice", nome="permit", descrizione="Permetti a un utente di entrare anche se il canale è bloccato.")
    @app_commands.describe(member="L'utente da ammettere")
    async def permit(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        try:
            overwrite = channel.overwrites_for(member)
            overwrite.update(connect=True, view_channel=True)
            await channel.set_permissions(member, overwrite=overwrite, reason="Ammesso dal proprietario del vocale")
        except discord.HTTPException:
            await interaction.response.send_message(MESSAGGIO_ERRORE_DISCORD, ephemeral=True)
            return
        await interaction.response.send_message(
            f"{member.mention} può entrare nel canale.", allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo("voice", nome="deny", descrizione="Vieta a un utente di entrare nel canale.")
    @app_commands.describe(member="L'utente da escludere")
    async def deny(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        if member.id == interaction.user.id or member.id == await voice_temp_repo.get_owner(channel.id):
            await interaction.response.send_message(
                "Non puoi vietare l'accesso al proprietario del canale.", ephemeral=True
            )
            return
        permesso, motivo = self._puo_espellere(interaction, member)
        if not permesso:
            await interaction.response.send_message(motivo, ephemeral=True)
            return
        try:
            overwrite = channel.overwrites_for(member)
            overwrite.update(connect=False)
            await channel.set_permissions(member, overwrite=overwrite, reason="Escluso dal proprietario del vocale")
            if member.voice is not None and member.voice.channel is not None and member.voice.channel.id == channel.id:
                await member.move_to(None, reason="Escluso dal proprietario del canale")
        except discord.HTTPException:
            await interaction.response.send_message(MESSAGGIO_ERRORE_DISCORD, ephemeral=True)
            return
        await interaction.response.send_message(
            f"{member.mention} non può più entrare nel canale.", allowed_mentions=discord.AllowedMentions.none()
        )
        await _registra(
            interaction.guild, f"⛔ {interaction.user.mention} ha escluso {member.mention} da {channel.mention}."
        )

    @comando_di_gruppo("voice", nome="bitrate", descrizione="Imposta la qualità audio del canale (kbps).")
    @app_commands.describe(kbps="Qualità in kbps (8-384, dipende dal livello del server)")
    async def bitrate(
        self, interaction: discord.Interaction, kbps: app_commands.Range[int, 8, 384]
    ) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        massimo = interaction.guild.bitrate_limit // 1000
        if kbps > massimo:
            await interaction.response.send_message(
                f"Questo server arriva al massimo a {int(massimo)} kbps.", ephemeral=True
            )
            return
        try:
            await channel.edit(bitrate=kbps * 1000)
        except discord.HTTPException:
            await interaction.response.send_message(MESSAGGIO_ERRORE_DISCORD, ephemeral=True)
            return
        await interaction.response.send_message(f"Qualità audio impostata a {kbps} kbps.")

    @comando_di_gruppo("voice", nome="nascondi", descrizione="Nascondi o mostra il canale a chi non è dentro.")
    @app_commands.describe(nascosto="Sì per nasconderlo, no per mostrarlo di nuovo")
    async def nascondi(self, interaction: discord.Interaction, nascosto: bool) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        await interaction.response.defer()  # un set_permissions per ogni presente: più di 3 secondi
        try:
            if nascosto:
                # Chi deve continuare a vedere il canale riceve un permesso esplicito PRIMA
                # che @everyone lo perda: proprietario, chi è dentro e il bot (che deve poterlo eliminare).
                proprietario = interaction.guild.get_member(await voice_temp_repo.get_owner(channel.id) or 0)
                for chi in {m.id: m for m in [*channel.members, proprietario, interaction.guild.me] if m}.values():
                    ow = channel.overwrites_for(chi)
                    ow.update(view_channel=True, connect=True)
                    await channel.set_permissions(chi, overwrite=ow, reason="Vocale nascosto")
            overwrite = channel.overwrites_for(interaction.guild.default_role)
            overwrite.update(view_channel=False if nascosto else None)
            await channel.set_permissions(
                interaction.guild.default_role,
                overwrite=None if overwrite.is_empty() else overwrite,
            )
        except discord.HTTPException:
            await interaction.followup.send(MESSAGGIO_ERRORE_DISCORD, ephemeral=True)
            return
        await interaction.followup.send("Canale nascosto." if nascosto else "Canale di nuovo visibile.")

    @comando_di_gruppo("voice", nome="invita", descrizione="Manda a un utente un invito al tuo canale.")
    @app_commands.describe(member="L'utente da invitare (può entrare anche se il canale è bloccato)")
    async def invita(self, interaction: discord.Interaction, member: discord.Member) -> None:
        """VOC-007: invito monouso di un giorno, in DM; ammette anche l'utente come /voice permit."""
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        if member.bot:
            await interaction.response.send_message("Non puoi invitare un bot.", ephemeral=True)
            return
        # L'invito vale per il server: il bot lo crea solo per chi potrebbe
        # crearlo da sé, altrimenti aggirerebbe il permesso «Crea invito».
        if not channel.permissions_for(interaction.user).create_instant_invite:
            await interaction.response.send_message(
                "Non hai il permesso di creare inviti su questo canale: usa /voice permit.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)  # permesso, invito e DM: tre chiamate
        try:
            overwrite = channel.overwrites_for(member)
            overwrite.update(connect=True, view_channel=True)
            await channel.set_permissions(member, overwrite=overwrite, reason="Invitato dal proprietario del vocale")
            invito = await channel.create_invite(
                max_age=86_400, max_uses=1, unique=True, reason="Invito al vocale temporaneo"
            )
        except discord.HTTPException:
            await interaction.followup.send(MESSAGGIO_ERRORE_DISCORD, ephemeral=True)
            return
        try:
            await member.send(
                f"{interaction.user.display_name} ti invita nel canale vocale "
                f"**{channel.name}** di **{interaction.guild.name}**: {invito.url}"[:2000]
            )
        except discord.HTTPException:
            await interaction.followup.send(
                f"{member.mention} non riceve DM: mandagli tu questo invito (vale un giorno, "
                f"un solo uso): {invito.url}",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        await interaction.followup.send(
            f"Invito mandato in DM a {member.mention}.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo("voice", nome="stato", descrizione="Scrivi cosa state facendo nel canale (vuoto: toglie).")
    @app_commands.describe(testo="Lo stato del canale, fino a 500 caratteri")
    async def stato(
        self,
        interaction: discord.Interaction,
        testo: app_commands.Range[str, 1, 500] | None = None,
    ) -> None:
        """VOC-008: lo stato del canale vocale di Discord (sotto il nome)."""
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        try:
            await channel.edit(status=testo)
        except discord.HTTPException:
            await interaction.response.send_message(
                "Non sono riuscito a cambiare lo stato: mi serve il permesso "
                "«Impostare lo stato del canale vocale».",
                ephemeral=True,
            )
            return
        await interaction.response.send_message("Stato aggiornato." if testo else "Stato tolto.", ephemeral=True)

    @comando_di_gruppo("voice", nome="transfer", descrizione="Trasferisci la proprietà del canale.")
    @app_commands.describe(member="Il nuovo proprietario del canale")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = await self._get_managed_channel_or_reply(interaction)
        if channel is None:
            return
        if member.bot:
            await interaction.response.send_message(
                "Non puoi trasferire il canale a un bot.", ephemeral=True
            )
            return
        if member.voice is None or member.voice.channel is None or member.voice.channel.id != channel.id:
            await interaction.response.send_message(
                f"{member.mention} non è nel canale: puoi trasferirlo solo "
                f"a chi è connesso qui.",
                ephemeral=True,
            )
            return
        vecchio_id = await voice_temp_repo.get_owner(channel.id)
        if member.id == vecchio_id:
            await interaction.response.send_message(
                f"{member.mention} è già il proprietario del canale.", ephemeral=True
            )
            return

        if not await self._assegna_proprieta(interaction, channel, member, vecchio_id):
            return

        await interaction.response.send_message(
            f"Proprietà del canale trasferita a {member.mention}."
        )
        await _registra(
            interaction.guild,
            f"👑 {interaction.user.mention} ha passato {channel.mention} a {member.mention}.",
        )

    # ================================================================
    # Pulizia all'avvio dei canali rimasti orfani
    # ================================================================
    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """
        Un canale temporaneo si elimina quando esce l'ultima persona.
        Se succede mentre il bot è spento l'evento va perso e il canale
        resta per sempre: qui, a ogni avvio (e a ogni riconnessione),
        si cancellano i canali registrati rimasti vuoti e si tolgono
        dal registro quelli che non esistono più.
        """
        for tracked in await voice_temp_repo.list_channels():
            if not is_old_enough_for_startup_cleanup(tracked.age_seconds):
                continue
            guild = self.bot.get_guild(tracked.guild_id)
            if guild is None:
                # Server non raggiungibile adesso (o bot uscito): non
                # si decide niente, si riprova al prossimo avvio.
                continue
            try:
                await self._cleanup_tracked_channel(guild, tracked.channel_id)
            except Exception:
                logger.exception(
                    "Pulizia all'avvio non riuscita per il vocale temporaneo %s",
                    tracked.channel_id,
                )

    async def _cleanup_tracked_channel(self, guild: discord.Guild, channel_id: int) -> None:
        channel = guild.get_channel(channel_id)
        if channel is None:
            await voice_temp_repo.unregister_channel(channel_id)
            return
        if channel.members:
            return
        try:
            await channel.delete(reason="Vocale temporaneo rimasto vuoto (pulizia all'avvio)")
        except discord.NotFound:
            pass  # già cancellato: resta solo da toglierlo dal registro
        except discord.HTTPException:
            logger.warning(
                "Vocale temporaneo vuoto %s non cancellato: riprovo al prossimo avvio.",
                channel_id,
            )
            return
        await voice_temp_repo.unregister_channel(channel_id)

    @staticmethod
    async def _sposta(member: discord.Member, channel: discord.VoiceChannel) -> None:
        try:
            await member.move_to(channel, reason="Vocale temporaneo automatico")
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Canale temporaneo creato ma impossibile spostare %s", member.id)

    # ================================================================
    # Eventi vocali: creazione automatica + eliminazione a canale vuoto
    # ================================================================
    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        before_channel_id = before.channel.id if before.channel else None
        after_channel_id = after.channel.id if after.channel else None

        if before_channel_id == after_channel_id:
            return  # non è un cambio di canale (es. solo mute/deafen)

        guild = member.guild

        # --- Modalità automatica: ingresso nel canale generatore ---
        if not await db.is_module_active_for_guild(guild.id, MODULE_VOICE_TEMP):
            pass  # non blocchiamo qui: il cleanup sotto deve comunque
            # girare anche se il modulo viene disattivato con canali
            # temporanei ancora aperti, altrimenti resterebbero orfani
        else:
            config = await voice_temp_repo.get_config(guild.id)
            # SEC-21: chi è in blacklist non ottiene un vocale
            # temporaneo (il cleanup più sotto gira comunque).
            if is_generator_join(
                after_channel_id, config.generator_channel_id
            ) and not await blacklist_repo.is_user_blacklisted(member.id):
                category = guild.get_channel(config.category_id) if config.category_id else None
                if isinstance(category, discord.CategoryChannel):
                    channel = await _create_temp_channel(guild, member, category, config)
                    if channel is not None:
                        await self._sposta(member, channel)
            elif after_channel_id is not None and not await blacklist_repo.is_user_blacklisted(member.id):
                # VOC-016: un generatore in più, con le sue regole.
                altro = await voice_temp_repo.get_generatore(guild.id, after_channel_id)
                category = guild.get_channel(altro.category_id) if altro else None
                if altro is not None and isinstance(category, discord.CategoryChannel):
                    regole = dataclasses.replace(
                        config,
                        generator_channel_id=altro.channel_id,
                        nome_modello=altro.nome_modello or config.nome_modello,
                    )
                    channel = await _create_temp_channel(guild, member, category, regole, altro.limite_utenti)
                    if channel is not None:
                        await self._sposta(member, channel)

        # --- Cleanup: il canale lasciato è un temporaneo tracciato ed è vuoto? ---
        if before_channel_id is not None:
            owner_id = await voice_temp_repo.get_owner(before_channel_id)
            remaining = len(before.channel.members) if before.channel else 0
            if should_delete_after_leave(before_channel_id, owner_id is not None, remaining):
                try:
                    await before.channel.delete(reason="Vocale temporaneo rimasto vuoto")
                except discord.NotFound:
                    pass  # già cancellato: resta solo da toglierlo dal registro
                except discord.HTTPException:
                    # Resta registrato: lo ritrova la pulizia all'avvio.
                    logger.warning(
                        "Vocale temporaneo vuoto %s non cancellato.", before_channel_id
                    )
                    return
                await voice_temp_repo.unregister_channel(before_channel_id)
                await _registra(guild, f"🗑️ Vocale **{before.channel.name}** eliminato: era vuoto.")


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_VOICE_TEMP,
            display_name="Vocali temporanei",
            category="voice",
            description="Creazione automatica e manuale di canali vocali personali.",
            premium_capable=False,
        )
    )
    await bot.add_cog(VoiceTempCog(bot))
    bot.add_view(CreateVoiceView())
    # Senza configurazione: tutte e tre le piattaforme, per ricevere i
    # clic sui bottoni dei messaggi già mandati (vedi PlatformRoleView).
    bot.add_view(PlatformRoleView())

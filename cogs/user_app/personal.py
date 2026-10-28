"""
cogs/user_app/personal.py
=========================
Comandi di iYokai App (NF-36), installabile dall'utente e usabile in ogni
server, in DM e nei gruppi: `/promemoria crea|elenco|annulla` (consegna in
DM), `/profilo`, e nel menu «App» del tasto destro «Profilo» (su un utente)
e «Testo pulito» (su un messaggio). Ogni comando risponde una volta sola,
in privato: niente risposte successive (dove l'app non è nel server Discord
ne ammette al massimo 5). Si carica solo sul client dell'app
(core/user_app_bot.py): sul bot principale `setup` non fa nulla.
Funzioni coperte: SPEC §B, §B.3 (NF-36)
"""

from __future__ import annotations

import io
import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.duration_logic import format_duration, parse_duration
from core.i18n import lingua_interazione, t, testo_per
from core.repositories.guild_clan_repo import guild_clan_repo
from core.repositories.leveling_repo import leveling_repo
from core.safe_image import run_image_task
from core.scheduler import scheduler
from core.user_app_bot import e_istanza_app
from core.user_app_impostazioni import impostazioni_di, risposta_privata
from core.user_app_logic import (
    AZIONE_PROMEMORIA,
    MAX_PROMEMORIA,
    errore_durata,
    programma_promemoria,
    testo_pulito,
)
from core.user_app_profilo import ProfiloGlobale, dati_rank_card, profilo_globale, testo_medaglie
from core.rank_card_image import render_profile_card

logger = logging.getLogger("iyokai.user_app")

INSTALLAZIONE = app_commands.AppInstallationType(guild=False, user=True)
OVUNQUE = app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True)


def _embed_profilo(utente: discord.User, lingua: str = "it", livello: tuple[int, int] | None = None,
                   clan: str | None = None, globale: ProfiloGlobale | None = None) -> discord.Embed:
    """`livello` = (livello, XP totali) in questo server; `clan` = nome e tag del clan in questo server;
    `globale` = i dati di tutti i server (solo per sé o per chi ha acceso il profilo pubblico)."""
    embed = discord.Embed(title=utente.display_name[:256], color=utente.accent_color or discord.Color.blurple())
    embed.add_field(name=t("app_profilo_nome", lingua), value=utente.name[:1024])
    embed.add_field(name=t("app_profilo_id", lingua), value=str(utente.id))
    embed.add_field(name=t("app_profilo_creato", lingua), value=discord.utils.format_dt(utente.created_at, "R"))
    if livello is not None:
        embed.add_field(name=t("app_profilo_livello", lingua), value=f"{livello[0]} · {livello[1]:,} XP".replace(",", "."))
    if clan:
        embed.add_field(name=t("app_profilo_clan", lingua), value=clan[:1024])
    if globale is not None:
        embed.add_field(
            name=t("app_profilo_livello_globale", lingua),
            value=f"{globale.livello} · {globale.xp_totale:,} XP · {t('app_profilo_server', lingua, server=globale.server)}".replace(",", "."),
            inline=False,
        )
        if globale.clan:
            embed.add_field(name=t("app_profilo_clan_globale", lingua), value="\n".join(globale.clan)[:1024], inline=False)
        medaglie = testo_medaglie(globale.medaglie)
        if medaglie:
            embed.add_field(name=t("app_profilo_medaglie", lingua), value=medaglie[:1024], inline=False)
    embed.set_thumbnail(url=utente.display_avatar.url)
    if utente.banner is not None:
        embed.set_image(url=utente.banner.url)
    if utente.bot:
        embed.set_footer(text=t("app_profilo_bot", lingua))
    return embed


async def _livello_e_clan(guild_id: int | None, user_id: int) -> tuple[tuple[int, int] | None, str | None]:
    """Livello e clan di una persona nel server dove si usa il comando (niente in DM)."""
    if not guild_id:
        return None, None
    try:
        totali = await leveling_repo.get_totals(guild_id, user_id)
        clan = await guild_clan_repo.get_member_clan_in_guild(guild_id, user_id)
    except Exception:  # noqa: BLE001 - dati in più: il profilo si mostra lo stesso
        logger.warning("Livello e clan non letti per il profilo.", exc_info=True)
        return None, None
    livello = (totali.level, totali.xp_total) if totali.xp_total > 0 else None
    return livello, (f"[{clan.tag}] {clan.name}" if clan else None)


async def _lingua_di(user_id: int) -> str:
    """La lingua personale scelta, per i DM (nessuna interazione in corso); senza scelta, italiano."""
    from core.i18n import lingua_risposta

    return await lingua_risposta(None, user_id)


class PersonaleCog(commands.Cog):
    promemoria = app_commands.Group(
        name="promemoria",
        description="I tuoi promemoria, in ogni server e in DM.",
        allowed_installs=INSTALLAZIONE,
        allowed_contexts=OVUNQUE,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._menu = [
            app_commands.ContextMenu(
                name="Profilo", callback=self.menu_profilo, allowed_installs=INSTALLAZIONE, allowed_contexts=OVUNQUE
            ),
            app_commands.ContextMenu(
                name="Testo pulito", callback=self.menu_testo_pulito, allowed_installs=INSTALLAZIONE,
                allowed_contexts=OVUNQUE,
            ),
        ]
        for menu in self._menu:
            bot.tree.add_command(menu)

    async def cog_unload(self) -> None:
        for menu in self._menu:
            self.bot.tree.remove_command(menu.name, type=menu.type)

    # ---------------------------------------------------------------- consegna
    async def consegna(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Handler dello scheduler: DM dall'app, se non va dal bot principale. Se nessuno dei due può, resta nel log."""
        testo = t("app_promemoria_consegna", await _lingua_di(user_id), testo=payload.get("message", "…"))[:2000]
        for client in (self.bot, getattr(self.bot, "bot_principale", None)):
            if client is None:
                continue
            try:
                utente = await client.fetch_user(user_id)
                await utente.send(testo, allowed_mentions=discord.AllowedMentions.none())
                return
            except discord.HTTPException:
                continue
        logger.warning("Promemoria dell'app per %s non consegnato: DM chiusi.", user_id)

    # ---------------------------------------------------------------- promemoria
    @promemoria.command(name="crea", description="Ti scrivo in DM tra il tempo che scegli.")
    @app_commands.describe(durata="Tra quanto, es. 30m, 2h, 7d", testo="Cosa ricordarti")
    async def crea(
        self,
        interaction: discord.Interaction,
        durata: app_commands.Range[str, 2, 10],
        testo: app_commands.Range[str, 1, 1500],
    ) -> None:
        try:
            secondi = parse_duration(durata)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        errore = errore_durata(secondi)
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        if not (await impostazioni_di(interaction.user.id)).dm_ok:
            await interaction.response.send_message(await testo_per(interaction, "app_dm_spenti"), ephemeral=True)
            return
        numero = await programma_promemoria(interaction.user.id, secondi, testo, scheduler)
        if numero is None:
            await interaction.response.send_message(
                await testo_per(interaction, "app_promemoria_troppi", massimo=MAX_PROMEMORIA), ephemeral=True
            )
            return
        await interaction.response.send_message(
            await testo_per(interaction, "app_promemoria_creato", durata=format_duration(secondi), numero=numero),
            ephemeral=True,
        )

    @promemoria.command(name="elenco", description="Mostra i tuoi promemoria in sospeso.")
    async def elenco(self, interaction: discord.Interaction) -> None:
        azioni = await scheduler.list_pending_for_user(interaction.user.id, AZIONE_PROMEMORIA, MAX_PROMEMORIA)
        if not azioni:
            await interaction.response.send_message(await testo_per(interaction, "app_promemoria_nessuno"), ephemeral=True)
            return
        righe = [
            f"`{a['id']}` · {discord.utils.format_dt(a['execute_at'], 'R')} · {a['payload'].get('message', '')[:60]}"
            for a in azioni
        ]
        embed = discord.Embed(
            title=await testo_per(interaction, "app_promemoria_titolo"), description="\n".join(righe)[:4000],
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @promemoria.command(name="annulla", description="Annulla un tuo promemoria.")
    @app_commands.describe(numero="Il numero del promemoria (da /promemoria elenco)")
    async def annulla(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2_147_483_647]) -> None:
        azione = await scheduler.get_pending_action(numero)
        if azione is None or azione["executed"] or azione["user_id"] != interaction.user.id \
                or azione["action_type"] != AZIONE_PROMEMORIA:
            await interaction.response.send_message(await testo_per(interaction, "app_promemoria_non_trovato"), ephemeral=True)
            return
        await scheduler.cancel(numero)
        await interaction.response.send_message(await testo_per(interaction, "app_promemoria_annullato", numero=numero), ephemeral=True)

    # ---------------------------------------------------------------- profilo
    @app_commands.command(name="profilo", description="La scheda di un utente; il tuo profilo globale e la rank card.")
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(utente="Di chi (vuoto: tu)", carta="Mostra anche la rank card globale come immagine")
    async def profilo(self, interaction: discord.Interaction, utente: discord.User | None = None, carta: bool = False) -> None:
        await self._mostra_profilo(interaction, utente or interaction.user, carta)

    async def menu_profilo(self, interaction: discord.Interaction, utente: discord.User) -> None:
        await self._mostra_profilo(interaction, utente)

    async def _dati_globali(self, interaction: discord.Interaction, utente: discord.abc.User) -> ProfiloGlobale | None:
        """I dati di tutti i server: per sé sempre, per gli altri solo se hanno acceso il profilo pubblico."""
        if utente.id != interaction.user.id and not (await impostazioni_di(utente.id)).profilo_pubblico:
            return None
        try:
            return await profilo_globale(utente.id)
        except Exception:  # noqa: BLE001 - dati in più: il profilo si mostra lo stesso
            logger.warning("Profilo globale non letto.", exc_info=True)
            return None

    async def _mostra_profilo(self, interaction: discord.Interaction, utente: discord.abc.User, carta: bool = False) -> None:
        privata = await risposta_privata(interaction.user.id)
        await interaction.response.defer(ephemeral=privata)
        try:
            completo = await self.bot.fetch_user(utente.id)  # serve per il banner
        except discord.HTTPException:
            completo = utente
        livello, clan = await _livello_e_clan(interaction.guild_id, utente.id)
        lingua = await lingua_interazione(interaction)
        globale = await self._dati_globali(interaction, utente)
        embed = _embed_profilo(completo, lingua, livello, clan, globale)
        file = None
        if carta and globale is None:
            embed.set_footer(text=t("app_profilo_carta_privata", lingua))
        elif carta:
            try:
                avatar = await completo.display_avatar.read()
            except discord.HTTPException:
                avatar = None
            sfondo = await leveling_repo.get_sfondo_card(utente.id)
            png = await run_image_task(render_profile_card, dati_rank_card(completo.display_name, globale), avatar, sfondo)
            file = discord.File(io.BytesIO(png), filename="profilo.png")
            embed.set_image(url="attachment://profilo.png")
        if file is None:
            await interaction.followup.send(embed=embed, ephemeral=privata)
        else:
            await interaction.followup.send(embed=embed, file=file, ephemeral=privata)

    async def menu_testo_pulito(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        pulito = testo_pulito(messaggio.content)
        await interaction.response.send_message(
            pulito or await testo_per(interaction, "app_msg_senza_testo"), ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot) -> None:
    """Solo sul client dell'app: il bot principale non riceve questi comandi."""
    if not e_istanza_app(bot):
        return
    cog = PersonaleCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(AZIONE_PROMEMORIA, cog.consegna)

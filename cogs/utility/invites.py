"""
cogs/utility/invites.py
=======================
Inviti (NF-27, SPEC §23): ogni ingresso viene attribuito all'invito usato (via
core/invite_tracker.resolve_join_invite) e registrato con il tipo di link (personale dal sito,
normale, vanity, sconosciuto); si vede quante persone ha invitato un membro, la classifica del
server (10 righe), lo storico di un membro e da chi è stato invitato. Ogni membro può avere il
suo link personale «finto vanity» sul sito (core/invite_service.py). L'attribuzione è "giusta o
sconosciuta", ma con ingressi simultanei può mancare: lo diciamo sempre (LC-6).
Comandi: `/level inviti utente|classifica|storico|link`; per lo staff `/admin-inviti impostazioni|bonus|escludi`.
Funzioni coperte: SPEC §23 (NF-27, link personali r10)
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core import invite_links_logic as logica, invite_service
from core.command_access import Livello, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config_schema import ImpostazioneNonValida
from core.database import db
from core.i18n import testo_per
from core.invite_tracker import invite_tracker
from core.premium import PremiumModule, registry
from core.repositories.invite_stats_repo import invite_stats_repo
from core.repositories.inviti_extra_repo import TroppiEsclusi, inviti_extra_repo

logger = logging.getLogger("iyokai.invites")

MODULE_INVITES = "invites"
_SG_INVITI = ("inviti", "Quante persone ha invitato ognuno")
_NESSUNA_MENZIONE = discord.AllowedMentions.none()
AVVISO_ATTRIBUZIONE = (
    "Nota: l'invito usato si riconosce con buona affidabilità, non al 100%. "
    "Con ingressi simultanei o senza il permesso «Gestisci server» l'ingresso può non essere attribuito."
)


def _data(quando) -> str:
    return f"<t:{int(quando.timestamp())}:d>"


def _righe_extra(s) -> str:
    """Bonus dello staff e ingressi non contati (account giovani o rientri), solo se ce ne sono."""
    extra = ""
    if s.bonus:
        extra += f"\nBonus dello staff: {s.bonus:+d} (totale {s.punti})."
    if s.finti:
        extra += f"\nIngressi non contati (account giovani o rientri): {s.finti}."
    return extra


async def _senza_esclusi(guild: discord.Guild, righe: list, limite: int) -> list:
    """Toglie dalla classifica gli utenti e i ruoli esclusi dallo staff."""
    if not righe:
        return []
    utenti, ruoli = await inviti_extra_repo.esclusi(guild.id)
    if not utenti and not ruoli:
        return righe[:limite]
    tenuti = []
    for uid, s in righe:
        membro = guild.get_member(uid)
        if uid in utenti or (membro is not None and ruoli & {r.id for r in membro.roles}):
            continue
        tenuti.append((uid, s))
    return tenuti[:limite]


def _riga_invitato_da(ingresso) -> str:
    """Da chi è stato invitato un membro, in una riga."""
    if ingresso is None:
        return "Non ho registrato con quale invito è entrato."
    chi = f"<@{ingresso.inviter_id}>" if ingresso.inviter_id else "nessuno di riconosciuto"
    return f"Invitato da {chi} il {_data(ingresso.joined_at)} ({logica.ETICHETTE_TIPO.get(ingresso.kind, ingresso.kind)})."


class InvitesCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot or not await db.is_module_active_for_guild(member.guild.id, MODULE_INVITES):
            return
        try:
            trovato = await invite_tracker.resolve_join_invite(member.guild, member.id)
            ingresso = await invite_service.registra_ingresso(member.guild, member.id, trovato, member.created_at)
            await self._scrivi_nel_registro(member, ingresso)
        except Exception:
            logger.exception("Errore nel registrare l'invito di %s", member.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        invite_tracker.forget_member(member.guild.id, member.id)
        if member.bot:
            return
        try:
            await invite_stats_repo.mark_left(member.guild.id, member.id)
            await invite_service.elimina_link_membro(self.bot, member.guild.id, member.id)
        except Exception:
            logger.exception("Errore nel segnare l'uscita di %s", member.id)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        invite_service.invito_cancellato(invite.code)

    async def _scrivi_nel_registro(self, member: discord.Member, ingresso: invite_service.Ingresso) -> None:
        """Una riga nel canale scelto dall'admin (se c'è): chi è entrato, con quale link, chi lo ha invitato."""
        canale_id = await db.get_guild_setting(member.guild.id, logica.SETTING_CANALE_LOG)
        canale = member.guild.get_channel(canale_id) if canale_id else None
        if not isinstance(canale, discord.TextChannel):
            return
        chi = f"<@{ingresso.invitante_id}>" if ingresso.invitante_id else "nessuno di riconosciuto"
        try:
            await canale.send(
                f"{member.mention} è entrato con {logica.ETICHETTE_TIPO[ingresso.tipo]}. Invitato da: {chi}.",
                allowed_mentions=_NESSUNA_MENZIONE,
            )
        except (discord.Forbidden, discord.HTTPException):
            logger.info("Registro inviti: messaggio non inviato nel server %s.", member.guild.id)

    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_INVITES):
            await interaction.response.send_message(
                await testo_per(interaction, "ping_questo_modulo_non_attivo_su"),
                ephemeral=True,
            )
            return False
        return True

    @comando_di_gruppo("level", nome="utente", descrizione="Quante persone ha invitato un membro.", sottogruppo=_SG_INVITI)
    @app_commands.describe(utente="Il membro (se vuoto, tu)")
    async def utente(self, interaction: discord.Interaction, utente: discord.Member | None = None) -> None:
        if not await self._pronto(interaction):
            return
        bersaglio = utente or interaction.user
        s = await invite_stats_repo.stats_for(interaction.guild.id, bersaglio.id)
        ingresso = await invite_stats_repo.ingresso_di(interaction.guild.id, bersaglio.id)
        await interaction.response.send_message(
            f"{bersaglio.mention} ha invitato {s.totale} persone: {s.presenti} sono ancora nel server, "
            f"{s.totale - s.presenti} sono uscite.{_righe_extra(s)}\n{_riga_invitato_da(ingresso)}\n{AVVISO_ATTRIBUZIONE}",
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("level", nome="classifica", descrizione="I 10 membri che hanno invitato più persone.", sottogruppo=_SG_INVITI)
    async def classifica(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        righe = await _senza_esclusi(interaction.guild, await invite_stats_repo.top(interaction.guild.id, 100, tetto=100), 10)
        if not righe:
            await interaction.response.send_message(
                f"Nessun invito registrato finora.\n{AVVISO_ATTRIBUZIONE}", ephemeral=True
            )
            return
        testo = "\n".join(
            f"{i}. <@{uid}>: {s.punti} presenti ({s.totale} in tutto{f', bonus {s.bonus:+d}' if s.bonus else ''})"
            for i, (uid, s) in enumerate(righe, 1)
        )
        await interaction.response.send_message(
            f"**Classifica inviti**\n{testo}\n{AVVISO_ATTRIBUZIONE}",
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )


    @comando_di_gruppo("level", nome="storico", descrizione="Chi ha invitato un membro e le ultime persone che ha portato.", sottogruppo=_SG_INVITI)
    @app_commands.describe(utente="Il membro (se vuoto, tu)")
    async def storico(self, interaction: discord.Interaction, utente: discord.Member | None = None) -> None:
        if not await self._pronto(interaction):
            return
        bersaglio = utente or interaction.user
        guild_id = interaction.guild.id
        s = await invite_stats_repo.stats_for(guild_id, bersaglio.id)
        ingresso = await invite_stats_repo.ingresso_di(guild_id, bersaglio.id)
        ultimi = await invite_stats_repo.invitati_da(guild_id, bersaglio.id)
        righe = [
            f"<@{r.user_id}> · {_data(r.joined_at)} · "
            + ("è ancora qui" if r.left_at is None else f"uscito il {_data(r.left_at)}")
            + f" · {logica.ETICHETTE_TIPO.get(r.kind, r.kind)}"
            for r in ultimi
        ]
        testo = (
            f"**Inviti di {bersaglio.mention}**\n{_riga_invitato_da(ingresso)}\n"
            f"Ha portato {s.totale} persone: {s.presenti} presenti, {s.totale - s.presenti} uscite."
        )
        if righe:
            testo += f"\nGli ultimi {len(righe)}:\n" + "\n".join(righe)
        await interaction.response.send_message(
            f"{testo}\n{AVVISO_ATTRIBUZIONE}", ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE
        )

    @comando_di_gruppo("level", nome="link", descrizione="Il tuo link d'invito personale, che passa dal sito del bot.", sottogruppo=_SG_INVITI)
    async def link(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        esito, link = await invite_service.ottieni_link(interaction.guild, interaction.user)
        if link is None:
            await interaction.response.send_message(logica.testo_esito(esito), ephemeral=True)
            return
        indirizzo = invite_service.indirizzo(link)
        if indirizzo is None:
            await interaction.response.send_message(
                await testo_per(interaction, "invites_il_sito_del_bot_non"),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            await testo_per(interaction, "invites_il_tuo_link_personale_chi", indirizzo=indirizzo),
            ephemeral=True,
        )

    @comando_di_gruppo("admin-inviti", nome="impostazioni", descrizione="Registro degli inviti, link personale e ingressi non contati.")
    @app_commands.describe(
        canale="Dove scrivere chi entra e con quale link",
        ruolo="Solo chi ha questo ruolo può avere il link personale",
        togli="Togli il canale del registro o il ruolo (il modulo si accende con /admin-bot setup attiva)",
        chi="Chi ha il link personale",
        eta_minima_giorni="Gli account più giovani di tanti giorni non contano (0 = spento)",
        rientri_finti="Chi esce e rientra conta come ingresso non valido? (non cambia se vuoto)",
    )
    @app_commands.choices(chi=[
        app_commands.Choice(name="tutti", value="tutti"),
        app_commands.Choice(name="chi può creare inviti", value="crea_invito"),
        app_commands.Choice(name="solo un ruolo", value="ruolo"),
        app_commands.Choice(name="nessuno", value="spento"),
    ])
    @app_commands.choices(togli=[
        app_commands.Choice(name="canale del registro", value="canale"),
        app_commands.Choice(name="ruolo richiesto", value="ruolo"),
    ])
    @richiedi(Livello.ADMIN)
    async def opzioni(
        self,
        interaction: discord.Interaction,
        canale: discord.TextChannel | None = None,
        ruolo: discord.Role | None = None,
        togli: app_commands.Choice[str] | None = None,
        chi: app_commands.Choice[str] | None = None,
        eta_minima_giorni: app_commands.Range[int, 0, logica.MAX_ETA_MINIMA_GIORNI] | None = None,
        rientri_finti: bool | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        guild = interaction.guild
        nuova_modalita = chi.value if chi else invite_service.NON_CAMBIARE
        nuovo_canale = None if togli and togli.value == "canale" else (canale.id if canale else invite_service.NON_CAMBIARE)
        nuovo_ruolo = None if togli and togli.value == "ruolo" else (ruolo.id if ruolo else invite_service.NON_CAMBIARE)
        try:
            await invite_service.imposta_opzioni(
                guild, canale_log=nuovo_canale, ruolo_link=nuovo_ruolo, modalita=nuova_modalita,
                eta_minima=invite_service.NON_CAMBIARE if eta_minima_giorni is None else eta_minima_giorni,
                rientri_finti=invite_service.NON_CAMBIARE if rientri_finti is None else rientri_finti,
                changed_by=interaction.user.id,
            )
        except ImpostazioneNonValida as errore:
            await interaction.response.send_message(str(errore), ephemeral=True)
            return
        o = await invite_service.leggi_opzioni(guild.id)
        await interaction.response.send_message(
            f"Modulo inviti: {'acceso' if o.attivo else 'spento'}.\n"
            f"Registro: {f'<#{o.canale_log_id}>' if o.canale_log_id else 'nessun canale'}.\n"
            f"Link personale: {logica.ETICHETTE_MODALITA[o.modalita]}"
            f"{f' (<@&{o.ruolo_link_id}>)' if o.modalita == 'ruolo' and o.ruolo_link_id else ''}.\n"
            + await testo_per(
                interaction, "invites_impostazioni_extra", eta=o.eta_minima_giorni or "-",
                rientri="sì" if o.rientri_finti else "no",
            ),
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("admin-inviti", nome="bonus", descrizione="Aggiungi o togli inviti a un membro (punti dello staff).")
    @app_commands.describe(membro="A chi cambiare i punti", quanti="Quanti punti aggiungere (negativo per togliere)")
    @richiedi(Livello.ADMIN)
    async def bonus(
        self, interaction: discord.Interaction, membro: discord.Member,
        quanti: app_commands.Range[int, -logica.MAX_BONUS, logica.MAX_BONUS],
    ) -> None:
        if not await self._pronto(interaction):
            return
        if membro.bot or quanti == 0:
            await interaction.response.send_message(await testo_per(interaction, "invites_bonus_non_valido"), ephemeral=True)
            return
        totale = await inviti_extra_repo.aggiungi_bonus(interaction.guild.id, membro.id, quanti, interaction.user.id)
        logger.info("Inviti: bonus %+d a %s nel server %s da %s", quanti, membro.id, interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            await testo_per(interaction, "invites_bonus_fatto", membro=membro.mention, quanti=f"{quanti:+d}", totale=totale),
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("admin-inviti", nome="escludi", descrizione="Nascondi membri o ruoli dalla classifica degli inviti.")
    @app_commands.describe(azione="Cosa fare", utente="Il membro", ruolo="Il ruolo (chi lo ha non compare)")
    @app_commands.choices(azione=[
        app_commands.Choice(name="aggiungi", value="aggiungi"),
        app_commands.Choice(name="togli", value="togli"),
        app_commands.Choice(name="elenco", value="elenco"),
    ])
    @richiedi(Livello.ADMIN)
    async def escludi(
        self, interaction: discord.Interaction, azione: app_commands.Choice[str],
        utente: discord.Member | None = None, ruolo: discord.Role | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        guild_id = interaction.guild.id
        if azione.value == "elenco":
            utenti, ruoli = await inviti_extra_repo.esclusi(guild_id)
            righe = [f"<@{u}>" for u in sorted(utenti)[:50]] + [f"<@&{r}>" for r in sorted(ruoli)[:50]]
            testo = ", ".join(righe) if righe else await testo_per(interaction, "invites_nessun_escluso")
            await interaction.response.send_message(testo[:1900], ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)
            return
        bersagli = [("utente", utente.id)] if utente else []
        if ruolo is not None:
            bersagli.append(("ruolo", ruolo.id))
        if not bersagli:
            await interaction.response.send_message(await testo_per(interaction, "invites_scegli_utente_o_ruolo"), ephemeral=True)
            return
        try:
            for tipo, id_ in bersagli:
                if azione.value == "aggiungi":
                    await inviti_extra_repo.aggiungi_escluso(guild_id, tipo, id_)
                else:
                    await inviti_extra_repo.togli_escluso(guild_id, tipo, id_)
        except TroppiEsclusi:
            await interaction.response.send_message(
                await testo_per(interaction, "invites_troppi_esclusi", massimo=logica.MAX_ESCLUSI), ephemeral=True
            )
            return
        await interaction.response.send_message(await testo_per(interaction, "invites_escluso_fatto"), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_INVITES,
            display_name="Inviti",
            category="community",
            description="Chi ha invitato chi e classifica degli inviti.",
            premium_capable=False,
        )
    )
    await bot.add_cog(InvitesCog(bot))

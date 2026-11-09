"""
cogs/utility/giveaway_extra.py
==============================
Giveaway, parte 2 (catalogo #128, D69 B9-B10): elenco dei partecipanti, bottone «Riepilogo», opzioni del
server (aspetto, messaggi, log, ruoli esclusi), modifica di un giveaway e menu «Riestrai giveaway».
Funzioni coperte: SPEC §15.5 (NF-28), UTL-116, 119, 120, 126, 128, 129, 130, 132, 133
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.command_access import Livello, puo_usare
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.giveaway_fine import concludi
from core.giveaway_logic import (
    MAX_BOTTONE_TESTO,
    MAX_MSG_CONFERMA,
    MAX_MSG_DM,
    MAX_RUOLI_ESCLUSI,
    PARTECIPANTI_PER_PAGINA,
    embed_annuncio,
    motivo_immagine_non_valida,
    pagine_partecipanti,
    parse_colore,
    pick_winners_pesati,
    righe_partecipanti,
)
from core.i18n import lingua_risposta, testo_per
from core.repositories.giveaway_repo import giveaway_repo
from core.ui_base import BaseModal, BaseView, _utente_o_server_in_blacklist
from core.role_menu_logic import valida_emoji

logger = logging.getLogger("iyokai.giveaway_extra")

MODULO = "leveling"  # i giveaway stanno nel modulo «Livelli & Economia»
NOME_MENU_RIESTRAI = "Riestrai giveaway"
_NESSUNA_MENZIONE = discord.AllowedMentions.none()
SECONDI_DI_VITA = 180


async def _server_pronto(interaction: discord.Interaction) -> bool:
    """Solo in un server con il modulo acceso. Risponde da solo se no."""
    if interaction.guild is None:
        await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
        return False
    if not await db.is_module_active_for_guild(interaction.guild.id, MODULO):
        await interaction.response.send_message(await testo_per(interaction, "leveling_questo_modulo_non_attivo_su"), ephemeral=True)
        return False
    return True


# ====================================================================
# Elenco dei partecipanti (a pagine da 20)
# ====================================================================
async def _testo_pagina(interaction: discord.Interaction, giveaway_id: int, pagina: int, totale: int) -> str:
    pagine = pagine_partecipanti(totale)
    scarto = (pagina - 1) * PARTECIPANTI_PER_PAGINA
    ids = await giveaway_repo.list_partecipanti(giveaway_id, PARTECIPANTI_PER_PAGINA, scarto)
    intestazione = await testo_per(
        interaction, "giveaway_partecipanti_titolo", id=giveaway_id, totale=totale, pagina=pagina, pagine=pagine
    )
    corpo = righe_partecipanti(ids, scarto + 1) or await testo_per(interaction, "giveaway_nessun_partecipante")
    return f"{intestazione}\n{corpo}"


class ListaPartecipantiView(BaseView):
    """Sfoglia i partecipanti: solo chi ha aperto l'elenco può usare i tasti."""

    def __init__(self, giveaway_id: int, proprietario: int, totale: int) -> None:
        super().__init__(timeout=SECONDI_DI_VITA)
        self.giveaway_id = giveaway_id
        self.proprietario = proprietario
        self.totale = totale
        self.pagina = 1
        self._aggiorna_tasti()

    def _aggiorna_tasti(self) -> None:
        pagine = pagine_partecipanti(self.totale)
        self.indietro.disabled = self.pagina <= 1
        self.avanti.disabled = self.pagina >= pagine

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.proprietario:
            await interaction.response.send_message(await testo_per(interaction, "giveaway_non_e_tuo"), ephemeral=True)
            return False
        return True

    async def _vai(self, interaction: discord.Interaction, pagina: int) -> None:
        self.pagina = pagina
        self._aggiorna_tasti()
        testo = await _testo_pagina(interaction, self.giveaway_id, self.pagina, self.totale)
        await interaction.response.edit_message(content=testo, view=self, allowed_mentions=_NESSUNA_MENZIONE)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def indietro(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._vai(interaction, max(1, self.pagina - 1))

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def avanti(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._vai(interaction, min(pagine_partecipanti(self.totale), self.pagina + 1))


async def mostra_partecipanti(interaction: discord.Interaction, giveaway_id: int) -> None:
    """Risposta effimera con la prima pagina. Usata dal bottone «Partecipanti» e dal comando."""
    totale = await giveaway_repo.count_entries(giveaway_id)
    testo = await _testo_pagina(interaction, giveaway_id, 1, totale)
    vista = ListaPartecipantiView(giveaway_id, interaction.user.id, totale)
    await interaction.response.send_message(testo, view=vista, ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)


# ====================================================================
# Bottone «Riepilogo» del messaggio finale
# ====================================================================
class BottoneRiepilogo(discord.ui.DynamicItem[discord.ui.Button], template=r"giveaway_riep:(?P<id>[0-9]+)"):
    """Sul messaggio dei vincitori: premio, partecipanti, vincitori. Vale anche dopo un riavvio."""

    def __init__(self, giveaway_id: int, etichetta: str = "Riepilogo") -> None:
        super().__init__(
            discord.ui.Button(label=etichetta[:45], emoji="📋", style=discord.ButtonStyle.secondary,
                              custom_id=f"giveaway_riep:{giveaway_id}")
        )
        self.giveaway_id = giveaway_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        # SEC-10: un bottone dinamico non ha una BaseView sopra di sé, il controllo blacklist si fa qui.
        return not await _utente_o_server_in_blacklist(interaction)

    async def callback(self, interaction: discord.Interaction) -> None:
        giveaway = await giveaway_repo.get_giveaway(self.giveaway_id)
        if giveaway is None or interaction.guild is None or giveaway.guild_id != interaction.guild.id:
            await interaction.response.send_message(await testo_per(interaction, "giveaway_non_trovato"), ephemeral=True)
            return
        partecipanti = await giveaway_repo.count_entries(giveaway.id)
        vincitori = await giveaway_repo.get_vincitori(giveaway.id)
        testo = await testo_per(
            interaction, "giveaway_riepilogo", premio=giveaway.prize[:200], id=giveaway.id,
            partecipanti=partecipanti, termine=int(giveaway.ends_at.timestamp()),
            vincitori=", ".join(f"<@{u}>" for u in vincitori[:50]) or "-",
        )
        await interaction.response.send_message(testo[:2000], ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE)


# ====================================================================
# Opzioni del server: pannello con menu dei ruoli esclusi e finestre
# ====================================================================
class FinestraAspetto(BaseModal):
    def __init__(self, opzioni, titolo: str, etichette: dict[str, str]) -> None:
        super().__init__(title=titolo[:45], timeout=SECONDI_DI_VITA)
        self.colore = discord.ui.TextInput(
            label=etichette["colore"][:45], required=False, min_length=0, max_length=7,
            default=f"#{opzioni.colore:06X}" if opzioni.colore is not None else None, placeholder="#5865F2",
        )
        self.emoji = discord.ui.TextInput(
            label=etichette["emoji"][:45], required=False, max_length=64, default=opzioni.bottone_emoji, placeholder="🎉",
        )
        self.testo = discord.ui.TextInput(
            label=etichette["testo"][:45], required=False, max_length=MAX_BOTTONE_TESTO, default=opzioni.bottone_testo,
        )
        for campo in (self.colore, self.emoji, self.testo):
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        campi: dict = {}
        valore = self.colore.value.strip()
        if valore:
            colore = parse_colore(valore)
            if colore is None:
                await interaction.response.send_message(await testo_per(interaction, "giveaway_colore_non_valido"), ephemeral=True)
                return
            campi["colore"] = colore
        else:
            campi["colore"] = None
        emoji = self.emoji.value.strip()
        if emoji and not valida_emoji(emoji):
            await interaction.response.send_message(await testo_per(interaction, "giveaway_emoji_non_valida"), ephemeral=True)
            return
        campi["bottone_emoji"] = emoji or None
        campi["bottone_testo"] = self.testo.value.strip() or None
        await giveaway_repo.set_opzioni(interaction.guild.id, **campi)
        await interaction.response.send_message(await testo_per(interaction, "giveaway_opzioni_salvate"), ephemeral=True)


class FinestraMessaggi(BaseModal):
    def __init__(self, opzioni, titolo: str, etichette: dict[str, str]) -> None:
        super().__init__(title=titolo[:45], timeout=SECONDI_DI_VITA)
        self.conferma = discord.ui.TextInput(
            label=etichette["conferma"][:45], style=discord.TextStyle.paragraph, required=False,
            max_length=MAX_MSG_CONFERMA, default=opzioni.msg_conferma,
        )
        self.dm = discord.ui.TextInput(
            label=etichette["dm"][:45], style=discord.TextStyle.paragraph, required=False,
            max_length=MAX_MSG_DM, default=opzioni.msg_dm,
        )
        self.add_item(self.conferma)
        self.add_item(self.dm)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await giveaway_repo.set_opzioni(
            interaction.guild.id,
            msg_conferma=self.conferma.value.strip() or None, msg_dm=self.dm.value.strip() or None,
        )
        await interaction.response.send_message(await testo_per(interaction, "giveaway_opzioni_salvate"), ephemeral=True)


class MenuRuoliEsclusi(discord.ui.RoleSelect):
    def __init__(self, esclusi: tuple[int, ...], segnaposto: str) -> None:
        super().__init__(
            placeholder=segnaposto[:150], min_values=0, max_values=MAX_RUOLI_ESCLUSI,
            default_values=[discord.Object(id=r, type=discord.Role) for r in esclusi[:MAX_RUOLI_ESCLUSI]],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        ruoli = tuple(r.id for r in self.values)
        await giveaway_repo.set_opzioni(interaction.guild.id, ruoli_esclusi=ruoli)
        await interaction.response.send_message(
            await testo_per(interaction, "giveaway_esclusi_salvati", n=len(ruoli)), ephemeral=True
        )


class PannelloOpzioni(BaseView):
    """Menu dei ruoli esclusi (fino a 25) e due finestre. Solo chi ha aperto il pannello."""

    def __init__(self, proprietario: int, opzioni, testi: dict[str, str]) -> None:
        super().__init__(timeout=SECONDI_DI_VITA)
        self.proprietario = proprietario
        self.testi = testi
        self.opzioni = opzioni
        self.add_item(MenuRuoliEsclusi(opzioni.ruoli_esclusi, testi["menu"]))
        self.aspetto.label = testi["bottone_aspetto"][:45]
        self.messaggi.label = testi["bottone_messaggi"][:45]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.proprietario:
            await interaction.response.send_message(await testo_per(interaction, "giveaway_non_e_tuo"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Aspetto", style=discord.ButtonStyle.secondary, row=1)
    async def aspetto(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        opzioni = await giveaway_repo.get_opzioni(interaction.guild.id)
        await interaction.response.send_modal(FinestraAspetto(opzioni, self.testi["titolo_aspetto"], self.testi))

    @discord.ui.button(label="Messaggi", style=discord.ButtonStyle.secondary, row=1)
    async def messaggi(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        opzioni = await giveaway_repo.get_opzioni(interaction.guild.id)
        await interaction.response.send_modal(FinestraMessaggi(opzioni, self.testi["titolo_messaggi"], self.testi))


async def _testi_pannello(interaction: discord.Interaction) -> dict[str, str]:
    chiavi = {
        "menu": "giveaway_menu_esclusi", "bottone_aspetto": "giveaway_bottone_aspetto",
        "bottone_messaggi": "giveaway_bottone_messaggi", "titolo_aspetto": "giveaway_titolo_aspetto",
        "titolo_messaggi": "giveaway_titolo_messaggi", "colore": "giveaway_campo_colore", "emoji": "giveaway_campo_emoji",
        "testo": "giveaway_campo_testo", "conferma": "giveaway_campo_conferma", "dm": "giveaway_campo_dm",
    }
    return {nome: await testo_per(interaction, chiave) for nome, chiave in chiavi.items()}


def _riga_stato(opzioni, testi_lingua: str) -> str:
    return testi_lingua.format(
        colore=f"#{opzioni.colore:06X}" if opzioni.colore is not None else "-",
        emoji=opzioni.bottone_emoji or "🎉", testo=opzioni.bottone_testo or "-",
        log=f"<#{opzioni.canale_log}>" if opzioni.canale_log else "-",
        esclusi=len(opzioni.ruoli_esclusi),
        conferma="sì" if opzioni.msg_conferma else "-", dm="sì" if opzioni.msg_dm else "-",
    )


# ====================================================================
# Il cog
# ====================================================================
class GiveawayExtraCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._menu = app_commands.ContextMenu(name=NOME_MENU_RIESTRAI, callback=self.menu_riestrai)
        self._menu.guild_only = True
        # Permesso di base come per il gruppo; il controllo vero è nel callback.
        self._menu.default_permissions = discord.Permissions(manage_guild=True)

    async def cog_load(self) -> None:
        await super().cog_load()
        self.bot.tree.add_command(self._menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(NOME_MENU_RIESTRAI, type=discord.AppCommandType.message)
        await super().cog_unload()

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, canale: discord.abc.GuildChannel) -> None:
        try:
            await giveaway_repo.togli_canale(canale.guild.id, canale.id)
        except Exception:
            logger.exception("Giveaway: pulizia del canale %s fallita", canale.id)

    # ---------------------------------------------------------------- partecipanti
    @comando_di_gruppo("admin-giveaway", nome="partecipanti", descrizione="Chi partecipa a un giveaway, a pagine da 20.")
    @app_commands.describe(id="Il numero del giveaway")
    async def partecipanti(self, interaction: discord.Interaction, id: app_commands.Range[int, 1, 2_147_483_647]) -> None:
        if not await _server_pronto(interaction):
            return
        giveaway = await giveaway_repo.get_del_server(interaction.guild.id, id)
        if giveaway is None:
            await interaction.response.send_message(await testo_per(interaction, "giveaway_non_trovato"), ephemeral=True)
            return
        await mostra_partecipanti(interaction, giveaway.id)

    # ---------------------------------------------------------------- opzioni
    @comando_di_gruppo("admin-giveaway", nome="opzioni", descrizione="Aspetto, messaggi, log e ruoli esclusi dei giveaway.")
    @app_commands.describe(
        canale_log="Dove scrivere la fine di ogni giveaway", senza_log="Smetti di scrivere nel canale di log",
    )
    async def opzioni(
        self, interaction: discord.Interaction, canale_log: discord.TextChannel | None = None, senza_log: bool = False,
    ) -> None:
        if not await _server_pronto(interaction):
            return
        if canale_log is not None:
            permessi = canale_log.permissions_for(interaction.guild.me)
            if not (permessi.view_channel and permessi.send_messages and permessi.embed_links):
                await interaction.response.send_message(
                    await testo_per(interaction, "giveaway_log_senza_permessi", canale=canale_log.mention), ephemeral=True,
                    allowed_mentions=_NESSUNA_MENZIONE,
                )
                return
            await giveaway_repo.set_opzioni(interaction.guild.id, canale_log=canale_log.id)
        elif senza_log:
            await giveaway_repo.set_opzioni(interaction.guild.id, canale_log=None)
        opzioni = await giveaway_repo.get_opzioni(interaction.guild.id)
        testi = await _testi_pannello(interaction)
        stato = _riga_stato(opzioni, await testo_per(interaction, "giveaway_opzioni_stato"))
        await interaction.response.send_message(
            stato, view=PannelloOpzioni(interaction.user.id, opzioni, testi), ephemeral=True,
            allowed_mentions=_NESSUNA_MENZIONE,
        )

    # ---------------------------------------------------------------- modifica
    async def _completa_giveaway(self, interaction: discord.Interaction, corrente: str) -> list[app_commands.Choice[int]]:
        if interaction.guild is None:
            return []
        trovati = await giveaway_repo.list_modificabili(interaction.guild.id, corrente.strip()[:50], 25)
        return [app_commands.Choice(name=f"#{g.id} {g.prize}"[:100], value=g.id) for g in trovati]

    @comando_di_gruppo("admin-giveaway", nome="modifica", descrizione="Cambia durata, vincitori, premio o immagine di un giveaway.")
    @app_commands.describe(
        id="Il giveaway da cambiare", durata="Minuti da adesso alla fine (se non è partito: la durata)",
        vincitori="Nuovo numero di vincitori", premio="Nuovo premio", immagine="Nuova immagine",
    )
    @app_commands.autocomplete(id=_completa_giveaway)
    async def modifica(
        self,
        interaction: discord.Interaction,
        id: app_commands.Range[int, 1, 2_147_483_647],
        durata: app_commands.Range[int, 1, 43200] | None = None,
        vincitori: app_commands.Range[int, 1, 50] | None = None,
        premio: app_commands.Range[str, 1, 200] | None = None,
        immagine: discord.Attachment | None = None,
    ) -> None:
        if not await _server_pronto(interaction):
            return
        if durata is None and vincitori is None and premio is None and immagine is None:
            await interaction.response.send_message(await testo_per(interaction, "giveaway_modifica_niente"), ephemeral=True)
            return
        if immagine is not None:
            errore = motivo_immagine_non_valida(immagine.content_type, immagine.width, immagine.height, immagine.size)
            if errore:
                await interaction.response.send_message(await testo_per(interaction, errore), ephemeral=True)
                return
        await interaction.response.defer(ephemeral=True)
        adesso = datetime.now(timezone.utc)
        giveaway = await giveaway_repo.modifica(
            interaction.guild.id, id, prize=premio, winners_count=vincitori,
            ends_at=adesso + timedelta(minutes=durata) if durata else None,
            duration_seconds=durata * 60 if durata else None,
            immagine_url=immagine.url if immagine else None,
        )
        if giveaway is None:
            await interaction.followup.send(await testo_per(interaction, "giveaway_modifica_non_possibile"))
            return
        await self._aggiorna_annuncio(interaction.guild, giveaway)
        await interaction.followup.send(await testo_per(interaction, "giveaway_modificato", id=giveaway.id))

    async def _aggiorna_annuncio(self, guild: discord.Guild, giveaway) -> None:
        """Riscrive l'embed dell'annuncio se il messaggio c'è ancora; se no, nessun errore."""
        if giveaway.message_id is None:
            return
        from core.giveaway_worker import _canale_del_giveaway

        canale = await _canale_del_giveaway(guild, giveaway.channel_id)
        if canale is None:
            return
        opzioni = await giveaway_repo.get_opzioni(guild.id)
        lingua = await lingua_risposta(guild.id, pubblica=True)
        try:
            messaggio = await canale.fetch_message(giveaway.message_id)
            await messaggio.edit(embed=embed_annuncio(giveaway, opzioni, lingua))
        except discord.HTTPException:
            logger.info("Giveaway %s: annuncio non aggiornato", giveaway.id)

    # ---------------------------------------------------------------- riestrai
    async def menu_riestrai(self, interaction: discord.Interaction, messaggio: discord.Message) -> None:
        if interaction.guild is None or not await puo_usare(interaction, Livello.ADMIN):
            await interaction.response.send_message(await testo_per(interaction, "giveaway_solo_staff"), ephemeral=True)
            return
        giveaway = await giveaway_repo.get_by_message(interaction.guild.id, messaggio.id)
        if giveaway is None:
            await interaction.response.send_message(await testo_per(interaction, "giveaway_menu_non_annuncio"), ephemeral=True)
            return
        if not giveaway.ended:
            await interaction.response.send_message(await testo_per(interaction, "giveaway_non_ancora_finito"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        candidati = await giveaway_repo.get_entries_ripescabili(giveaway.id)
        nuovi = pick_winners_pesati(candidati, giveaway.winners_count, random.Random())
        if not nuovi:
            await interaction.followup.send(await testo_per(interaction, "giveaway_nessuno_da_ripescare"))
            return
        await giveaway_repo.segna_vincitori(giveaway.id, nuovi)
        from core.giveaway_worker import _canale_del_giveaway, _vista_riepilogo

        canale = await _canale_del_giveaway(interaction.guild, giveaway.channel_id)
        opzioni = await giveaway_repo.get_opzioni(interaction.guild.id)
        lingua = await lingua_risposta(interaction.guild.id, pubblica=True)
        if canale is not None:
            await concludi(canale, interaction.guild, giveaway, nuovi, opzioni, lingua,
                           vista=_vista_riepilogo(giveaway.id), riestrazione=True)
        await interaction.followup.send(
            await testo_per(interaction, "giveaway_riestratto_ok", n=len(nuovi)), allowed_mentions=_NESSUNA_MENZIONE
        )


async def setup(bot: commands.Bot) -> None:
    bot.add_dynamic_items(BottoneRiepilogo)
    await bot.add_cog(GiveawayExtraCog(bot))

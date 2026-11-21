"""
cogs/leveling/inventario.py
===========================
Inventario del negozio: /monete inventario, usa, regala, vendi, oggetto; /admin-economia regalabile
e azzera-inventari. Gli oggetti comprati restano all'utente; ogni passaggio è una scrittura
condizionata (vedi core/repositories/inventario_repo.py).
Funzioni coperte: ECO-058, ECO-059, ECO-070, ECO-071, ECO-072, ECO-073, ECO-086
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.leveling import IdOggetto, _comando_rifiutato
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_guild, testo_per
from core.leveling_azzera_logic import nome_confermato
from datetime import datetime, timezone

from core.leveling_logic import prezzo_rivendita, tasso_del_giorno
from core.repositories.inventario_repo import Esito, inventario_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.shop_repo import shop_repo
from core.repositories.sociale_repo import sociale_repo
from core.role_safety import check_role_assignable

logger = logging.getLogger("iyokai.leveling.inventario")
NESSUNA_MENZIONE = discord.AllowedMentions.none()


class InventarioCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    @comando_di_gruppo("monete", nome="inventario", descrizione="Gli oggetti che hai comprato.")
    async def inventario(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        voci = await inventario_repo.lista(interaction.guild.id, interaction.user.id)
        if not voci:
            await interaction.response.send_message(await testo_per(interaction, "inv_vuoto"), ephemeral=True)
            return
        righe = [f"`{v.item_id}` **{discord.utils.escape_markdown(v.nome)}** x{v.quantita}" for v in voci]
        embed = discord.Embed(
            title=await testo_per(interaction, "inv_titolo"), description="\n".join(righe)[:4000], color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("monete", nome="usa", descrizione="Usa un oggetto del tuo inventario.")
    @app_commands.describe(item_id="ID dell'oggetto (vedi /monete inventario)")
    async def usa(self, interaction: discord.Interaction, item_id: IdOggetto) -> None:
        if await _comando_rifiutato(interaction):
            return
        guild = interaction.guild
        item = await shop_repo.get_item(item_id, guild.id)
        if item is None:
            await interaction.response.send_message(await testo_per(interaction, "inv_non_lo_hai"), ephemeral=True)
            return
        extra = ""
        if item.azione == "monete":  # ECO-060: pezzo e monete nella stessa transazione
            saldo = await inventario_repo.usa_con_monete(guild.id, interaction.user.id, item_id, item.azione_valore)
            if saldo is None:
                await interaction.response.send_message(await testo_per(interaction, "inv_non_lo_hai"), ephemeral=True)
                return
            extra = await testo_per(interaction, "inv_azione_monete", monete=item.azione_valore, saldo=saldo)
        elif item.azione in ("ruolo_dai", "ruolo_togli"):
            ruolo = guild.get_role(item.azione_valore)
            motivo = "ruolo non trovato" if ruolo is None else check_role_assignable(guild, ruolo, interaction.user, self_service=True)
            if motivo is not None:  # prima di consumare: se il ruolo non si può dare il pezzo resta
                await interaction.response.send_message(f"❌ {motivo}", ephemeral=True)
                return
            if not await inventario_repo.usa(guild.id, interaction.user.id, item_id):
                await interaction.response.send_message(await testo_per(interaction, "inv_non_lo_hai"), ephemeral=True)
                return
            try:
                if item.azione == "ruolo_dai":
                    await interaction.user.add_roles(ruolo, reason="Oggetto usato")
                else:
                    await interaction.user.remove_roles(ruolo, reason="Oggetto usato")
            except discord.HTTPException:
                await inventario_repo.restituisci(guild.id, interaction.user.id, item_id)
                await interaction.response.send_message(await testo_per(interaction, "inv_azione_fallita"), ephemeral=True)
                return
            extra = await testo_per(interaction, "inv_azione_ruolo", ruolo=ruolo.name[:60])
        elif not await inventario_repo.usa(guild.id, interaction.user.id, item_id):
            await interaction.response.send_message(await testo_per(interaction, "inv_non_lo_hai"), ephemeral=True)
            return
        testo = (item.reply_text or await testo_guild(guild, "inv_usato", nome=item.name)) + (f"\n{extra}" if extra else "")
        await interaction.response.send_message(testo[:1900], allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("admin-giochi", nome="oggetto-azione", descrizione="Cosa fa un oggetto del negozio quando lo si usa: monete o un ruolo.")
    @app_commands.describe(item_id="ID dell'oggetto", azione="Cosa succede", monete="Monete (solo per «Dà monete»)", ruolo="Il ruolo (per «Dà un ruolo» o «Toglie un ruolo»)")
    @app_commands.choices(azione=[
        app_commands.Choice(name="Niente", value="nessuna"), app_commands.Choice(name="Dà monete", value="monete"),
        app_commands.Choice(name="Dà un ruolo", value="ruolo_dai"), app_commands.Choice(name="Toglie un ruolo", value="ruolo_togli"),
    ])
    async def oggetto_azione(
        self, interaction: discord.Interaction, item_id: IdOggetto, azione: app_commands.Choice[str],
        monete: app_commands.Range[int, 1, 100_000] | None = None, ruolo: discord.Role | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        valore = monete if azione.value == "monete" else (ruolo.id if ruolo else None)
        if ruolo is not None and azione.value in ("ruolo_dai", "ruolo_togli"):
            motivo = check_role_assignable(interaction.guild, ruolo, interaction.user, self_service=True)
            if motivo is not None:
                await interaction.response.send_message(f"❌ {motivo}", ephemeral=True)
                return
        try:
            trovato = await shop_repo.imposta_azione(item_id, interaction.guild.id, azione.value, valore)
        except ValueError as errore:
            await interaction.response.send_message(f"❌ {errore}", ephemeral=True)
            return
        await interaction.response.send_message(await testo_per(interaction, "eco_salvato" if trovato else "inv_oggetto_inesistente"), ephemeral=True)

    @comando_di_gruppo("monete", nome="regala", descrizione="Regala un oggetto del tuo inventario a un altro membro.")
    @app_commands.describe(membro="Chi lo riceve", item_id="ID dell'oggetto (vedi /monete inventario)")
    async def regala(self, interaction: discord.Interaction, membro: discord.Member, item_id: IdOggetto) -> None:
        if await _comando_rifiutato(interaction):
            return
        if membro.id == interaction.user.id:
            await interaction.response.send_message(await testo_per(interaction, "leveling_non_puoi_pagare_te_stesso"), ephemeral=True)
            return
        if membro.bot:
            await interaction.response.send_message(await testo_per(interaction, "leveling_non_puoi_pagare_un_bot"), ephemeral=True)
            return
        if await sociale_repo.ha_bloccato(membro.id, interaction.user.id):  # ECO-155
            await interaction.response.send_message(await testo_per(interaction, "soc_bloccato"), ephemeral=True)
            return
        esito = await inventario_repo.regala(interaction.guild.id, interaction.user.id, membro.id, item_id)
        if esito is Esito.NON_REGALABILE:
            await interaction.response.send_message(await testo_per(interaction, "inv_non_regalabile"), ephemeral=True)
            return
        if esito is not Esito.FATTO:
            await interaction.response.send_message(await testo_per(interaction, "inv_non_lo_hai"), ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "inv_regalato", da=interaction.user.mention, a=membro.mention, id=item_id, pubblica=True),
            allowed_mentions=discord.AllowedMentions(users=[membro]),
        )

    @comando_di_gruppo("monete", nome="vendi", descrizione="Rivendi un oggetto per metà del suo prezzo.")
    @app_commands.describe(item_id="ID dell'oggetto (vedi /monete inventario)")
    async def vendi(self, interaction: discord.Interaction, item_id: IdOggetto) -> None:
        if await _comando_rifiutato(interaction):
            return
        r = await inventario_repo.vendi(interaction.guild.id, interaction.user.id, item_id)
        if r.esito is not Esito.FATTO:
            chiave = "inv_niente_da_pagare" if r.esito is Esito.NIENTE_DA_PAGARE else "inv_non_lo_hai"
            await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)
            return
        moneta = (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni.currency_name
        await interaction.response.send_message(
            await testo_per(interaction, "inv_venduto", monete=r.monete, moneta=moneta, saldo=r.saldo), ephemeral=True
        )

    @comando_di_gruppo("monete", nome="oggetto", descrizione="La scheda di un oggetto del negozio.")
    @app_commands.describe(item_id="ID dell'oggetto (vedi /monete shop list)")
    async def oggetto(self, interaction: discord.Interaction, item_id: IdOggetto) -> None:
        if await _comando_rifiutato(interaction):
            return
        item = await shop_repo.get_item(item_id, interaction.guild.id)
        if item is None:
            await interaction.response.send_message(await testo_per(interaction, "inv_oggetto_inesistente"), ephemeral=True)
            return
        embed = discord.Embed(title=item.name[:250], description=(item.description or "")[:2000], color=discord.Color.gold())
        for chiave, valore in (
            ("inv_prezzo", item.price), ("inv_rivendita", prezzo_rivendita(item.price, tasso_del_giorno(interaction.guild.id, datetime.now(timezone.utc).date()))),
            ("inv_scorte", item.stock if item.stock is not None else "∞"),
            ("inv_regalabile", "✅" if item.regalabile else "❌"),
        ):
            embed.add_field(name=await testo_per(interaction, chiave), value=str(valore), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("admin-economia", nome="regalabile", descrizione="Decidi se un oggetto del negozio si può regalare.")
    @app_commands.describe(item_id="ID dell'oggetto", regalabile="Sì = si può regalare")
    async def regalabile(self, interaction: discord.Interaction, item_id: IdOggetto, regalabile: bool) -> None:
        if await _comando_rifiutato(interaction):
            return
        item = await shop_repo.update_item(item_id, interaction.guild.id, regalabile=regalabile)
        chiave = "inv_oggetto_inesistente" if item is None else "eco_salvato"
        await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)

    @comando_di_gruppo(
        "admin-economia", nome="azzera-inventari", descrizione="Svuota gli inventari di tutto il server (scrivi il nome del server)."
    )
    @app_commands.describe(conferma="Scrivi qui il nome esatto del server")
    async def azzera_inventari(self, interaction: discord.Interaction, conferma: app_commands.Range[str, 1, 100]) -> None:
        if await _comando_rifiutato(interaction):
            return
        if not interaction.permissions.manage_guild:
            await interaction.response.send_message(await testo_per(interaction, "azz_serve_gestire_server"), ephemeral=True)
            return
        if not nome_confermato(conferma, interaction.guild.name):
            await interaction.response.send_message(await testo_per(interaction, "eco_azzera_nome_sbagliato"), ephemeral=True)
            return
        tolte = await inventario_repo.azzera_server(interaction.guild.id)
        logger.info("Inventari azzerati: server %s, staff %s, %s righe.", interaction.guild.id, interaction.user.id, tolte)
        await interaction.response.send_message(await testo_per(interaction, "inv_azzerati", righe=tolte), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InventarioCog(bot))

"""
core/rete_protezione_vista.py
=============================
I tasti della rete di protezione che restano validi anche dopo un riavvio (DynamicItem): «Togli timeout» (account
compromesso), «Banna» e «Ignora» (proposta della rete dei ban), «Annulla ban». Il tasto porta solo numeri; chi lo preme
viene ricontrollato ADESSO sul server vero: proprietario del server o del bot, oppure (ban) chi ha il permesso di bannare.
Funzioni coperte: SPEC §6.22 (VER-025)
Dipende da: core/rete_protezione.py
"""

from __future__ import annotations

import re

import discord

from core import rete_protezione as rete
from core.config import config
from core.i18n import testo_guild, testo_per
from core.ui_base import BaseView
from core.repositories.rete_repo import rete_repo

MODELLO = r"rete:(?P<az>to|ap|ri|an):(?P<a>\d{1,20}):(?P<b>\d{1,20})"
_ETICHETTE = {"to": "rete_btn_togli_timeout", "ap": "rete_btn_banna", "ri": "rete_btn_ignora", "an": "rete_btn_annulla_ban"}
_STILI = {"to": discord.ButtonStyle.primary, "ap": discord.ButtonStyle.danger, "ri": discord.ButtonStyle.secondary, "an": discord.ButtonStyle.secondary}


def puo_decidere_ban(guild: discord.Guild | None, utente_id: int) -> bool:
    """Proprietario del bot, proprietario del server o chi ha il permesso di bannare in quel server (letto ora)."""
    if guild is None:
        return False
    if utente_id in (config.OWNER_ID, guild.owner_id):
        return True
    membro = guild.get_member(utente_id)
    return membro is not None and membro.guild_permissions.ban_members


def puo_togliere_timeout(guild: discord.Guild | None, utente_id: int) -> bool:
    return guild is not None and utente_id in (config.OWNER_ID, guild.owner_id)


class BottoneRete(discord.ui.DynamicItem[discord.ui.Button], template=MODELLO):
    def __init__(self, az: str, a: int, b: int, etichetta: str = "") -> None:
        super().__init__(discord.ui.Button(label=(etichetta or az)[:80], style=_STILI[az], custom_id=f"rete:{az}:{a}:{b}"))
        self.az, self.a, self.b = az, a, b

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]):
        return cls(match["az"], int(match["a"]), int(match["b"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        bot = interaction.client
        if self.az == "to":
            guild = bot.get_guild(self.a)
            if not puo_togliere_timeout(guild, interaction.user.id):
                return await interaction.response.send_message(await testo_per(interaction, "rete_non_permesso"), ephemeral=True)
            fatto = await rete.togli_timeout(bot, guild, self.b, interaction.user.id)
            chiave = "rete_timeout_tolto" if fatto else "rete_timeout_non_c_e"
            return await interaction.response.send_message(await testo_per(interaction, chiave, utente=f"<@{self.b}>"), ephemeral=True)
        proposta = await rete_repo.proposta(self.a)
        guild = bot.get_guild(proposta["guild_dest"]) if proposta else None
        if not puo_decidere_ban(guild, interaction.user.id):
            return await interaction.response.send_message(await testo_per(interaction, "rete_non_permesso"), ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        if self.az == "ap":
            esito = await rete.applica_ban(bot, guild, self.a, interaction.user.id)
            chiave = {"ok": "rete_ban_applicato", "gia_deciso": "rete_ban_gia_deciso", "gerarchia": "rete_ban_gerarchia"}.get(esito, "rete_ban_fallito")
        elif self.az == "ri":
            chiave = "rete_ban_rifiutato" if await rete.rifiuta_proposta(self.a, guild.id, interaction.user.id) else "rete_ban_gia_deciso"
        else:
            chiave = "rete_ban_annullato" if await rete.annulla_ban(bot, guild, self.a, interaction.user.id) else "rete_ban_gia_deciso"
        await interaction.followup.send(await testo_per(interaction, chiave), ephemeral=True)


async def crea_vista(guild: discord.Guild, az: str, a: int, b: int) -> discord.ui.View:
    """La vista dei tasti per un avviso: «to» = togli timeout; «ap» = Banna e Ignora per una proposta."""
    vista = BaseView(timeout=None)  # controllo blacklist (SEC-10)
    azioni = ("ap", "ri") if az == "ap" else (az,)
    for azione in azioni:
        vista.add_item(BottoneRete(azione, a, b, await testo_guild(guild, _ETICHETTE[azione])))
    return vista

"""
core/verify_paese_staff.py
==========================
Paese nella verifica web (D53): valuta chi si verifica, mette in attesa quando troppe verifiche
vengono da fuori paese e chiede allo staff di approvare o rifiutare con due bottoni persistenti.
Mai un blocco automatico: il paese è un indizio, decide lo staff (come D50).
Impostazioni (punto unico: SETTINGS_SCHEMA e `core/config_impostazioni.py`): `verify_paesi`,
`verify_paesi_soglia`, `verify_paesi_minuti`, `verify_paesi_canale_id`.
Funzioni coperte: SPEC §4.2 (paese, D53)
Dipende da: core/geoip_paesi.py, core/repositories/verify_paese_repo.py
"""

from __future__ import annotations

import logging

import discord

from core import geoip_paesi
from core.command_access import Livello, puo_usare
from core.database import db
from core.i18n import testo_guild, testo_per
from core.repositories.verify_repo import verify_repo
from core.ui_base import BaseView
from core.verify_paese_logic import (
    MINUTI_DI_BASE,
    STATO_APPROVATA,
    STATO_ATTESA,
    STATO_OK,
    STATO_RIFIUTATA,
    leggi_paesi,
    tenere_in_attesa,
)

logger = logging.getLogger("iyokai.verify_paese")

SETTING_PAESI = "verify_paesi"
SETTING_SOGLIA = "verify_paesi_soglia"
SETTING_MINUTI = "verify_paesi_minuti"
SETTING_CANALE = "verify_paesi_canale_id"


def _repo():
    from core.repositories.verify_paese_repo import verify_paese_repo

    return verify_paese_repo


async def _canale_staff(guild: discord.Guild) -> discord.TextChannel | None:
    """Il canale scelto per questo avviso, altrimenti il canale del log della verifica."""
    scelto = await db.get_guild_setting(guild.id, SETTING_CANALE)
    if not scelto:
        scelto = (await verify_repo.get_config(guild.id)).log_channel_id
    canale = guild.get_channel(scelto) if scelto else None
    return canale if isinstance(canale, discord.TextChannel) else None


async def valuta(guild: discord.Guild, membro: discord.Member, ip: str) -> str | None:
    """
    Da chiamare durante la verifica web. Salva il codice del paese (mai l'IP). Restituisce il testo
    per il membro se va messo in attesa (la verifica NON prosegue), altrimenti None.
    """
    paesi = leggi_paesi(await db.get_guild_setting(guild.id, SETTING_PAESI))
    if not paesi:
        return None  # funzione non usata da questo server: non si raccoglie niente
    repo = _repo()
    # Lo stato deciso dallo staff vale prima del paese: un IP senza paese non apre la porta.
    prima = await repo.leggi(guild.id, membro.id)
    lingua = prima["lingua"] if prima else None
    if prima and prima["stato"] == STATO_ATTESA:
        return await testo_guild(guild, "verify_paese_attesa_utente")
    if prima and prima["stato"] == STATO_RIFIUTATA:
        return await testo_guild(guild, "verify_paese_rifiutata_utente")
    if prima and prima["stato"] == STATO_APPROVATA:
        return None
    paese = geoip_paesi.paese_da_ip(ip)
    if paese is None:
        return None
    soglia = await db.get_guild_setting(guild.id, SETTING_SOGLIA, 0) or 0
    minuti = await db.get_guild_setting(guild.id, SETTING_MINUTI, MINUTI_DI_BASE) or MINUTI_DI_BASE
    da_fuori = paese not in paesi
    canale = await _canale_staff(guild)
    fermare = False
    if da_fuori and soglia > 0 and canale is not None:  # senza nessuno da avvisare non si ferma in silenzio
        recenti = await repo.conta_da_fuori(guild.id, paesi, minuti, membro.id)
        fermare = tenere_in_attesa(True, recenti + 1, soglia)
    await repo.registra(guild.id, membro.id, paese, None, STATO_ATTESA if fermare else STATO_OK)
    if not fermare:
        return None
    try:
        await canale.send(
            embed=await _embed_avviso(guild, membro, paese, lingua, soglia, minuti),
            view=vista_decisione(guild.id, membro.id),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException:
        logger.warning("Avviso del paese non inviato nel server %s: la verifica prosegue.", guild.id)
        await repo.registra(guild.id, membro.id, paese, None, STATO_OK)
        return None
    return await testo_guild(guild, "verify_paese_attesa_utente")


async def _embed_avviso(guild, membro, paese, lingua, soglia, minuti) -> discord.Embed:
    return discord.Embed(
        title=await testo_guild(guild, "verify_paese_titolo"),
        description=(await testo_guild(
            guild, "verify_paese_descrizione", utente=membro.mention, id=membro.id, paese=paese,
            lingua=lingua or "-", soglia=soglia, minuti=minuti,
        ))[:4000],
        color=discord.Color.orange(),
    )


class BottoneDecisione(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"verifypaese:(?P<s>si|no):(?P<g>[0-9]+):(?P<u>[0-9]+)",
):
    def __init__(self, guild_id: int, user_id: int, approva: bool) -> None:
        super().__init__(
            discord.ui.Button(
                label="Approva" if approva else "Rifiuta",
                style=discord.ButtonStyle.success if approva else discord.ButtonStyle.danger,
                custom_id=f"verifypaese:{'si' if approva else 'no'}:{guild_id}:{user_id}",
            )
        )
        self.guild_id, self.user_id, self.approva = guild_id, user_id, approva

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["g"]), int(match["u"]), match["s"] == "si")

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.guild.id != self.guild_id:
            return
        await decidi(interaction, self.user_id, self.approva)


def vista_decisione(guild_id: int, user_id: int) -> BaseView:
    vista = BaseView(timeout=None)
    vista.add_item(BottoneDecisione(guild_id, user_id, True))
    vista.add_item(BottoneDecisione(guild_id, user_id, False))
    return vista


async def decidi(interaction: discord.Interaction, user_id: int, approva: bool) -> None:
    """Solo admin. Approva: stessi controlli e ruoli della verifica. Rifiuta: resta non verificato."""
    guild = interaction.guild
    if guild is None or not await puo_usare(interaction, Livello.ADMIN):
        await interaction.response.send_message(await testo_per(interaction, "verify_paese_solo_admin"), ephemeral=True)
        return
    if not await _repo().decidi(guild.id, user_id, STATO_APPROVATA if approva else STATO_RIFIUTATA):
        await interaction.response.send_message(await testo_per(interaction, "verify_paese_gia_deciso"), ephemeral=True)
        return
    await interaction.response.defer()
    esito = ""
    membro = guild.get_member(user_id)
    if approva and membro is None:
        esito = await testo_per(interaction, "verify_paese_membro_uscito")
    elif approva:
        cog = interaction.client.get_cog("VerifyCog")
        if cog is not None:
            risultato = await cog.run_checks_and_finalize(guild, membro, captcha_ok=True)
            if not risultato.success:
                esito = risultato.reason[:300]
    chiave = "verify_paese_approvata_da" if approva else "verify_paese_rifiutata_da"
    riga = await testo_per(interaction, chiave, staff=interaction.user.mention, utente=f"<@{user_id}>")
    try:
        base = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else discord.Embed()
        base.add_field(name="​", value=(riga + (f"\n{esito}" if esito else ""))[:1024], inline=False)
        base.color = discord.Color.green() if approva else discord.Color.red()
        await interaction.message.edit(embed=base, view=None, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        logger.warning("Messaggio del paese non aggiornato nel server %s.", guild.id)

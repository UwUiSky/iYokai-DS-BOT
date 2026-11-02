"""
core/verify_vpn_staff.py
========================
VPN e proxy nella verifica web (D64, D65): blocca subito chi si verifica da una VPN o un proxy, avvisa gli
admin nel canale del registro della verifica con il bottone persistente «Lascia passare» (solo admin), che
segna un'eccezione per quella persona e la ricorda nello storico condiviso (con founder e admin, D67). Se
almeno 3 server diversi (founder diversi, admin diversi, in momenti diversi) l'hanno già lasciata passare, qui
passa ma gli admin vedono «già accettato da N server» con lo storico (di base solo il numero; i nomi solo dei
server con `verify_condividi_nome`). Sotto la soglia il «Lascia passare» vale solo nel server che l'ha dato. Si salvano solo metodo, esito e data: mai l'IP.
Impostazioni (punto unico: SETTINGS_SCHEMA e `core/config_impostazioni.py`): `verify_blocca_vpn` (base vero),
`verify_condividi_nome` (base falso).
Funzioni coperte: SPEC §4.2 (VPN e proxy, D64, D65)
Dipende da: core/verify_vpn.py, core/repositories/verify_vpn_repo.py
"""

from __future__ import annotations

import logging

import discord

from core import verify_vpn
from core.command_access import Livello, puo_usare
from core.database import db
from core.i18n import testo_guild, testo_per
from core.repositories.verify_repo import verify_repo
from core.ui_base import BaseView
from core.verify_vpn_logic import storico_basta, testo_metodi

logger = logging.getLogger("iyokai.verify_vpn")

SETTING_BLOCCA = "verify_blocca_vpn"
SETTING_NOME = "verify_condividi_nome"
RIGHE_STORICO = 10


def _repo():
    from core.repositories.verify_vpn_repo import verify_vpn_repo

    return verify_vpn_repo


async def _canale_log(guild: discord.Guild) -> discord.TextChannel | None:
    scelto = (await verify_repo.get_config(guild.id)).log_channel_id
    canale = guild.get_channel(scelto) if scelto else None
    return canale if isinstance(canale, discord.TextChannel) else None


async def _nomi_metodi(guild: discord.Guild, metodi: str) -> str:
    voci = [m for m in metodi.split(",") if m]
    return ", ".join([await testo_guild(guild, f"verify_vpn_metodo_{m}") for m in voci])[:300] or "-"


async def controlla(
    bot, guild: discord.Guild, membro: discord.Member, ip: str, chiave: str,
    segnali_intestazioni: tuple[str, ...] = (), fuso: str | None = None,
) -> str | None:
    """
    Da chiamare all'inizio della verifica web. Restituisce il testo per la persona se va bloccata (la verifica
    NON prosegue), altrimenti None. Regola spenta o eccezione data: non si controlla niente.
    """
    if not await db.get_guild_setting(guild.id, SETTING_BLOCCA, True):
        return None
    repo = _repo()
    if await repo.ha_eccezione(guild.id, membro.id):
        return None
    esito = await verify_vpn.rileva(ip, segnali_intestazioni=segnali_intestazioni, fuso=fuso, chiave=chiave)
    if not esito.bloccato:
        return None
    metodi = testo_metodi(esito.metodi)
    precedenti = await repo.storico_altri(guild.id, membro.id)
    if precedenti and storico_basta(precedenti):  # D65+D67: abbastanza server diversi l'hanno già accettata
        from core.repositories.verify_vpn_repo import ESITO_DA_STORICO

        if await repo.registra_blocco(guild.id, membro.id, metodi, esito=ESITO_DA_STORICO):
            await _avvisa_storico(bot, guild, membro, metodi, precedenti)
        return None
    if await repo.registra_blocco(guild.id, membro.id, metodi):
        await _avvisa(guild, membro, metodi)
    return await testo_guild(guild, "verify_vpn_bloccato_utente")


async def _avvisa(guild: discord.Guild, membro: discord.Member, metodi: str) -> None:
    canale = await _canale_log(guild)
    if canale is None:
        return
    embed = discord.Embed(
        title=await testo_guild(guild, "verify_vpn_titolo"),
        description=(await testo_guild(
            guild, "verify_vpn_descrizione", utente=membro.mention, metodo=await _nomi_metodi(guild, metodi)
        ))[:4000],
        color=discord.Color.red(),
    )
    try:
        await canale.send(
            embed=embed,
            view=vista_eccezione(guild.id, membro.id, await testo_guild(guild, "verify_vpn_bottone_passa")),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException:
        logger.warning("Avviso VPN non inviato nel server %s: la persona resta bloccata.", guild.id)


async def _avvisa_storico(bot, guild: discord.Guild, membro: discord.Member, metodi: str, precedenti) -> None:
    canale = await _canale_log(guild)
    if canale is None:
        return
    server = {r["guild_id"] for r in precedenti}
    righe = []
    for r in list(precedenti)[:RIGHE_STORICO]:
        riga = await testo_guild(
            guild, "verify_vpn_storico_riga", data=r["creato_il"].date().isoformat(),
            metodo=await _nomi_metodi(guild, r["metodo"] or ""), esito=await testo_guild(guild, "verify_vpn_storico_esito"),
        )
        altro = bot.get_guild(r["guild_id"])
        if altro is not None and await db.get_guild_setting(altro.id, SETTING_NOME, False):
            riga += " · " + altro.name[:60]  # il nome solo se quel server ha dato il consenso
        righe.append(riga)
    testo = await testo_guild(
        guild, "verify_vpn_storico_descrizione", utente=membro.mention, metodo=await _nomi_metodi(guild, metodi), n=len(server)
    )
    embed = discord.Embed(
        title=await testo_guild(guild, "verify_vpn_storico_titolo"),
        description=(testo + "\n" + "\n".join(righe))[:4000],
        color=discord.Color.orange(),
    )
    try:
        await canale.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        logger.warning("Avviso dello storico VPN non inviato nel server %s.", guild.id)


class BottoneLasciaPassare(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"verifyvpn:ok:(?P<g>[0-9]+):(?P<u>[0-9]+)",
):
    def __init__(self, guild_id: int, user_id: int, etichetta: str = "") -> None:
        # L'etichetta conta solo all'invio; ricostruito da Discord al clic, il bottone non la mostra.
        super().__init__(
            discord.ui.Button(
                label=(etichetta or "Lascia passare")[:80],
                style=discord.ButtonStyle.success,
                custom_id=f"verifyvpn:ok:{guild_id}:{user_id}",
            )
        )
        self.guild_id, self.user_id = guild_id, user_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["g"]), int(match["u"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.guild.id != self.guild_id:
            return
        await lascia_passare(interaction, self.user_id)


def vista_eccezione(guild_id: int, user_id: int, etichetta: str = "") -> BaseView:
    vista = BaseView(timeout=None)
    vista.add_item(BottoneLasciaPassare(guild_id, user_id, etichetta))
    return vista


async def lascia_passare(interaction: discord.Interaction, user_id: int) -> None:
    """Solo admin. Segna l'eccezione per la persona in questo server e nello storico condiviso."""
    guild = interaction.guild
    if guild is None or not await puo_usare(interaction, Livello.ADMIN):
        await interaction.response.send_message(await testo_per(interaction, "verify_vpn_solo_admin"), ephemeral=True)
        return
    if not await _repo().lascia_passare(guild.id, user_id, founder_id=guild.owner_id, admin_id=interaction.user.id):
        await interaction.response.send_message(await testo_per(interaction, "verify_vpn_gia_passata"), ephemeral=True)
        return
    await interaction.response.defer()
    # il messaggio nel registro è pubblico: lingua del server, non di chi clicca
    riga = await testo_guild(guild, "verify_vpn_lasciato_da", staff=interaction.user.mention, utente=f"<@{user_id}>")
    try:
        base = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else discord.Embed()
        base.add_field(name="​", value=riga[:1024], inline=False)
        base.color = discord.Color.green()
        await interaction.message.edit(embed=base, view=None, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        logger.warning("Messaggio VPN non aggiornato nel server %s.", guild.id)


async def storico_owner(bot, user_id: int) -> list[dict]:
    """
    Solo per il proprietario del bot (D65): i server che hanno lasciato passare la persona, sempre con il
    nome. Lo stesso punto per `/owner system storico-vpn` e per la pagina del proprietario nel pannello.
    """
    voci = []
    for r in await _repo().storico_completo(user_id):
        server = bot.get_guild(r["guild_id"])
        voci.append({
            "data": r["creato_il"].date().isoformat(), "nome": server.name[:60] if server is not None else "?",
            "guild_id": r["guild_id"], "metodo": r["metodo"] or "-",
        })
    return voci


def righe_storico_owner(voci: list[dict]) -> list[str]:
    """Le voci di `storico_owner` come righe per Discord."""
    return [f"{v['data']} · **{v['nome']}** (`{v['guild_id']}`) · {v['metodo']} · lasciato passare" for v in voci]

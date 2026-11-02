"""
core/automod_decisioni.py
=========================
«Decide lo staff» (AMD-047): quando una regola ha l'azione `decide_staff`, le sanzioni non partono da sole.
Il bot scrive nel log AutoMod un riquadro con due bottoni persistenti, «Applica» e «Ignora». Le azioni leggere
(cancella, avviso, log) partono subito; le sanzioni aspettano la scelta di un moderatore.
Funzioni coperte: SPEC §6 (AMD-047), D63
"""

from __future__ import annotations

import logging
from typing import Any

import discord

from core import channel_router as router
from core.automod_regole_logic import Azione, azione_a_json, azione_da_json
from core.i18n import testo_guild, testo_per
from core.repositories.automod_decisioni_repo import automod_decisioni_repo

logger = logging.getLogger("iyokai.automod.decisioni")

# Le sanzioni che aspettano lo staff.
RINVIABILI = ("warn", "timeout", "mute_ruolo", "kick", "ban", "ban_tempo", "ruolo", "nickname")
MODELLO_ID = r"amdec:(?P<esito>ok|no):(?P<id>\d+)"
STATI = {"ok": "applicata", "no": "ignorata"}


class BottoneDecisione(discord.ui.DynamicItem[discord.ui.Button], template=MODELLO_ID):
    """Bottone Applica o Ignora. Il custom_id porta solo l'id della decisione: rispondono anche dopo un riavvio."""

    def __init__(self, esito: str, decisione_id: int, *, etichetta: str | None = None, disabled: bool = False) -> None:
        super().__init__(discord.ui.Button(
            label=(etichetta or ("Applica" if esito == "ok" else "Ignora"))[:45],
            style=discord.ButtonStyle.danger if esito == "ok" else discord.ButtonStyle.secondary,
            custom_id=f"amdec:{esito}:{decisione_id}", disabled=disabled))
        self.esito, self.decisione_id = esito, decisione_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):
        return cls(match["esito"], int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await decidi(interaction, self.decisione_id, self.esito)


def vista(decisione_id: int, *, disabled: bool = False, etichette: tuple[str, str] | None = None) -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    for esito, etichetta in zip(("ok", "no"), etichette or (None, None)):
        v.add_item(BottoneDecisione(esito, decisione_id, etichetta=etichetta, disabled=disabled))
    return v


async def chiedi_allo_staff(b: Any, rinviate: list[Azione]) -> bool:
    """Scrive la richiesta nel log AutoMod. True se è partita (le sanzioni restano in attesa)."""
    if b.membro is None or not rinviate:
        return False
    canale = await router.destinazione(b.guild, router.TIPO_AUTOMOD, getattr(b, "canale_log_id", None))
    if canale is None:
        return False  # nessun canale dove chiedere: meglio non sanzionare e non perdere niente senza dirlo
    estratto = (b.messaggio.content if b.messaggio is not None else "") or ""
    decisione_id = await automod_decisioni_repo.crea(
        b.guild.id, b.membro.id, b.regola_chiave, b.regola_nome, getattr(b.canale, "id", None), estratto,
        [azione_a_json(a) for a in rinviate])
    embed = discord.Embed(title=(await testo_guild(b.guild, "amdec_titolo", regola=b.regola_nome))[:256], color=discord.Color.orange())
    embed.add_field(name=await testo_guild(b.guild, "amdec_utente"), value=f"{b.membro.mention} ({b.membro.id})", inline=False)
    embed.add_field(name=await testo_guild(b.guild, "amdec_azioni"), value=", ".join(a.t for a in rinviate)[:1024], inline=False)
    if estratto:
        embed.add_field(name=await testo_guild(b.guild, "amdec_messaggio"), value=("`" + estratto[:500].replace("`", "'") + "`"), inline=False)
    etichette = (await testo_guild(b.guild, "amdec_applica"), await testo_guild(b.guild, "amdec_ignora"))
    try:
        messaggio = await canale.send(embed=embed, view=vista(decisione_id, etichette=etichette),
                                      allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        return False
    await automod_decisioni_repo.imposta_messaggio(decisione_id, messaggio.id)
    return True


async def _puo_applicare(interaction: discord.Interaction, decisione_id: int) -> bool:
    """«Applica» fa agire il bot al posto del moderatore: servono i permessi di ogni sanzione e un ruolo sopra la persona."""
    from core.automod_pannello_logic import permessi_mancanti

    riga = await automod_decisioni_repo.ottieni(decisione_id)
    if riga is None or riga["guild_id"] != interaction.guild.id:
        return True  # la decisione non c'è o è di un altro server: risponde «già deciso» più avanti
    staff, guild = interaction.user, interaction.guild
    if permessi_mancanti(tuple(azione_da_json(a) for a in riga["azioni"]), staff.guild_permissions):
        return False
    if staff.id == guild.owner_id:
        return True
    persona = guild.get_member(riga["user_id"])
    sopra = getattr(getattr(persona, "top_role", None), "position", 0)
    return persona is None or sopra == 0 or getattr(getattr(staff, "top_role", None), "position", 0) > sopra


async def decidi(interaction: discord.Interaction, decisione_id: int, esito: str) -> None:
    """Un moderatore preme un bottone: la decisione si chiude una volta sola, poi (se «Applica») partono le sanzioni."""
    from core.automod_azioni import Bersaglio, esegui_azioni

    guild = interaction.guild
    permessi = getattr(interaction.user, "guild_permissions", None)
    if guild is None or permessi is None or not (permessi.moderate_members or permessi.manage_guild):
        await interaction.response.send_message(await testo_per(interaction, "amdec_nessun_permesso"), ephemeral=True)
        return
    if esito == "ok" and not await _puo_applicare(interaction, decisione_id):
        await interaction.response.send_message(await testo_per(interaction, "amdec_nessun_permesso"), ephemeral=True)
        return
    riga = await automod_decisioni_repo.decidi(decisione_id, guild.id, STATI[esito], interaction.user.id)
    if riga is None:
        await interaction.response.send_message(await testo_per(interaction, "amdec_gia_deciso"), ephemeral=True)
        return
    await interaction.response.defer()
    fatte: tuple[str, ...] = ()
    if esito == "ok":
        membro = guild.get_member(riga["user_id"])
        if membro is not None:
            fatte = await esegui_azioni(
                tuple(azione_da_json(a) for a in riga["azioni"]),
                Bersaglio(guild=guild, motivo=riga["regola_nome"], regola_chiave=riga["regola_chiave"], regola_nome=riga["regola_nome"],
                          membro=membro, canale=guild.get_channel(riga["canale_id"]) if riga["canale_id"] else None))
    chiave = "amdec_applicata" if esito == "ok" else "amdec_ignorata"
    embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else discord.Embed()
    embed.set_footer(text=(await testo_per(interaction, chiave, staff=interaction.user.display_name, azioni=", ".join(fatte) or "-"))[:2000])
    try:
        await interaction.edit_original_response(embed=embed, view=vista(decisione_id, disabled=True))
    except discord.HTTPException:
        logger.info("AutoMod: riquadro della decisione %s non aggiornabile.", decisione_id)

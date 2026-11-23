"""
cogs/utility/giveaway_guidato.py
================================
`/admin-giveaway guidato`: crea un giveaway a passi (premio, durata e vincitori, canale, requisiti) con
riepilogo da confermare. Accanto resta `/admin-giveaway avvia` con tutte le opzioni. Il giveaway nasce solo
alla conferma, con gli stessi dati e lo stesso annuncio del comando.
Funzioni coperte: SPEC §15.5 (UTL-121; D124)
Dipende da: core/procedura_guidata.py, core/giveaway_guidato_logic.py
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord.ext import commands

from core import giveaway_guidato_logic as logica
from core.channel_access import PERMESSI_DI_SCRITTURA, motivo_se_il_bot_non_puo
from core.command_access import Livello, puo_usare
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.giveaway_logic import MAX_MESSAGGI_RICHIESTI, MAX_PREMIO_GIVEAWAY, embed_annuncio
from core.i18n import lingua_interazione, lingua_risposta, t, testo_per
from core.procedura_guidata import NESSUNA_MENZIONE, Passo, StatoProcedura, VistaGuidata
from core.repositories.giveaway_repo import giveaway_repo
from core.ui_base import BaseModal

logger = logging.getLogger("iyokai.giveaway_guidato")

MODULO_LIVELLI = "leveling"
TIPI_CANALE = [discord.ChannelType.text, discord.ChannelType.news]
PASSI = (
    Passo("giveaway_guidato_base", ("premio", "durata", "vincitori")),
    Passo("giveaway_guidato_canale", ("canale_id",)),
    Passo("giveaway_guidato_requisiti"),
)


async def permesso(interaction: discord.Interaction) -> str | None:
    """Riletto a ogni passo e alla conferma: serve ancora il livello admin e il modulo livelli acceso."""
    lingua = await lingua_interazione(interaction)
    if interaction.guild is None:
        return t("guidata_solo_server", lingua)
    if not await puo_usare(interaction, Livello.ADMIN):
        return t("guidata_permesso_perso", lingua)
    if not await db.is_module_active_for_guild(interaction.guild.id, MODULO_LIVELLI):
        return t("leveling_questo_modulo_non_attivo_su", lingua)
    return None


class ModaleBase(BaseModal):
    def __init__(self, vista: VistaGuidata) -> None:
        super().__init__(title=t("giveaway_guidato_base_titolo", vista.lingua)[:45], timeout=300)
        self.vista = vista
        d = vista.stato.dati
        self.premio = discord.ui.TextInput(
            label=t("giveaway_guidato_premio", vista.lingua)[:45], max_length=MAX_PREMIO_GIVEAWAY, default=d.get("premio")
        )
        self.durata = discord.ui.TextInput(
            label=t("giveaway_guidato_durata", vista.lingua)[:45], max_length=8, placeholder="90, 2h, 3d",
            default=str(d["durata"]) if d.get("durata") else None,
        )
        self.vincitori = discord.ui.TextInput(
            label=t("giveaway_guidato_vincitori", vista.lingua)[:45], max_length=2, required=False,
            default=str(d.get("vincitori") or 1),
        )
        for campo in (self.premio, self.durata, self.vincitori):
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.vista.autorizza(interaction):
            return
        dati, errore = logica.leggi_base(str(self.premio), str(self.durata), str(self.vincitori))
        if errore:
            await interaction.response.send_message(t(errore, self.vista.lingua), ephemeral=True)
            return
        self.vista.stato.dati.update(dati)
        await self.vista.aggiorna(interaction)


class ModaleRequisiti(BaseModal):
    def __init__(self, vista: VistaGuidata) -> None:
        super().__init__(title=t("giveaway_guidato_requisiti_titolo", vista.lingua)[:45], timeout=300)
        self.vista = vista
        d = vista.stato.dati
        self.livello = discord.ui.TextInput(
            label=t("giveaway_guidato_livello", vista.lingua)[:45], max_length=4, required=False, default=str(d.get("livello_min", 0))
        )
        self.messaggi = discord.ui.TextInput(
            label=t("giveaway_guidato_messaggi", vista.lingua)[:45], max_length=len(str(MAX_MESSAGGI_RICHIESTI)), required=False,
            default=str(d.get("messaggi_min", 0)),
        )
        self.add_item(self.livello)
        self.add_item(self.messaggi)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.vista.autorizza(interaction):
            return
        dati, errore = logica.leggi_requisiti(str(self.livello), str(self.messaggi))
        if errore:
            await interaction.response.send_message(t(errore, self.vista.lingua), ephemeral=True)
            return
        self.vista.stato.dati.update(dati)
        await self.vista.aggiorna(interaction)


def _bottone_modale(vista: VistaGuidata, etichetta: str, modale) -> discord.ui.Button:
    bottone = discord.ui.Button(label=etichetta[:80], style=discord.ButtonStyle.primary, row=0)

    async def premuto(interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(modale(vista))

    bottone.callback = premuto
    return bottone


def _costruisci_base(vista: VistaGuidata) -> list[discord.ui.Item]:
    return [_bottone_modale(vista, t("giveaway_guidato_scrivi", vista.lingua), ModaleBase)]


def _costruisci_canale(vista: VistaGuidata) -> list[discord.ui.Item]:
    attuale = vista.stato.dati.get("canale_id")
    scelta = discord.ui.ChannelSelect(
        channel_types=TIPI_CANALE, min_values=1, max_values=1, row=0,
        placeholder=t("giveaway_guidato_canale_scegli", vista.lingua)[:150],
        default_values=[discord.Object(id=attuale)] if attuale else [],
    )

    async def scelto(interaction: discord.Interaction) -> None:
        vista.stato.dati["canale_id"] = scelta.values[0].id
        await vista.aggiorna(interaction)

    scelta.callback = scelto
    return [scelta]


def _costruisci_requisiti(vista: VistaGuidata) -> list[discord.ui.Item]:
    attuale = vista.stato.dati.get("ruolo_id")
    ruolo = discord.ui.RoleSelect(
        min_values=0, max_values=1, row=0, placeholder=t("giveaway_guidato_ruolo_scegli", vista.lingua)[:150],
        default_values=[discord.Object(id=attuale)] if attuale else [],
    )

    async def scelto(interaction: discord.Interaction) -> None:
        vista.stato.dati["ruolo_id"] = ruolo.values[0].id if ruolo.values else None
        await vista.aggiorna(interaction)

    ruolo.callback = scelto
    return [ruolo, _bottone_modale(vista, t("giveaway_guidato_livello_messaggi", vista.lingua), ModaleRequisiti)]


def testo_riepilogo(dati: dict[str, Any], lingua: str) -> str:
    righe = [
        t("giveaway_guidato_r_premio", lingua, valore=str(dati.get("premio", ""))[:MAX_PREMIO_GIVEAWAY]),
        t("giveaway_guidato_r_durata", lingua, valore=logica.durata_leggibile(int(dati.get("durata", 0)))),
        t("giveaway_guidato_r_vincitori", lingua, valore=int(dati.get("vincitori", 1))),
        t("giveaway_guidato_r_canale", lingua, valore=f"<#{dati['canale_id']}>" if dati.get("canale_id") else "-"),
        t("giveaway_guidato_r_ruolo", lingua, valore=f"<@&{dati['ruolo_id']}>" if dati.get("ruolo_id") else "-"),
        t("giveaway_guidato_r_livello", lingua, valore=int(dati.get("livello_min", 0))),
        t("giveaway_guidato_r_messaggi", lingua, valore=int(dati.get("messaggi_min", 0))),
    ]
    return "\n".join(righe)


async def crea_giveaway(interaction: discord.Interaction, dati: dict[str, Any]) -> str:
    """La scrittura finale: ricontrolla permesso, canale e permessi del bot, poi crea e annuncia. ValueError = rifiuto."""
    lingua = await lingua_interazione(interaction)
    rifiuto = await permesso(interaction)
    if rifiuto is not None:
        raise ValueError(rifiuto)
    guild = interaction.guild
    canale = guild.get_channel(dati["canale_id"])
    if not isinstance(canale, (discord.TextChannel, discord.abc.GuildChannel)) or not hasattr(canale, "send"):
        raise ValueError(t("giveaway_guidato_canale_sparito", lingua))
    motivo = motivo_se_il_bot_non_puo(canale, guild.me, PERMESSI_DI_SCRITTURA)
    if motivo is not None:
        raise ValueError(t("giveaway_guidato_non_posso", lingua, motivo=motivo))
    ruolo = guild.get_role(dati["ruolo_id"]) if dati.get("ruolo_id") else None
    if dati.get("ruolo_id") and ruolo is None:
        raise ValueError(t("giveaway_guidato_ruolo_sparito", lingua))
    from cogs.leveling.leveling import LevelingCog

    scadenza = datetime.now(timezone.utc) + timedelta(minutes=dati["durata"])
    giveaway_id = await giveaway_repo.create_giveaway(
        guild.id, canale.id, dati["premio"], dati["vincitori"], dati.get("livello_min", 0),
        ruolo.id if ruolo else None, scadenza, interaction.user.id, min_messages=dati.get("messaggi_min", 0),
    )
    opzioni = await giveaway_repo.get_opzioni(guild.id)
    pubblica = await lingua_risposta(guild.id, pubblica=True)
    try:
        messaggio = await canale.send(
            embed=embed_annuncio(await giveaway_repo.get_giveaway(giveaway_id), opzioni, pubblica),
            view=LevelingCog.GiveawayEnterView(giveaway_id, opzioni), allowed_mentions=NESSUNA_MENZIONE,
        )
    except discord.HTTPException:
        await giveaway_repo.mark_ended(giveaway_id)  # senza annuncio nessuno può partecipare
        raise ValueError(t("giveaway_annuncio_non_inviato", lingua)) from None
    await giveaway_repo.set_message_id(giveaway_id, messaggio.id)
    return t("giveaway_guidato_creato", lingua, canale=canale.mention)


class GiveawayGuidatoCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "admin-giveaway",
        nome="guidato",
        descrizione="Crea un giveaway passo per passo: premio, durata, canale e requisiti.",
    )
    async def guidato(self, interaction: discord.Interaction) -> None:
        rifiuto = await permesso(interaction)
        if rifiuto is not None:
            await interaction.response.send_message(rifiuto, ephemeral=True)
            return
        lingua = await lingua_interazione(interaction)
        stato = StatoProcedura(interaction.user.id, PASSI, {"canale_id": interaction.channel_id, "vincitori": 1})
        vista = VistaGuidata(
            stato, titolo=t("giveaway_guidato_titolo", lingua), lingua=lingua, permesso=permesso,
            costruttori={
                "giveaway_guidato_base": _costruisci_base,
                "giveaway_guidato_canale": _costruisci_canale,
                "giveaway_guidato_requisiti": _costruisci_requisiti,
            },
            testi={p.chiave: (lambda v, c=p.chiave: t(f"{c}_testo", v.lingua)) for p in PASSI},
            riepilogo=lambda v: testo_riepilogo(v.stato.dati, v.lingua), conferma=crea_giveaway,
        )
        await interaction.response.send_message(embed=vista.embed(), view=vista, ephemeral=True)
        vista.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GiveawayGuidatoCog(bot))

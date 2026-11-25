"""
cogs/utility/setup_guidato.py
=============================
`/admin-bot setup guidato`: primo setup del bot o modifica di uno già fatto, a passi con riepilogo
(ruoli del bot, poi i moduli di ogni categoria). Niente è scritto finché non si conferma; alla conferma si
usano gli stessi punti unici dei comandi (`imposta_ruolo`, `imposta_modulo`).
Funzioni coperte: SPEC §2.2 (UTL-121; D124)
Dipende da: core/procedura_guidata.py, core/setup_guidato_logic.py, core/setup_wizard_logic.py
"""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord.ext import commands

from cogs.utility.setup import ETICHETTE_CATEGORIE
from core import setup_guidato_logic as logica
from core.config_schema import ImpostazioneNonValida
from core.command_access import Livello, TipoRuolo, errore_ruolo_bot, imposta_ruolo, leggi_ruolo, puo_usare, ruolo_valido_per_server
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config_schema import imposta_modulo
from core.database import db
from core.i18n import lingua_interazione, t
from core.premium import registry
from core.procedura_guidata import Passo, StatoProcedura, VistaGuidata
from core.setup_wizard_logic import MAX_MODULI_PER_PASSO, TIPO_MODULI, costruisci_passi

logger = logging.getLogger("iyokai.setup_guidato")

TESTI_RUOLI = {TipoRuolo.ADMIN: "setup_ruolo_admin", TipoRuolo.MOD: "setup_ruolo_mod", TipoRuolo.MODBAN: "setup_ruolo_modban"}
PASSO_RUOLI = "setup_guidato_ruoli"


async def permesso(interaction: discord.Interaction) -> str | None:
    """Riletto a ogni passo e alla conferma: serve il livello admin su questo server."""
    lingua = await lingua_interazione(interaction)
    if interaction.guild is None:
        return t("guidata_solo_server", lingua)
    if not await puo_usare(interaction, Livello.ADMIN):
        return t("guidata_permesso_perso", lingua)
    return None


def _passi_moduli(per_categoria: dict[str, list[str]]) -> tuple[Passo, ...]:
    """Un passo per categoria (diviso a pezzi da 25), con il nome della categoria come titolo."""
    passi = []
    for p in costruisci_passi(per_categoria, tuple(ETICHETTE_CATEGORIE))[1:]:
        nome = ETICHETTE_CATEGORIE.get(p.categoria, p.categoria)
        if p.parti > 1:
            nome += f" ({p.parte}/{p.parti})"
        passi.append(Passo(f"setup_guidato_mod:{p.categoria}:{p.parte}", titolo=nome))
    return tuple(passi)


def _nomi_del_passo(chiave: str, per_categoria: dict[str, list[str]]) -> list[str]:
    _, categoria, parte = chiave.split(":")
    inizio = (int(parte) - 1) * MAX_MODULI_PER_PASSO
    return per_categoria[categoria][inizio:inizio + MAX_MODULI_PER_PASSO]


def _costruisci_ruoli(vista: VistaGuidata) -> list[discord.ui.Item]:
    elementi = []
    guild = vista.contesto["guild"]
    for riga, tipo in enumerate(TESTI_RUOLI):
        attuale = vista.stato.dati["ruoli"].get(tipo.value)
        menu = discord.ui.RoleSelect(
            placeholder=t(TESTI_RUOLI[tipo], vista.lingua)[:150], min_values=0, max_values=1, row=riga,
            default_values=[discord.Object(id=attuale)] if attuale and guild.get_role(attuale) else [],
        )

        async def scelto(interaction: discord.Interaction, menu=menu, tipo=tipo) -> None:
            vista.stato.dati["ruoli"][tipo.value] = menu.values[0].id if menu.values else None
            await vista.aggiorna(interaction)

        menu.callback = scelto
        elementi.append(menu)
    return elementi


def _costruttore_moduli(chiave: str, per_categoria: dict[str, list[str]]):
    def costruisci(vista: VistaGuidata) -> list[discord.ui.Item]:
        nomi = _nomi_del_passo(chiave, per_categoria)
        scelti = vista.stato.dati["moduli"]
        menu = discord.ui.Select(
            placeholder=t("setup_wizard_scegli_moduli", vista.lingua)[:150], min_values=0, max_values=len(nomi), row=0,
            options=[
                discord.SelectOption(
                    label=vista.contesto["moduli"][n].display_name[:100], value=n,
                    description=(vista.contesto["moduli"][n].description or "")[:100] or None, default=scelti[n],
                )
                for n in nomi
            ],
        )

        async def scelto(interaction: discord.Interaction) -> None:
            for n in nomi:
                scelti[n] = n in menu.values
            await vista.aggiorna(interaction)

        menu.callback = scelto
        return [menu]

    return costruisci


def testo_riepilogo(dati: dict[str, Any], moduli: dict[str, Any], lingua: str) -> str:
    righe = []
    for tipo, nuovo in logica.ruoli_cambiati(dati["iniziali_ruoli"], dati["ruoli"]):
        ruolo = f"<@&{nuovo}>" if nuovo else t("setup_wizard_non_scelto", lingua)
        righe.append(t("setup_guidato_r_ruolo", lingua, nome=t(TESTI_RUOLI[TipoRuolo(tipo)], lingua), valore=ruolo))
    for nome, attivo in logica.moduli_cambiati(dati["iniziali_moduli"], dati["moduli"]):
        righe.append(t("setup_guidato_r_modulo_si" if attivo else "setup_guidato_r_modulo_no", lingua, nome=moduli[nome].display_name))
    return "\n".join(righe)[:3900] or t("setup_guidato_nessun_cambio", lingua)


async def scrivi_setup(interaction: discord.Interaction, dati: dict[str, Any]) -> str:
    """Alla conferma: permesso riletto, tutti i ruoli controllati PRIMA di scrivere, poi ruoli e moduli. ValueError = rifiuto."""
    lingua = await lingua_interazione(interaction)
    rifiuto = await permesso(interaction)
    if rifiuto is not None:
        raise ValueError(rifiuto)
    guild = interaction.guild
    autore = interaction.user if isinstance(interaction.user, discord.Member) else None
    ruoli = logica.ruoli_cambiati(dati["iniziali_ruoli"], dati["ruoli"])
    for tipo, nuovo in ruoli:
        if nuovo is not None and not ruolo_valido_per_server(guild, nuovo):
            raise ValueError(t("setup_guidato_ruolo_sparito", lingua))
        if errore_ruolo_bot(guild, TipoRuolo(tipo), autore, await leggi_ruolo(guild.id, TipoRuolo(tipo)), nuovo):
            chiave = "setup_guidato_admin_negato" if TipoRuolo(tipo) is TipoRuolo.ADMIN else "setup_guidato_ruolo_bot_negato"
            raise ValueError(t(chiave, lingua))
    for tipo, nuovo in ruoli:
        await imposta_ruolo(guild, TipoRuolo(tipo), guild.get_role(nuovo) if nuovo else None, interaction.user.id, autore=autore)
    cambiati = logica.moduli_cambiati(dati["iniziali_moduli"], dati["moduli"])
    for nome, attivo in cambiati:
        try:
            await imposta_modulo(interaction.client, guild.id, nome, attivo, interaction.user.id)
        except ImpostazioneNonValida:
            continue  # modulo di sicurezza senza il livello SECURITY: resta com'era
    return t("setup_guidato_fatto", lingua, ruoli=len(ruoli), moduli=len(cambiati))


class SetupGuidatoCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "admin-bot",
        nome="guidato",
        descrizione="Primo setup o modifica del setup, passo per passo e con riepilogo.",
        sottogruppo=("setup", "Attivazione dei moduli e configurazione guidata"),
    )
    async def guidato(self, interaction: discord.Interaction) -> None:
        rifiuto = await permesso(interaction)
        if rifiuto is not None:
            await interaction.response.send_message(rifiuto, ephemeral=True)
            return
        guild = interaction.guild
        await db.ensure_guild_exists(guild.id)
        per_categoria: dict[str, list[str]] = {}
        moduli = {}
        attuali: dict[str, bool] = {}
        for categoria in ETICHETTE_CATEGORIE:
            for m in registry.modules_in_category(categoria):
                per_categoria.setdefault(categoria, []).append(m.name)
                moduli[m.name] = m
                attuali[m.name] = await db.is_module_active_for_guild(guild.id, m.name)
        lingua = await lingua_interazione(interaction)
        if not moduli:
            await interaction.response.send_message(t("setup_wizard_vuoto", lingua), ephemeral=True)
            return
        ruoli = {tipo.value: await leggi_ruolo(guild.id, tipo) for tipo in TipoRuolo}
        modo = logica.modo_setup(ruoli, attuali)
        dati = {
            "ruoli": dict(ruoli), "moduli": dict(attuali), "iniziali_ruoli": dict(ruoli), "iniziali_moduli": dict(attuali),
        }
        passi_moduli = _passi_moduli(per_categoria)
        passi = (Passo(PASSO_RUOLI),) + passi_moduli
        costruttori = {PASSO_RUOLI: _costruisci_ruoli}
        testi = {PASSO_RUOLI: lambda v: t("setup_guidato_ruoli_testo", v.lingua)}
        for p in passi_moduli:
            costruttori[p.chiave] = _costruttore_moduli(p.chiave, per_categoria)
            testi[p.chiave] = lambda v, c=p.chiave: "\n".join(
                f"{'✅' if v.stato.dati['moduli'][n] else '❌'} **{v.contesto['moduli'][n].display_name}**"
                f" — {(v.contesto['moduli'][n].description or '')[:70]}" for n in _nomi_del_passo(c, per_categoria)
            )
        vista = VistaGuidata(
            StatoProcedura(interaction.user.id, passi, dati),
            titolo=t("setup_guidato_titolo_primo" if modo == logica.MODO_PRIMO else "setup_guidato_titolo_modifica", lingua),
            lingua=lingua, permesso=permesso, costruttori=costruttori, testi=testi,
            riepilogo=lambda v: testo_riepilogo(v.stato.dati, v.contesto["moduli"], v.lingua), conferma=scrivi_setup,
            contesto={"guild": guild, "moduli": moduli},
        )
        await interaction.response.send_message(embed=vista.embed(), view=vista, ephemeral=True)
        vista.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupGuidatoCog(bot))

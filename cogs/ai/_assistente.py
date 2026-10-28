"""
cogs/ai/_assistente.py
==================
Contorno della risposta di `-chiedi`: scoperta delle attività senza AI, voce
della base di conoscenza, stato di ogni comando citato, comandi vicini
spiegati, bottone «Attiva» per i moduli spenti, piano in più passi con
«Configura tutto» e traguardo del primo comando scoperto con l'AI.
Funzioni coperte: SPEC §25.12, §25.25, §25.28–§25.31, §25.34, §25.73, §25.101 (AI-R-006, AI-R-029..032, AI-R-036, AI-R-080, AI-R-108)

Un bot non può far partire un comando slash al posto della persona (D18): «Configura tutto»
accende i moduli che servono (stesso punto unico del pannello, solo per chi è admin) e mostra
i passi come comandi cliccabili. La conferma è il clic.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

import discord

from cogs.ai._comune import chiedi, taglia
from core import ai_ricerca_logic as logica
from core import command_search_logic as ricerca
from core.ai_servizio import RichiestaAI
from core.ai_testi_logic import riconosci_lingua
from core.command_access import Livello, puo_usare
from core.config_schema import imposta_modulo
from core.database import db
from core.premium import guild_has_premium_access, registry
from core.repositories.ai_repo import ai_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.ai_ricerca")

CODICE_TRAGUARDO = "primo_comando_ai"
TESTO_TRAGUARDO = "Traguardo sbloccato: primo comando scoperto con l'AI."


@dataclass
class Arricchimento:
    campi: list[tuple[str, str]] = field(default_factory=list)
    bottoni: list[discord.ui.Button] = field(default_factory=list)


# ---------------------------------------------------------------- strada senza AI
async def eventi_in_corso(guild_id: int | None) -> list[str]:
    """Eventi di gioco attivi nel server (boss, dungeon, misteri), per «cosa posso fare qui?»."""
    if guild_id is None:
        return []
    try:
        from core.repositories.ai_gioco_repo import ai_gioco_repo

        return await ai_gioco_repo.eventi_in_corso(guild_id)
    except Exception:
        logger.warning("Eventi in corso non letti.", exc_info=True)
        return []


async def voci_conoscenza(guild_id: int | None) -> list[tuple[str, str]]:
    if guild_id is None:
        return []
    try:
        return [(v["titolo"], v["testo"]) for v in await ai_repo.conoscenza_elenco(guild_id)]
    except Exception:
        logger.warning("Base di conoscenza non letta.", exc_info=True)
        return []


async def risposta_locale(
    interaction: discord.Interaction, domanda: str, comandi: Sequence[ricerca.ComandoInfo], guild_id: int | None
) -> bool:
    """
    Risponde da sola se basta una regola o il database: scoperta delle attività o voce della base
    di conoscenza. True se ha risposto. La ricerca evidente resta alla ricerca per parole.
    """
    voci = await voci_conoscenza(guild_id)
    decisione = logica.scegli_strada(domanda, comandi, voci)
    if decisione.strada is logica.Strada.SCOPERTA:
        testo = logica.elenco_scoperta(comandi, await eventi_in_corso(guild_id))
        titolo = "Cosa puoi fare qui"
    elif decisione.strada is logica.Strada.FAQ:
        testo, titolo = decisione.testo, "Dalla guida del server"
    else:
        return False
    await interaction.response.defer(ephemeral=True)
    embed = discord.Embed(title=titolo, description=taglia(testo), color=discord.Color.blurple())
    await interaction.followup.send(embed=embed, ephemeral=True)
    return True


# ---------------------------------------------------------------- stato dei comandi
async def contesto_comando(
    info: ricerca.ComandoInfo, guild_id: int | None, *, permesso: bool, bot=None
) -> logica.ContestoComando:
    mancanti, spenti, premium = [], [], False
    for modulo in info.moduli:
        if registry.get(modulo) is None:
            mancanti.append(modulo)
            continue
        if guild_id is None:
            continue
        if registry.is_module_premium(modulo) and not await guild_has_premium_access(guild_id, modulo, bot=bot):
            premium = True
        if not await db.is_module_active_for_guild(guild_id, modulo):
            spenti.append(modulo)
    configurato = False
    if guild_id is not None and info.gruppo == "ai" and not spenti:
        configurato = (await ai_repo.get_config(guild_id)).attivo
    return logica.ContestoComando(
        permesso=permesso, moduli_mancanti=tuple(mancanti), premium_bloccato=premium,
        moduli_spenti=tuple(spenti), configurato=configurato,
    )


async def stati_dei_comandi(
    infos: Sequence[ricerca.ComandoInfo], guild_id: int | None, percorsi_ok: set[str], bot=None
) -> dict[str, logica.StatoComando]:
    return {
        c.percorso: logica.stato_comando(await contesto_comando(c, guild_id, permesso=c.percorso in percorsi_ok, bot=bot))
        for c in infos
    }


async def moduli_spenti_per_ai(
    comandi: Sequence[ricerca.ComandoInfo], guild_id: int | None
) -> dict[str, str]:
    """percorso -> primo modulo spento, per avvisare l'AI (§25.29). Vuoto fuori da un server."""
    if guild_id is None:
        return {}
    attivi: dict[str, bool] = {}
    spenti: dict[str, str] = {}
    for c in comandi:
        for m in c.moduli:
            if m not in attivi:
                attivi[m] = await db.is_module_active_for_guild(guild_id, m)
            if not attivi[m]:
                spenti[c.percorso] = m
                break
    return spenti


# ---------------------------------------------------------------- bottoni
class _AttivaModulo(discord.ui.Button):
    def __init__(self, modulo: str) -> None:
        voce = registry.get(modulo)
        nome = getattr(voce, "display_name", modulo)
        super().__init__(label=f"Attiva «{nome}»"[:80], style=discord.ButtonStyle.success)
        self.modulo = modulo

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None or not await puo_usare(interaction, Livello.ADMIN):
            await interaction.response.send_message("Solo chi amministra il server può accendere un modulo.", ephemeral=True)
            return
        await imposta_modulo(interaction.client, interaction.guild_id, self.modulo, True, interaction.user.id)
        self.disabled = True
        await interaction.response.edit_message(view=self.view)
        await interaction.followup.send(f"Modulo «{self.modulo}» acceso.", ephemeral=True)


class _ConfiguraTutto(discord.ui.Button):
    def __init__(self, moduli: list[str], testo_passi: str) -> None:
        super().__init__(label="Configura tutto", style=discord.ButtonStyle.primary)
        self.moduli = moduli
        self.testo_passi = testo_passi

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None or not await puo_usare(interaction, Livello.ADMIN):
            await interaction.response.send_message("Solo chi amministra il server può configurare.", ephemeral=True)
            return
        acceso = []
        for modulo in self.moduli:
            if await imposta_modulo(interaction.client, interaction.guild_id, modulo, True, interaction.user.id):
                acceso.append(modulo)
        self.disabled = True
        await interaction.response.edit_message(view=self.view)
        intro = f"Moduli accesi: {', '.join(acceso)}.\n" if acceso else "I moduli necessari sono già accesi.\n"
        await interaction.followup.send(taglia(intro + "Ora lancia i passi, uno alla volta:\n" + self.testo_passi, 1900), ephemeral=True)


class AssistenteView(BaseView):
    def __init__(self, bottoni: Sequence[discord.ui.Button], timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        for b in bottoni:
            self.add_item(b)


# ---------------------------------------------------------------- arricchimento
async def piano_in_passi(
    interaction: discord.Interaction, domanda: str, comandi: Sequence[ricerca.ComandoInfo], guild_id: int | None
) -> list[logica.Passo]:
    risposta, _ = await chiedi(RichiestaAI(
        user_id=interaction.user.id, funzione="chiedi_piano", tipo="testo", testo=domanda,
        guild_id=guild_id, channel_id=interaction.channel_id, fascia="media", riusa=False,
        istruzioni=logica.ISTRUZIONI_PIANO + "\n\nComandi:\n" + logica.elenco_per_ai(comandi), lingua=riconosci_lingua(domanda),
    ))
    return logica.leggi_piano(risposta.testo, comandi) if risposta else []


async def arricchisci(
    interaction: discord.Interaction,
    domanda: str,
    citati: Sequence[ricerca.ComandoInfo],
    comandi_livelli: Sequence[ricerca.ComandoInfo],
    tutti: Sequence[ricerca.ComandoInfo],
    ids_di: Callable[[set[str]], Awaitable[dict[str, int]]],
    guild_id: int | None,
    lingua: str = "it",
) -> Arricchimento:
    """Stato, comandi vicini, attivazioni, piano e traguardo. Ogni pezzo che fallisce si salta: la risposta c'è già."""
    esito = Arricchimento()
    percorsi_ok = {c.percorso for c in comandi_livelli}
    per_percorso = {c.percorso: c for c in tutti}
    vicini: list[tuple[ricerca.ComandoInfo, str]] = []
    for c in citati:
        vicini += logica.vicini_di(c.percorso, per_percorso, gia_citati=[x.percorso for x in citati])
    vicini = vicini[:3]
    infos = list(citati) + [v for v, _ in vicini]
    try:
        stati = await stati_dei_comandi(infos, guild_id, percorsi_ok, bot=interaction.client)
        ids = await ids_di({c.gruppo for c in infos})
    except Exception:
        logger.warning("Stato dei comandi non letto.", exc_info=True)
        stati, ids = {}, {}

    def menzione(c: ricerca.ComandoInfo) -> str:
        return ricerca.menzione(c.percorso, ids)

    if citati and stati:
        esito.campi.append(("Stato", "\n".join(logica.riga_con_stato(menzione(c), stati[c.percorso]) for c in citati)))
    if vicini:
        esito.campi.append(("Alternative", logica.testo_vicini(
            [(f"{menzione(v)} ({stati[v.percorso].etichetta})" if stati else menzione(v), f) for v, f in vicini]
        )))
    if guild_id is not None and stati:
        for modulo in logica.moduli_da_proporre(stati[c.percorso] for c in citati):
            esito.bottoni.append(_AttivaModulo(modulo))
    if guild_id is not None and logica.richiesta_composta(domanda):
        passi = await piano_in_passi(interaction, domanda, comandi_livelli, guild_id)
        if passi:
            menzioni = {p.comando.percorso: menzione(p.comando) for p in passi}
            testo = logica.testo_piano(passi, menzioni)
            esito.campi.append(("Passi", taglia(testo, 1000)))
            moduli = logica.moduli_del_piano(passi, [m.name for m in registry.all_modules()])
            esito.bottoni.append(_ConfiguraTutto(moduli, testo))
    if citati:
        try:
            if await ai_repo.traguardo_assegna(interaction.user.id, CODICE_TRAGUARDO):
                esito.campi.append(("Traguardo", TESTO_TRAGUARDO))
        except Exception:
            logger.warning("Traguardo non assegnato.", exc_info=True)
    return esito

"""
cogs/ai/dungeon.py
==================
Dungeon di gruppo con scelte votate: l'admin avvia la partita in un canale, ognuno sceglie la classe,
poi a ogni stanza il gruppo vota con i bottoni (a tempo). La riuscita dipende da classi e livelli di chi
partecipa. La storia è un albero di stanze scritto dall'AI in anticipo, salvato nella libreria comune e
riusato in ogni server con lo stesso tema; l'AI scrive solo i rami che mancano. Con l'AI ferma c'è
una storia pronta.
Funzioni coperte: SPEC §25.53–§25.55, §25.99 (AI-R-058..060, AI-R-106)

I comandi stanno in `/ai dungeon` (D43): `/fun` ha già 25 figli. I bottoni sono di tutti.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.ai._comune import NESSUNA_MENZIONE, chiedi, registra_modulo_ai, taglia
from core import dungeon_logic as logica
from core.ai_servizio import RichiestaAI
from core.ai_testi_logic import estrai_json, testo_lore
from core.bot_ready import attendi_bot_pronto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.repositories.ai_gioco_repo import Partita, ai_gioco_repo
from core.repositories.ai_repo import ai_repo
from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.ai_dungeon")

SOTTO_DUNGEON = ("dungeon", "Dungeon di gruppo con scelte votate")
PREMIO_MONETE, PREMIO_XP, MAX_PREMIATI = 50, 30, 25
AGGIORNA: set[int] = set()
TOKEN_STORIA = 1800


# ---------------------------------------------------------------- storia: libreria, AI, riserva
async def tema_del_server(guild_id: int) -> tuple[str, str]:
    """(chiave del tema, testo della lore) del server; senza tema vale quello degli yokai."""
    cfg = await ai_repo.get_config(guild_id)
    return cfg.lore_tema or "yokai", testo_lore(cfg.lore_tema, cfg.lore_testo)


async def scegli_storia(guild_id: int, user_id: int, tema: str, lore: str):
    """(id, Storia). Libreria del tema (non giocata di recente) → AI → storia pronta. Salva ciò che l'AI scrive."""
    giocate = await ai_gioco_repo.storie_giocate(guild_id)
    trovata = await ai_gioco_repo.storia_trova(tema, giocate)
    if trovata is not None:
        storia = await ai_gioco_repo.storia_carica(trovata)
        if storia is not None and storia.nodo(storia.inizio) is not None:
            return trovata, storia
    risposta, _ = await chiedi(RichiestaAI(
        user_id=user_id, funzione="dungeon_storia", tipo="testo", testo=f"Tema: {tema}", guild_id=guild_id, fascia="media",
        istruzioni=logica.istruzioni_storia(lore), riusa=False, max_token=TOKEN_STORIA,
    ))
    nuova = logica.leggi_storia(risposta.testo) if risposta else None
    if nuova is not None:
        salvata = await ai_gioco_repo.storia_salva(tema, nuova)  # testo scritto dall'AI da zero: vale per ogni server
        if salvata is not None:
            return salvata, nuova
    pronta = logica.storia_pronta(tema)
    chiave = f"pronta_{tema}"
    salvata = await ai_gioco_repo.storia_salva(chiave, pronta) or await ai_gioco_repo.storia_trova(chiave)
    return salvata, pronta


async def scrivi_nodo(guild_id: int, user_id: int, lore: str, cronologia: list[str], id_nodo: str) -> tuple[logica.Nodo, bool]:
    """La stanza che manca (AI-R-059): (stanza, scritta dall'AI). Senza AI un finale pronto, che non va in libreria."""
    risposta, _ = await chiedi(RichiestaAI(
        user_id=user_id, funzione="dungeon_stanza", tipo="testo", guild_id=guild_id, fascia="media", riusa=False, max_token=700,
        testo="Cammino: " + (logica.riassunto_per_storia(cronologia) or "inizio"), istruzioni=logica.istruzioni_nodo(lore, cronologia),
        conta_utente=False,
    ))
    if risposta:
        nodo = logica.leggi_nodo(estrai_json(risposta.testo), id_forzato=id_nodo)
        if nodo is not None:
            return nodo, True
    return logica.nodo_finale_locale(id_nodo), False


# ---------------------------------------------------------------- aspetto
def embed_stanza(p: Partita, storia: logica.Storia, nodo: logica.Nodo, voti: list[int] | None = None, giocatori: int = 0) -> discord.Embed:
    embed = discord.Embed(title=taglia(storia.titolo, 256), description=taglia(nodo.testo, 3000), color=discord.Color.dark_purple())
    if not nodo.finale:
        righe = [f"{i + 1}. {s.testo}" + (f" ({voti[i]} voti)" if voti else "") for i, s in enumerate(nodo.scelte)]
        embed.add_field(name="Cosa fate?", value="\n".join(righe), inline=False)
        embed.set_footer(text=f"Votate entro {logica.SECONDI_VOTO} secondi. Giocatori: {giocatori}. Stanza {len(p.cronologia) + 1}.")
    return embed


def embed_lobby(storia: logica.Storia, tema: str, giocatori: dict[str, int]) -> discord.Embed:
    embed = discord.Embed(
        title=taglia(f"Dungeon: {storia.titolo}", 256), color=discord.Color.dark_purple(),
        description=f"Si parte tra {logica.SECONDI_LOBBY} secondi. Scegli la tua classe con un bottone.",
    )
    classi = ", ".join(f"{nome} ({prova})" for nome, prova in logica.classi_del_tema(tema))
    embed.add_field(name="Classi", value=classi, inline=False)
    if giocatori:
        embed.add_field(name="Nel gruppo", value=", ".join(f"{c}: {n}" for c, n in giocatori.items()), inline=False)
    return embed


# ---------------------------------------------------------------- bottoni
class _Bottone(discord.ui.Button):
    def __init__(self, custom_id: str, label: str, stile, indice: int, tipo: str) -> None:
        super().__init__(label=label[:80], style=stile, custom_id=custom_id)
        self.indice = indice
        self.tipo = tipo

    async def callback(self, interaction: discord.Interaction) -> None:
        await (scelta_classe if self.tipo == "classe" else voto)(interaction, self.indice)


class DungeonView(BaseView):
    """Senza argomenti: tutti i bottoni, registrati all'avvio per i messaggi vecchi. Con argomenti: quelli della fase."""

    def __init__(self, classi: list[str] | None = None, scelte: list[str] | None = None) -> None:
        super().__init__(timeout=None)
        if classi is None and scelte is None:
            classi = [f"Classe {i + 1}" for i in range(3)]
            scelte = [f"Scelta {i + 1}" for i in range(logica.MAX_SCELTE)]
            for i, nome in enumerate(classi):
                self.add_item(_Bottone(f"aidg:c{i}", nome, discord.ButtonStyle.secondary, i, "classe"))
            for i, nome in enumerate(scelte):
                self.add_item(_Bottone(f"aidg:v{i}", nome, discord.ButtonStyle.primary, i, "voto"))
            return
        for i, nome in enumerate(classi or []):
            self.add_item(_Bottone(f"aidg:c{i}", nome, discord.ButtonStyle.secondary, i, "classe"))
        for i, nome in enumerate(scelte or []):
            self.add_item(_Bottone(f"aidg:v{i}", nome, discord.ButtonStyle.primary, i, "voto"))


async def scelta_classe(interaction: discord.Interaction, indice: int) -> None:
    p = await ai_gioco_repo.partita_per_messaggio(interaction.message.id) if interaction.message else None
    if p is None or p.stato != "lobby":
        await interaction.response.send_message("La partita è già cominciata o è finita.", ephemeral=True)
        return
    tema, _ = await tema_del_server(p.guild_id)
    classi = logica.classi_del_tema(tema)
    if not 0 <= indice < len(classi):
        await interaction.response.send_message("Classe sconosciuta.", ephemeral=True)
        return
    await ai_gioco_repo.partita_giocatore(p.id, interaction.user.id, classi[indice][0])
    await interaction.response.send_message(f"Sei nel gruppo come {classi[indice][0]}.", ephemeral=True)
    AGGIORNA.add(p.id)


async def voto(interaction: discord.Interaction, indice: int) -> None:
    p = await ai_gioco_repo.partita_per_messaggio(interaction.message.id) if interaction.message else None
    if p is None or p.stato != "in_corso":
        await interaction.response.send_message("Il voto non è aperto.", ephemeral=True)
        return
    if not await ai_gioco_repo.partita_voto(p.id, interaction.user.id, indice):
        tema, _ = await tema_del_server(p.guild_id)
        await ai_gioco_repo.partita_giocatore(p.id, interaction.user.id, logica.classi_del_tema(tema)[0][0])  # arriva in corsa
        await ai_gioco_repo.partita_voto(p.id, interaction.user.id, indice)
    await interaction.response.send_message("Voto registrato: puoi cambiarlo finché il tempo non scade.", ephemeral=True)
    AGGIORNA.add(p.id)


# ---------------------------------------------------------------- andamento della partita
async def _carica(p: Partita):
    storia = await ai_gioco_repo.storia_carica(p.storia_id)
    return storia


async def _messaggio(bot: commands.Bot, p: Partita) -> discord.Message | None:
    canale = bot.get_channel(p.channel_id)
    if canale is None or p.message_id is None:
        return None
    try:
        return await canale.fetch_message(p.message_id)
    except discord.HTTPException:
        return None


async def aggiorna_messaggio(bot: commands.Bot, partita_id: int) -> None:
    """Ridisegna lobby o stanza con i voti contati (al più ogni 5 secondi)."""
    p = await ai_gioco_repo.partita(partita_id)
    if p is None or p.stato == "finita":
        return
    storia = await _carica(p)
    messaggio = await _messaggio(bot, p)
    if storia is None or messaggio is None:
        return
    giocatori = await ai_gioco_repo.partita_giocatori(p.id)
    tema, _ = await tema_del_server(p.guild_id)
    if p.stato == "lobby":
        conta: dict[str, int] = {}
        for _, classe, _ in giocatori:
            conta[classe] = conta.get(classe, 0) + 1
        await messaggio.edit(embed=embed_lobby(storia, tema, conta))
        return
    nodo = storia.nodo(p.nodo)
    voti = [sum(1 for _, _, v in giocatori if v == i) for i in range(len(nodo.scelte))] if nodo else None
    if nodo:
        await messaggio.edit(embed=embed_stanza(p, storia, nodo, voti, len(giocatori)))


async def _mostra_stanza(bot: commands.Bot, p: Partita, storia: logica.Storia, nodo: logica.Nodo, giocatori: int) -> None:
    messaggio = await _messaggio(bot, p)
    if messaggio is None:
        return
    vista = None if nodo.finale else DungeonView(scelte=[s.testo for s in nodo.scelte])
    await messaggio.edit(embed=embed_stanza(p, storia, nodo, None, giocatori), view=vista)


async def premia_gruppo(guild_id: int, user_ids: list[int]) -> int:
    """Monete e XP a chi ha giocato fino alla vittoria (piccoli e a tetto fisso), più un frammento da collezione."""
    tetto = (await leveling_settings_repo.get_config(guild_id)).impostazioni.max_level
    dati = 0
    for user_id in user_ids[:MAX_PREMIATI]:
        try:
            await leveling_repo.add_coins(guild_id, user_id, PREMIO_MONETE)
            await leveling_repo.modifica_xp(guild_id, user_id, "aggiungi", PREMIO_XP, tetto)
            await ai_gioco_repo.frammento_sblocca(guild_id, user_id, "dungeon")
            dati += 1
        except Exception:
            logger.warning("Premio del dungeon non assegnato a %s.", user_id, exc_info=True)
    return dati


async def avanza(bot: commands.Bot, p: Partita, rng=None) -> None:
    """Il tempo è scaduto: la lobby parte, oppure il voto si chiude e il gruppo passa alla stanza dopo (o alla fine)."""
    storia = await _carica(p)
    giocatori = await ai_gioco_repo.partita_giocatori(p.id)
    adesso = datetime.now(timezone.utc)
    if storia is None:
        await ai_gioco_repo.partita_chiudi(p.id, "annullata")
        return
    if p.stato == "lobby":
        if not giocatori:
            await ai_gioco_repo.partita_chiudi(p.id, "annullata")
            messaggio = await _messaggio(bot, p)
            if messaggio is not None:
                await messaggio.edit(content="Nessuno si è unito: il dungeon è annullato.", embed=None, view=None)
            return
        await ai_gioco_repo.partita_avanza(p.id, storia.inizio, adesso + timedelta(seconds=logica.SECONDI_VOTO), None)
        p = await ai_gioco_repo.partita(p.id)
        await _mostra_stanza(bot, p, storia, storia.nodo(storia.inizio), len(giocatori))
        return
    nodo = storia.nodo(p.nodo)
    if nodo is None or nodo.finale:
        await ai_gioco_repo.partita_chiudi(p.id, nodo.esito if nodo else "annullata")
        return
    tema, lore = await tema_del_server(p.guild_id)
    scelta_idx = logica.scelta_vincente({u: v for u, _, v in giocatori if v is not None}, len(nodo.scelte), rng)
    scelta = nodo.scelte[scelta_idx]
    livelli = {}
    for u, _, _ in giocatori:
        livelli[u] = (await leveling_repo.get_totals(p.guild_id, u)).level
    squadra = [(logica.prova_della_classe(tema, classe), livelli[u]) for u, classe, _ in giocatori]
    prob = logica.probabilita_successo(scelta.prova, scelta.difficolta, squadra)
    riuscita = logica.riesce(prob, rng)
    destinazione = scelta.successo if riuscita else scelta.fallimento
    traccia = f"{scelta.testo} ({'riuscita' if riuscita else 'fallita'})"
    prossimo = storia.nodo(destinazione)
    if len(p.cronologia) + 1 >= logica.MAX_STANZE and (prossimo is None or not prossimo.finale):
        prossimo = logica.nodo_finale_locale(destinazione, "neutro")  # la storia non si allunga all'infinito
    elif prossimo is None:
        prossimo, dall_ai = await scrivi_nodo(p.guild_id, giocatori[0][0] if giocatori else 0, lore, list(p.cronologia) + [traccia], destinazione)
        if dall_ai:
            await ai_gioco_repo.storia_nodo_salva(p.storia_id, prossimo)  # il ramo scritto resta nella libreria
    if prossimo.finale:
        await ai_gioco_repo.partita_avanza(p.id, prossimo.id, adesso + timedelta(minutes=5), traccia)
        await ai_gioco_repo.partita_chiudi(p.id, prossimo.esito)
        p = await ai_gioco_repo.partita(p.id)
        premiati = await premia_gruppo(p.guild_id, [u for u, _, _ in giocatori]) if prossimo.esito == "vittoria" else 0
        messaggio = await _messaggio(bot, p)
        if messaggio is not None:
            embed = embed_stanza(p, storia, prossimo)
            embed.add_field(name="Fine", value={"vittoria": "Vittoria!", "sconfitta": "Sconfitta.", "neutro": "Il gruppo torna a casa."}[prossimo.esito]
                            + (f" Premio a {premiati} giocatori." if premiati else ""), inline=False)
            await messaggio.edit(embed=embed, view=None)
        return
    await ai_gioco_repo.partita_avanza(p.id, prossimo.id, adesso + timedelta(seconds=logica.SECONDI_VOTO), traccia)
    p = await ai_gioco_repo.partita(p.id)
    await _mostra_stanza(bot, p, storia, prossimo, len(giocatori))


async def avvia_partita(bot: commands.Bot, guild: discord.Guild, canale: discord.TextChannel, user_id: int) -> tuple[int | None, str]:
    tema, lore = await tema_del_server(guild.id)
    storia_id, storia = await scegli_storia(guild.id, user_id, tema, lore)
    if storia_id is None:
        return None, "Non riesco a preparare una storia."
    scade = datetime.now(timezone.utc) + timedelta(seconds=logica.SECONDI_LOBBY)
    partita_id = await ai_gioco_repo.partita_crea(guild.id, canale.id, storia_id, storia.inizio, scade)
    if partita_id is None:
        return None, "In questo canale c'è già un dungeon."
    try:
        messaggio = await canale.send(
            embed=embed_lobby(storia, tema, {}), view=DungeonView(classi=[c for c, _ in logica.classi_del_tema(tema)], scelte=[]),
            allowed_mentions=NESSUNA_MENZIONE,
        )
    except discord.HTTPException:
        await ai_gioco_repo.partita_chiudi(partita_id, "annullata")
        return None, "Non riesco a scrivere in quel canale."
    await ai_gioco_repo.partita_imposta_messaggio(partita_id, messaggio.id)
    return partita_id, ""


class AiDungeonCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(DungeonView())
        self._ciclo.start()
        await super().cog_load()

    async def cog_unload(self) -> None:
        self._ciclo.cancel()
        await super().cog_unload()

    @tasks.loop(seconds=5)
    async def _ciclo(self) -> None:
        try:
            for partita_id in list(AGGIORNA):
                AGGIORNA.discard(partita_id)
                await aggiorna_messaggio(self.bot, partita_id)
            for p in await ai_gioco_repo.partite_scadute():
                try:
                    await avanza(self.bot, p)
                except Exception:
                    logger.warning("Dungeon %s non avanzato.", p.id, exc_info=True)
                    await ai_gioco_repo.partita_chiudi(p.id, "annullata")
        except Exception:
            logger.warning("Giro del dungeon non riuscito.", exc_info=True)

    @_ciclo.before_loop
    async def _prima(self) -> None:
        await attendi_bot_pronto(self.bot)

    @comando_di_gruppo("ai", nome="avvia", descrizione="Avvia un dungeon di gruppo in un canale.", sottogruppo=SOTTO_DUNGEON)
    @app_commands.describe(canale="Dove giocare (vuoto: questo canale)")
    async def dungeon_avvia(self, interaction: discord.Interaction, canale: discord.TextChannel | None = None) -> None:
        destinazione = canale or interaction.channel
        if not isinstance(destinazione, discord.TextChannel):
            await interaction.response.send_message("Scegli un canale di testo.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        partita_id, motivo = await avvia_partita(self.bot, interaction.guild, destinazione, interaction.user.id)
        await interaction.followup.send(f"Dungeon aperto in {destinazione.mention}." if partita_id else motivo, ephemeral=True)

    @comando_di_gruppo("ai", nome="storie", descrizione="Quante storie di dungeon ci sono pronte per il tema del server.", sottogruppo=SOTTO_DUNGEON)
    async def dungeon_storie(self, interaction: discord.Interaction) -> None:
        tema, _ = await tema_del_server(interaction.guild_id)
        n = await ai_gioco_repo.storie_conta(tema)
        await interaction.response.send_message(
            f"Per il tema «{tema}» ci sono {n} storie pronte, valide in ogni server con lo stesso tema. "
            "Se le hai già giocate tutte, l'AI ne scrive una nuova.", ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiDungeonCog(bot))

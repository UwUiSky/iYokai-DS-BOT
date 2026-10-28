"""
cogs/ai/riepilogo.py
====================
`/ai riepilogo imposta|anteprima`: ogni giorno o ogni settimana, a un'ora scelta, il bot pubblica nel canale scelto un
riepilogo fatto di numeri (attivi, canale vivace, messaggio più votato, clan cresciuto); l'AI ne scrive solo il tono e,
se l'admin lo chiede, riassume le discussioni dei canali scelti. `/utility ai avviso`: la persona segue fino a 3 parole
e riceve un avviso in privato quando se ne parla molto in un canale che vede. Funzionano anche con l'AI ferma.
Funzioni coperte: SPEC §25.41, §25.42, §25.43, §25.92 (AI-R-044, AI-R-045, AI-R-046, AI-R-099)
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.ai._comune import NESSUNA_MENZIONE, SOTTO_AI, chiedi, registra_modulo_ai, taglia, testo_canale
from core import riepilogo_logic as logica
from core.ai_servizio import RichiestaAI
from core.ai_testi_logic import testo_lore
from core.bot_ready import attendi_bot_pronto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.repositories.activity_stats_repo import activity_stats_repo
from core.repositories.ai_repo import ai_repo
from core.repositories.ai_riepilogo_repo import ConfigRiepilogo, ai_riepilogo_repo

logger = logging.getLogger("iyokai.ai_riepilogo")

SOTTO_RIEPILOGO = ("riepilogo", "Riepilogo del server a orario")
MESSAGGI_PER_CANALE = 80
SCADENZA_CACHE = 120.0


async def raccogli_numeri(guild_id: int, dal: datetime) -> logica.Numeri:
    giorno: date = dal.date()
    messaggi = sum((await activity_stats_repo.by_day(guild_id, giorno, "messages")).values())
    voce = sum((await activity_stats_repo.by_day(guild_id, giorno, "voice_minutes")).values())
    canali = await activity_stats_repo.top_channels(guild_id, giorno, "messages", 1)
    return logica.Numeri(
        messaggi=messaggi, minuti_voce=voce,
        attivi=tuple(await activity_stats_repo.top_members(guild_id, giorno, "messages", 3)),
        canale=canali[0] if canali else None,
        meme=await ai_riepilogo_repo.meme_top(guild_id, dal),
        clan=await ai_riepilogo_repo.clan_top(guild_id, dal),
    )


async def discussioni(guild: discord.Guild, cfg: ConfigRiepilogo) -> str | None:
    """Se l'admin l'ha chiesto: l'AI riassume le discussioni dei soli canali scelti. Niente viene salvato oltre al riepilogo."""
    if not cfg.con_testo or not cfg.canali_testo:
        return None
    pezzi: list[str] = []
    for canale_id in cfg.canali_testo[: logica.MAX_CANALI_TESTO]:
        canale = guild.get_channel(canale_id)
        if canale is None or not canale.permissions_for(guild.me).read_message_history:
            continue
        try:
            testo = await testo_canale(canale, MESSAGGI_PER_CANALE, max_caratteri=3000)
        except discord.HTTPException:
            continue
        if testo:
            pezzi.append(f"[#{canale.name}]\n{testo}")
    if not pezzi:
        return None
    risposta, _ = await chiedi(RichiestaAI(
        user_id=0, funzione="riepilogo_discussioni", tipo="testo", guild_id=guild.id, fascia="media",
        testo="\n\n".join(pezzi), istruzioni=logica.ISTRUZIONI_DISCUSSIONI, messaggi_utenti=True, riusa=False,
        max_token=400, conta_utente=False,
    ))
    return taglia(risposta.testo, 1000) if risposta and risposta.testo.strip() else None


async def componi_riepilogo(guild: discord.Guild, cfg: ConfigRiepilogo, adesso: datetime | None = None) -> tuple[str, str | None]:
    """(testo, discussioni): i numeri con il tono dell'AI se c'è, altrimenti i numeri soli."""
    adesso = adesso or datetime.now(timezone.utc)
    dal = adesso - timedelta(days=logica.giorni_del_periodo(cfg.frequenza))
    testo = logica.testo_numeri(await raccogli_numeri(guild.id, dal), cfg.frequenza, guild.id)
    ai_cfg = await ai_repo.get_config(guild.id)
    risposta, _ = await chiedi(RichiestaAI(
        user_id=0, funzione="riepilogo_tono", tipo="testo", guild_id=guild.id, fascia="bassa", testo=testo,
        istruzioni=logica.ISTRUZIONI_TONO + " Tema: " + (testo_lore(ai_cfg.lore_tema, ai_cfg.lore_testo) or "nessuno"),
        riusa=False, max_token=300, conta_utente=False,
    ))
    if risposta and risposta.testo.strip() and testo.count("<@") <= risposta.testo.count("<@"):
        testo = risposta.testo.strip()
    return taglia(testo, 3500), await discussioni(guild, cfg)


def embed_riepilogo(guild: discord.Guild, testo: str, parte: str | None, frequenza: str) -> discord.Embed:
    embed = discord.Embed(
        title=taglia(f"{'Settimana' if frequenza == 'settimana' else 'Giornata'} su {guild.name}", 256),
        description=testo, color=discord.Color.teal(),
    )
    if parte:
        embed.add_field(name="Di cosa si è parlato", value=parte, inline=False)
    embed.set_footer(text="Numeri dalle statistiche del server. Il tono può essere scritto dall'AI.")
    return embed


async def pubblica(guild: discord.Guild, cfg: ConfigRiepilogo) -> bool:
    canale = guild.get_channel(cfg.canale_id) if cfg.canale_id else None
    if canale is None:
        return False
    testo, parte = await componi_riepilogo(guild, cfg)
    try:
        await canale.send(embed=embed_riepilogo(guild, testo, parte, cfg.frequenza), allowed_mentions=NESSUNA_MENZIONE)
    except discord.HTTPException:
        logger.warning("Riepilogo non inviato nel server %s.", guild.id, exc_info=True)
        return False
    await ai_riepilogo_repo.salva_testo(guild.id, testo + (f"\n\nDi cosa si è parlato:\n{parte}" if parte else ""))
    return True


class AiRiepilogoCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.contatore = logica.ContatoreParole()
        self._cache: dict[int, tuple[float, dict[str, list[int]]]] = {}

    async def cog_load(self) -> None:
        await super().cog_load()
        self._ciclo.start()

    async def cog_unload(self) -> None:
        self._ciclo.cancel()
        await super().cog_unload()

    # ---------------------------------------------------------------- giro a orario
    @tasks.loop(seconds=60)
    async def _ciclo(self) -> None:
        adesso = datetime.now(timezone.utc)
        try:
            for cfg in await ai_riepilogo_repo.attivi():
                guild = self.bot.get_guild(cfg.guild_id)
                if guild is None or not logica.da_pubblicare(cfg.ora, cfg.frequenza, cfg.ultimo_invio, adesso):
                    continue
                if await ai_riepilogo_repo.prenota_invio(cfg.guild_id, adesso, logica.inizio_slot(cfg.ora, cfg.frequenza, adesso)):
                    await pubblica(guild, cfg)
        except Exception:
            logger.warning("Giro dei riepiloghi non riuscito.", exc_info=True)

    @_ciclo.before_loop
    async def _prima(self) -> None:
        await attendi_bot_pronto(self.bot)

    # ---------------------------------------------------------------- avvisi su parole
    async def _parole(self, guild_id: int) -> dict[str, list[int]]:
        ora = time.monotonic()
        voce = self._cache.get(guild_id)
        if voce and ora - voce[0] < SCADENZA_CACHE:
            return voce[1]
        parole: dict[str, list[int]] = {}
        try:
            if (await ai_repo.get_config(guild_id)).attivo:  # tutto parte spento: serve l'AI accesa dall'admin
                parole = await ai_riepilogo_repo.parole_del_server(guild_id)
        except Exception:
            logger.warning("Parole seguite non lette.", exc_info=True)
        self._cache[guild_id] = (ora, parole)
        return parole

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or not message.content:
            return
        parole = await self._parole(message.guild.id)
        if not parole:
            return
        adesso = datetime.now(timezone.utc)
        for parola in logica.parole_nel_testo(message.content, set(parole)):
            if not self.contatore.conta(message.channel.id, parola, adesso):
                continue
            for user_id in parole[parola]:
                membro = message.guild.get_member(user_id)
                if membro is None or membro.id == message.author.id:
                    continue
                if not message.channel.permissions_for(membro).view_channel:
                    continue  # mai per canali che la persona non vede
                if self.contatore.da_avvisare(message.channel.id, parola, user_id, adesso):
                    try:
                        await membro.send(f"Si parla molto di «{parola}» in {message.channel.mention} ({message.guild.name}): {message.jump_url}", allowed_mentions=NESSUNA_MENZIONE)
                    except discord.HTTPException:
                        pass

    # ---------------------------------------------------------------- comandi
    @comando_di_gruppo("ai", nome="imposta", descrizione="Riepilogo del server: canale, ora, frequenza e canali da leggere.", sottogruppo=SOTTO_RIEPILOGO)
    @app_commands.describe(
        attivo="Sì: pubblica il riepilogo. No: spento", canale="Dove pubblicarlo", ora="Ora di pubblicazione (fuso di Roma)",
        frequenza="Ogni giorno o ogni lunedì", leggi_canale="Aggiunge o toglie un canale da cui l'AI riassume le discussioni",
    )
    @app_commands.choices(frequenza=[app_commands.Choice(name=f, value=f) for f in logica.FREQUENZE])
    async def riepilogo_imposta(
        self, interaction: discord.Interaction, attivo: bool | None = None, canale: discord.TextChannel | None = None,
        ora: app_commands.Range[int, 0, 23] | None = None, frequenza: str | None = None, leggi_canale: discord.TextChannel | None = None,
    ) -> None:
        campi: dict = {k: v for k, v in {"attivo": attivo, "canale_id": canale.id if canale else None, "ora": ora, "frequenza": frequenza}.items() if v is not None}
        if leggi_canale is not None:
            attuali = list((await ai_riepilogo_repo.config(interaction.guild_id)).canali_testo)
            if leggi_canale.id in attuali:
                attuali.remove(leggi_canale.id)
            elif len(attuali) >= logica.MAX_CANALI_TESTO:
                await interaction.response.send_message(f"Al massimo {logica.MAX_CANALI_TESTO} canali.", ephemeral=True)
                return
            else:
                attuali.append(leggi_canale.id)
            campi.update(canali_testo=attuali, con_testo=bool(attuali))
        if campi:
            await ai_riepilogo_repo.imposta(interaction.guild_id, **campi)
        c = await ai_riepilogo_repo.config(interaction.guild_id)
        testo = (
            f"Riepilogo {'acceso' if c.attivo else 'spento'}: {c.frequenza}, alle {c.ora}:00, "
            f"{f'in <#{c.canale_id}>' if c.canale_id else 'canale non scelto'}."
            + (f" L'AI legge i messaggi di: {', '.join(f'<#{x}>' for x in c.canali_testo)}." if c.canali_testo else " Solo numeri: nessun messaggio viene letto.")
        )
        await interaction.response.send_message(testo, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("ai", nome="anteprima", descrizione="Mostra a te il riepilogo di adesso, senza pubblicarlo.", sottogruppo=SOTTO_RIEPILOGO)
    async def riepilogo_anteprima(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        cfg = await ai_riepilogo_repo.config(interaction.guild_id)
        testo, parte = await componi_riepilogo(interaction.guild, cfg)
        await interaction.followup.send(embed=embed_riepilogo(interaction.guild, testo, parte, cfg.frequenza), ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("utility", nome="avviso", descrizione="Segui fino a 3 parole: ti avviso quando se ne parla molto.", sottogruppo=SOTTO_AI)
    @app_commands.describe(azione="Cosa fare", parola="La parola (per aggiungi e togli)")
    @app_commands.choices(azione=[app_commands.Choice(name=n, value=n) for n in ("aggiungi", "togli", "elenco")])
    async def avviso(self, interaction: discord.Interaction, azione: str, parola: app_commands.Range[str, 2, 30] | None = None) -> None:
        g, u = interaction.guild_id, interaction.user.id
        if g is None:
            await interaction.response.send_message("Si usa dentro un server.", ephemeral=True)
            return
        if azione == "elenco" or parola is None:
            elenco = await ai_riepilogo_repo.parole_di(g, u)
            await interaction.response.send_message("Segui: " + (", ".join(elenco) if elenco else "nessuna parola."), ephemeral=True)
            return
        pulita = logica.parola_valida(parola)
        if pulita is None:
            await interaction.response.send_message("Scrivi una parola o due, senza simboli.", ephemeral=True)
            return
        if azione == "togli":
            fatto = await ai_riepilogo_repo.parole_togli(g, u, pulita)
            esito = "Parola tolta." if fatto else "Non la stavi seguendo."
        else:
            r = await ai_riepilogo_repo.parole_aggiungi(g, u, pulita, logica.MAX_PAROLE)
            esito = {"ok": f"Ti avviserò in privato quando se ne parla molto in un canale che vedi. Solo se l'AI è accesa nel server.",
                     "gia": "La segui già.", "piene": f"Puoi seguire al massimo {logica.MAX_PAROLE} parole: toglie prima una."}[r]
        self._cache.pop(g, None)
        await interaction.response.send_message(esito, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    await bot.add_cog(AiRiepilogoCog(bot))

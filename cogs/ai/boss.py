"""
cogs/ai/boss.py
===============
World Boss: un mostro compare in un canale (a orario o a mano) e il gruppo lo combatte con i bottoni
attacco, magia (costa monete), difesa e cura. Vita secondo i membri attivi, danno secondo il livello,
mostro scritto dall'AI secondo la lore (o pronto, con l'AI ferma), immagine disegnata con Pillow,
premi con tetti, boss di rete pubblicato dall'owner (solo totali in comune).
Funzioni coperte: SPEC §25.49–§25.52, §25.59, §25.64, §25.70 (AI-R-054..057, AI-R-064, AI-R-070, AI-R-077)

I comandi stanno in `/ai boss` (D43): `/fun` ha già 25 figli. I bottoni dell'evento sono di tutti.
"""

from __future__ import annotations

import io
import logging
import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.ai._comune import NESSUNA_MENZIONE, chiedi, registra_modulo_ai, taglia
from core import boss_logic as logica
from core.ai_servizio import RichiestaAI
from core.bot_ready import attendi_bot_pronto
from core.boss_image import disegna_boss
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.config import config
from core.repositories.activity_stats_repo import activity_stats_repo
from core.repositories.ai_gioco_repo import BossConfig, BossEvento, ai_gioco_repo
from core.repositories.ai_repo import ai_repo
from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.role_safety import check_role_assignable
from core.safe_image import run_image_task
from core.scheduler import scheduler
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.ai_boss")

SOTTO_BOSS = ("boss", "World Boss: evento di gruppo contro un mostro")
AZIONE_RUOLO = "ai_boss_ruolo"
MAX_PREMIATI = 200
MAX_RUOLI_PREMIO = 50
FRASE_FINE = {"sconfitto": "Il mostro è stato sconfitto!", "fuggito": "Il mostro è fuggito prima di essere sconfitto."}


# ---------------------------------------------------------------- scelta del mostro
async def scegli_mostro(guild_id: int, cfg: BossConfig, tema: str | None, rng: random.Random | None = None):
    """(mostro, id boss di rete, vita extra). Rete → AI secondo la lore → libreria → mostri pronti."""
    rng = rng or random
    if cfg.rete:
        rete = await ai_gioco_repo.rete_attiva()
        if rete is not None:
            return rete[1], rete[0], rete[2]
    tema_chiave = tema or "yokai"
    in_libreria = await ai_gioco_repo.mostro_libreria(tema_chiave)
    if in_libreria is not None and rng.random() < 0.5:  # si salva per riusare: metà delle volte basta la libreria
        return in_libreria, None, 0
    ai_cfg = await ai_repo.get_config(guild_id)
    risposta, _ = await chiedi(RichiestaAI(
        user_id=0, funzione="boss_mostro", tipo="testo", testo=f"Tema: {tema_chiave}", guild_id=guild_id,
        istruzioni=logica.ISTRUZIONI_MOSTRO, riusa=False, conta_utente=False, max_token=300,
    )) if ai_cfg.attivo else (None, None)
    nuovo = logica.leggi_mostro(risposta.testo) if risposta else None
    if nuovo is not None:
        if not nuovo.frasi:
            nuovo = logica.Mostro(nuovo.nome, nuovo.aspetto, logica.mostro_pronto(tema_chiave, rng).frasi)
        await ai_gioco_repo.mostro_salva(tema_chiave, nuovo)  # testo scritto dall'AI da zero: vale per ogni server
        return nuovo, None, 0
    return in_libreria or logica.mostro_pronto(tema_chiave, rng), None, 0


async def membri_attivi(guild_id: int) -> int:
    """Membri con almeno un messaggio negli ultimi 7 giorni (statistiche di attività, AI-R-057)."""
    try:
        oggi = datetime.now(timezone.utc).date()
        return len(await activity_stats_repo.members_over(guild_id, oggi - timedelta(days=7), "messages", 1))
    except Exception:
        logger.warning("Membri attivi non letti.", exc_info=True)
        return 0


# ---------------------------------------------------------------- aspetto del messaggio
def embed_boss(ev: BossEvento, *, fine: str | None = None, classifica: list[tuple[int, int]] | None = None, extra: str = "") -> discord.Embed:
    colore = discord.Color.red() if fine is None else (discord.Color.green() if fine == "sconfitto" else discord.Color.dark_grey())
    embed = discord.Embed(title=taglia(f"World Boss: {ev.nome}", 256), color=colore)
    frase = random.choice(ev.frasi) if ev.frasi and fine is None else ""
    embed.description = taglia("\n".join(x for x in (ev.aspetto, f"*{frase}*" if frase else "", FRASE_FINE.get(fine or "", "")) if x), 1500)
    embed.add_field(name="Vita", value=f"`{logica.barra_vita(ev.vita, ev.vita_max)}` {ev.vita}/{ev.vita_max}", inline=False)
    if classifica:
        righe = [f"{i}. <@{u}>: {d} danni" for i, (u, d) in enumerate(classifica[:5], 1)]
        embed.add_field(name="Chi ha colpito di più", value="\n".join(righe), inline=False)
    if extra:
        embed.add_field(name="Premi", value=taglia(extra, 1000), inline=False)
    if fine is None:
        embed.set_footer(text=f"Attacco, magia ({logica.COSTO_MAGIA} monete), difesa o cura. Ogni {logica.RITMO_CONTRATTACCO} azioni il boss colpisce.")
    embed.set_image(url="attachment://boss.png")
    return embed


# ---------------------------------------------------------------- premi
async def assegna_premi(guild: discord.Guild, ev: BossEvento, cfg: BossConfig) -> str:
    """Monete e XP a chi ha colpito (con tetti), un frammento da collezione e, se scelto, un ruolo a tempo (AI-R-077)."""
    partecipanti = await ai_gioco_repo.boss_partecipanti(ev.id, MAX_PREMIATI)
    totale = sum(d for _, d in partecipanti)
    tetto = (await leveling_settings_repo.get_config(guild.id)).impostazioni.max_level
    monete = xp = 0
    ruolo = guild.get_role(cfg.ruolo_premio_id) if cfg.ruolo_premio_id else None
    ruoli_dati = 0
    for posizione, (user_id, danno) in enumerate(partecipanti):
        p = logica.premio(danno, totale, len(partecipanti))
        try:
            if p.monete:
                await leveling_repo.add_coins(guild.id, user_id, p.monete)
            if p.xp:
                await leveling_repo.modifica_xp(guild.id, user_id, "aggiungi", p.xp, tetto)
            await ai_gioco_repo.frammento_sblocca(guild.id, user_id, "trofeo_boss")
        except Exception:
            logger.warning("Premio del boss non assegnato a %s.", user_id, exc_info=True)
            continue
        monete, xp = monete + p.monete, xp + p.xp
        if ruolo is not None and posizione < MAX_RUOLI_PREMIO and await _dai_ruolo(guild, ruolo, user_id, cfg.ruolo_premio_ore):
            ruoli_dati += 1
    righe = [f"{len(partecipanti)} partecipanti: {monete} monete e {xp} XP in totale (tetto a persona: {logica.PREMIO_MONETE_MAX} monete, {logica.PREMIO_XP_MAX} XP)."]
    if ruoli_dati:
        righe.append(f"Ruolo {ruolo.mention} per {cfg.ruolo_premio_ore} ore ai {ruoli_dati} che hanno colpito di più.")
    return "\n".join(righe)


async def _dai_ruolo(guild: discord.Guild, ruolo: discord.Role, user_id: int, ore: int) -> bool:
    membro = guild.get_member(user_id)
    if membro is None or check_role_assignable(guild, ruolo, guild.me, self_service=True) is not None:
        return False
    try:
        await membro.add_roles(ruolo, reason="Premio del World Boss")
        await scheduler.schedule(guild.id, user_id, AZIONE_RUOLO, datetime.now(timezone.utc) + timedelta(hours=ore), {"role_id": ruolo.id})
    except discord.HTTPException:
        return False
    return True


# ---------------------------------------------------------------- evento
class BossView(BaseView):
    """Bottoni persistenti: l'evento si riconosce dal messaggio che li porta."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def _azione(self, interaction: discord.Interaction, azione: str) -> None:
        ev = await ai_gioco_repo.boss_per_messaggio(interaction.message.id) if interaction.message else None
        if ev is None or ev.stato != "attivo":
            await interaction.response.send_message("Questo evento è finito.", ephemeral=True)
            return
        livello = (await leveling_repo.get_totals(ev.guild_id, interaction.user.id)).level
        danno = logica.danno_attacco(livello) if azione == "attacco" else logica.danno_magia(livello) if azione == "magia" else 0
        pagata = False
        if azione == "magia":
            if not await leveling_repo.spend_coins(ev.guild_id, interaction.user.id, logica.COSTO_MAGIA):
                await interaction.response.send_message(f"Servono {logica.COSTO_MAGIA} monete per la magia.", ephemeral=True)
                return
            pagata = True
        esito = await ai_gioco_repo.boss_agisci(ev.id, interaction.user.id, azione, danno, logica.ATTESA_AZIONE_SECONDI)
        if esito.stato != "ok":
            if pagata:
                await leveling_repo.add_coins(ev.guild_id, interaction.user.id, logica.COSTO_MAGIA)
            testo = {
                "chiuso": "Questo evento è finito.",
                "attesa": f"Riprendi fiato: aspetta ancora {esito.secondi} secondi.",
                "ferito": f"Sei ferito: puoi solo curarti. Ancora {esito.secondi} secondi.",
            }[esito.stato]
            await interaction.response.send_message(testo, ephemeral=True)
            return
        if azione in ("attacco", "magia"):
            testo = f"Hai inflitto {esito.danno} danni! Vita del mostro: {esito.vita}/{ev.vita_max}."
        elif azione == "difesa":
            testo = "Ti metti in guardia: eviterai il prossimo colpo del mostro."
        else:
            testo = "Ti sei curato: puoi di nuovo colpire."
        if esito.contrattacco:
            testo += f"\nIl mostro ha colpito {esito.contrattacco} persone senza guardia!"
        await interaction.response.send_message(testo, ephemeral=True)
        AGGIORNA.add(ev.id)
        if esito.sconfitto:
            await chiudi_evento(interaction.client, ev.id, "sconfitto")

    @discord.ui.button(label="Attacco", style=discord.ButtonStyle.danger, custom_id="aiboss:attacco")
    async def attacco(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._azione(interaction, "attacco")

    @discord.ui.button(label="Magia", style=discord.ButtonStyle.primary, custom_id="aiboss:magia")
    async def magia(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._azione(interaction, "magia")

    @discord.ui.button(label="Difesa", style=discord.ButtonStyle.secondary, custom_id="aiboss:difesa")
    async def difesa(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._azione(interaction, "difesa")

    @discord.ui.button(label="Cura", style=discord.ButtonStyle.success, custom_id="aiboss:cura")
    async def cura(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._azione(interaction, "cura")


AGGIORNA: set[int] = set()  # eventi da ridisegnare al prossimo giro (al più ogni pochi secondi)


async def _messaggio(bot: commands.Bot, ev: BossEvento) -> discord.Message | None:
    canale = bot.get_channel(ev.channel_id)
    if canale is None or ev.message_id is None:
        return None
    try:
        return await canale.fetch_message(ev.message_id)
    except discord.HTTPException:
        return None


async def aggiorna_messaggio(bot: commands.Bot, ev_id: int) -> None:
    ev = await ai_gioco_repo.boss_evento(ev_id)
    if ev is None or ev.stato != "attivo":
        return
    messaggio = await _messaggio(bot, ev)
    if messaggio is not None:
        await messaggio.edit(embed=embed_boss(ev, classifica=await ai_gioco_repo.boss_partecipanti(ev.id, 5)))


async def chiudi_evento(bot: commands.Bot, ev_id: int, stato: str) -> None:
    """Fine dell'evento (sconfitto o fuggito): messaggio finale, premi solo se sconfitto, totali del boss di rete."""
    ev = await ai_gioco_repo.boss_evento(ev_id)
    if ev is None:
        return
    if stato == "fuggito" and not await ai_gioco_repo.boss_chiudi(ev_id, "fuggito"):
        return  # già chiuso da qualcun altro
    ev = await ai_gioco_repo.boss_evento(ev_id)
    guild = bot.get_guild(ev.guild_id)
    cfg = await ai_gioco_repo.boss_config(ev.guild_id)
    premi = ""
    if stato == "sconfitto" and guild is not None:
        premi = await assegna_premi(guild, ev, cfg)
    classifica = await ai_gioco_repo.boss_partecipanti(ev.id, 5)
    if ev.rete_id is not None:
        tutti = await ai_gioco_repo.boss_partecipanti(ev.id, MAX_PREMIATI)
        await ai_gioco_repo.rete_aggiungi_totali(ev.rete_id, ev.guild_id, sum(d for _, d in tutti), len(tutti), stato == "sconfitto")
        d, s, p, v = await ai_gioco_repo.rete_totali(ev.rete_id)
        premi += f"\nIn tutta la rete: {d} danni da {p} persone in {s} server ({v} lo hanno sconfitto)."
    messaggio = await _messaggio(bot, ev)
    if messaggio is not None:
        try:
            await messaggio.edit(embed=embed_boss(ev, fine=stato, classifica=classifica, extra=premi), view=None)
        except discord.HTTPException:
            logger.info("Messaggio finale del boss non modificato (%s).", ev.id)


async def avvia_evento(
    bot: commands.Bot, guild: discord.Guild, canale: discord.TextChannel, cfg: BossConfig, rng: random.Random | None = None
) -> tuple[int | None, str]:
    """Fa comparire il boss nel canale. (id, "") oppure (None, motivo)."""
    ai_cfg = await ai_repo.get_config(guild.id)
    tema = ai_cfg.lore_tema
    mostro, rete_id, vita_extra = await scegli_mostro(guild.id, cfg, tema, rng)
    vita = logica.vita_boss(await membri_attivi(guild.id), vita_extra)
    scade = datetime.now(timezone.utc) + timedelta(minutes=logica.DURATA_MINUTI)
    ev_id = await ai_gioco_repo.boss_crea(guild.id, canale.id, mostro, vita, scade, rete_id)
    if ev_id is None:
        return None, "In questo canale c'è già un boss."
    ev = await ai_gioco_repo.boss_evento(ev_id)
    try:
        png = await run_image_task(disegna_boss, mostro.nome, mostro.aspetto, vita, vita, tema)
        file = discord.File(io.BytesIO(png), filename="boss.png")
        messaggio = await canale.send(
            content=f"Un mostro è comparso! Dura {logica.DURATA_MINUTI} minuti.", embed=embed_boss(ev), file=file,
            view=BossView(), allowed_mentions=NESSUNA_MENZIONE,
        )
    except discord.HTTPException:
        await ai_gioco_repo.boss_chiudi(ev_id, "fuggito")
        return None, "Non riesco a scrivere in quel canale."
    await ai_gioco_repo.boss_imposta_messaggio(ev_id, messaggio.id)
    return ev_id, ""


# ---------------------------------------------------------------- cog
class AiBossCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(BossView())
        self._ciclo.start()
        await super().cog_load()

    async def cog_unload(self) -> None:
        self._ciclo.cancel()
        await super().cog_unload()

    @tasks.loop(seconds=5)
    async def _ciclo(self) -> None:
        """Ridisegna gli eventi toccati, chiude quelli scaduti e, ogni minuto, fa comparire i boss a orario."""
        try:
            for ev_id in list(AGGIORNA):
                AGGIORNA.discard(ev_id)
                await aggiorna_messaggio(self.bot, ev_id)
            for ev in await ai_gioco_repo.boss_scaduti():
                await chiudi_evento(self.bot, ev.id, "fuggito")
            adesso = datetime.now(timezone.utc)
            if adesso.second < 5:
                await self._comparse_programmate(adesso)
        except Exception:
            logger.warning("Giro del World Boss non riuscito.", exc_info=True)

    @_ciclo.before_loop
    async def _prima(self) -> None:
        await attendi_bot_pronto(self.bot)

    async def _comparse_programmate(self, adesso: datetime) -> None:
        for cfg in await ai_gioco_repo.boss_programmati():
            giorno = logica.giorno_di_comparsa(cfg.giorni, cfg.ora, cfg.fuso, adesso, cfg.ultimo_giorno)
            guild = self.bot.get_guild(cfg.guild_id)
            canale = guild.get_channel(cfg.canale_id) if guild and cfg.canale_id else None
            if giorno is None or canale is None:
                continue
            await ai_gioco_repo.boss_segna_comparso(cfg.guild_id, giorno)
            await avvia_evento(self.bot, guild, canale, cfg)

    async def togli_ruolo(self, guild_id: int, user_id: int, payload: dict) -> None:
        guild = self.bot.get_guild(guild_id)
        membro = guild.get_member(user_id) if guild else None
        ruolo = guild.get_role(int(payload.get("role_id", 0))) if guild else None
        if membro is not None and ruolo is not None and ruolo in membro.roles:
            await membro.remove_roles(ruolo, reason="Fine del premio del World Boss")

    # ------------------------------------------------------------ comandi
    @comando_di_gruppo("ai", nome="imposta", descrizione="Canale, giorni, ora e premi del World Boss.", sottogruppo=SOTTO_BOSS)
    @app_commands.describe(
        canale="Dove compare il boss", giorni="Giorni: ven, lun,gio, ogni giorno", ora="Ora di comparsa (0-23)",
        fuso="Fuso orario, es. Europe/Rome", acceso="Boss a orario acceso o spento", rete="Partecipa ai boss di rete",
        ruolo="Ruolo a tempo per chi colpisce di più", ruolo_ore="Quante ore dura il ruolo",
    )
    async def boss_imposta(
        self, interaction: discord.Interaction, canale: discord.TextChannel | None = None,
        giorni: app_commands.Range[str, 2, 40] | None = None, ora: app_commands.Range[int, 0, 23] | None = None,
        fuso: app_commands.Range[str, 3, 40] | None = None, acceso: bool | None = None, rete: bool | None = None,
        ruolo: discord.Role | None = None, ruolo_ore: app_commands.Range[int, 1, 168] | None = None,
    ) -> None:
        campi: dict = {}
        if canale is not None:
            campi["canale_id"] = canale.id
        if giorni is not None:
            elenco = logica.leggi_giorni(giorni)
            if elenco is None:
                await interaction.response.send_message("Non capisco i giorni: scrivi per esempio «ven» o «lun,gio».", ephemeral=True)
                return
            campi["giorni"] = tuple(elenco)
        if ora is not None:
            campi["ora"] = ora
        if fuso is not None:
            if logica.fuso_valido(fuso) is None:
                await interaction.response.send_message("Fuso orario sconosciuto: usa un nome come Europe/Rome.", ephemeral=True)
                return
            campi["fuso"] = fuso
        for nome, valore in (("attivo", acceso), ("rete", rete), ("ruolo_premio_ore", ruolo_ore)):
            if valore is not None:
                campi[nome] = valore
        if ruolo is not None:
            problema = check_role_assignable(interaction.guild, ruolo, interaction.guild.me, self_service=True)
            if problema:
                await interaction.response.send_message(problema, ephemeral=True)
                return
            campi["ruolo_premio_id"] = ruolo.id
        cfg = await ai_gioco_repo.boss_imposta(interaction.guild_id, **campi) if campi else await ai_gioco_repo.boss_config(interaction.guild_id)
        quando = logica.descrivi_orario(cfg.giorni, cfg.ora, cfg.fuso)
        testo = (
            f"World Boss **{'acceso' if cfg.attivo else 'spento'}**. Canale: {'<#%d>' % cfg.canale_id if cfg.canale_id else 'da scegliere'}. "
            f"Quando: {quando}. Boss di rete: {'sì' if cfg.rete else 'no'}. "
            f"Ruolo premio: {'<@&%d> per %d ore' % (cfg.ruolo_premio_id, cfg.ruolo_premio_ore) if cfg.ruolo_premio_id else 'nessuno'}."
        )
        await interaction.response.send_message(testo, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("ai", nome="avvia", descrizione="Fa comparire subito il World Boss.", sottogruppo=SOTTO_BOSS)
    @app_commands.describe(canale="Dove far comparire il boss (vuoto: il canale scelto o questo)")
    async def boss_avvia(self, interaction: discord.Interaction, canale: discord.TextChannel | None = None) -> None:
        cfg = await ai_gioco_repo.boss_config(interaction.guild_id)
        destinazione = canale or (interaction.guild.get_channel(cfg.canale_id) if cfg.canale_id else None) or interaction.channel
        if not isinstance(destinazione, discord.TextChannel):
            await interaction.response.send_message("Scegli un canale di testo.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ev_id, motivo = await avvia_evento(self.bot, interaction.guild, destinazione, cfg)
        await interaction.followup.send(f"Il boss è comparso in {destinazione.mention}." if ev_id else motivo, ephemeral=True)

    @comando_di_gruppo("ai", nome="rete", descrizione="Solo proprietario: pubblica o chiude il boss di rete.", sottogruppo=SOTTO_BOSS)
    @app_commands.describe(nome="Nome del mostro (vuoto: chiude il boss di rete)", aspetto="Come appare", vita_extra="Vita in più")
    async def boss_rete(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 2, 40] | None = None,
        aspetto: app_commands.Range[str, 0, 200] = "", vita_extra: app_commands.Range[int, 0, 100000] = 0,
    ) -> None:
        if interaction.user.id != config.OWNER_ID:
            await interaction.response.send_message("Questo comando è solo del proprietario del bot.", ephemeral=True)
            return
        if nome is None:
            n = await ai_gioco_repo.rete_chiudi()
            await interaction.response.send_message("Boss di rete chiuso." if n else "Nessun boss di rete aperto.", ephemeral=True)
            return
        await ai_gioco_repo.rete_chiudi()
        mostro = logica.Mostro(nome.strip(), aspetto.strip(), logica.mostro_pronto(None).frasi)
        rete_id = await ai_gioco_repo.rete_crea(interaction.user.id, mostro, vita_extra)
        await interaction.response.send_message(
            f"Boss di rete «{mostro.nome}» pubblicato (n. {rete_id}). Comparirà nei server che hanno scelto di partecipare.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    registra_modulo_ai()
    cog = AiBossCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(AZIONE_RUOLO, cog.togli_ruolo)

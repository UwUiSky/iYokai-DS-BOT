"""
cogs/leveling/economia.py
=========================
Regole dell'economia scelte dal server (/admin-economia premi, limiti, stato, statistiche,
ruolo, azzera) e premi settimanale e mensile (/monete settimanale, mensile). Il saldo di partenza
si dà a chi entra; il saldo di chi esce si tiene o si cancella, come ha scelto il server.
Funzioni coperte: ECO-002, ECO-003, ECO-008, ECO-010, ECO-012, ECO-014, ECO-019, ECO-021,
ECO-022, ECO-023, ECO-024, ECO-025, ECO-026, ECO-028
Dipende da: core/repositories/economia_repo.py
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.leveling.leveling import MODULE_LEVELING, _comando_rifiutato, _format_seconds
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core import web_panel_pubblico as pubblico
from core.database import db
from core.i18n import testo_per
from core.leveling_azzera_logic import nome_confermato
from core.leveling_logic import ATTESA_PERIODICI, LevelingSettings, MODI_SALDO_USCITA, seconds_until_next_claim
from core.repositories.leveling_repo import leveling_repo
from core.repositories.rischio_repo import rischio_repo
from core.safe_image import run_image_task
from core.wallet_card import render_wallet_card
from core.repositories.economia_repo import MAX_MEMBRI_PER_RUOLO, economia_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo

logger = logging.getLogger("iyokai.leveling.economia")

NESSUNA_MENZIONE = discord.AllowedMentions.none()
_SCELTE_USCITA = [
    app_commands.Choice(name="Tieni il saldo", value="tieni"),
    app_commands.Choice(name="Cancella il saldo", value="cancella"),
]
_SCELTE_AZIONE_RUOLO = [
    app_commands.Choice(name="Aggiungi", value="aggiungi"),
    app_commands.Choice(name="Togli", value="togli"),
]


def righe_stato(i: LevelingSettings) -> list[tuple[str, str]]:
    """ECO-023: (chiave del testo, valore) di tutte le regole dell'economia. Funzione pura."""
    def zero(v: int, spento: str = "no") -> str:
        return str(v) if v else spento

    return [
        ("eco_stato_moneta", i.currency_name),
        ("eco_stato_daily", f"{i.daily_coins} / {i.daily_ore} h"),
        ("eco_stato_serie", f"+{i.daily_bonus_serie} x max {i.daily_serie_max}" if i.daily_bonus_serie else "no"),
        ("eco_stato_lavoro", f"{i.work_min}-{i.work_max} / {i.work_attesa_min} min"),
        ("eco_stato_periodici", f"{zero(i.settimanale_coins)} / {zero(i.mensile_coins)}"),
        ("eco_stato_iniziale", zero(i.saldo_iniziale)),
        ("eco_stato_tetto", zero(i.tetto_saldo, "nessuno")),
        ("eco_stato_uscita", i.saldo_uscita),
        ("eco_stato_pay", f"{zero(i.pay_min, '-')} / {zero(i.pay_max, '-')} / {i.pay_tax_pct}%"),
        ("eco_stato_puntate", f"{i.puntata_min}-{i.puntata_max} / {i.attesa_gioco} s"),
        ("eco_stato_rischio", f"furto {'sì' if i.furto_attivo else 'no'} {i.furto_percentuale}%/{i.furto_successo}% · colpo {i.colpo_successo}%"),
    ]


class EconomiaCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    # ---------------------------------------------------------------- ascoltatori
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """ECO-002: il saldo di partenza, una volta sola. I bot non hanno monete."""
        if member.bot:
            return
        try:
            if not await db.is_module_active_for_guild(member.guild.id, MODULE_LEVELING):
                return
            importo = (await leveling_settings_repo.get_config(member.guild.id)).impostazioni.saldo_iniziale
            if importo > 0:
                await economia_repo.accredito_iniziale(member.guild.id, member.id, importo)
        except Exception:
            logger.warning("Saldo di partenza non dato (server %s)", member.guild.id, exc_info=True)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """ECO-014: se il server ha scelto «cancella», chi esce perde il saldo."""
        if member.bot:
            return
        try:
            if not await db.is_module_active_for_guild(member.guild.id, MODULE_LEVELING):
                return
            config = await leveling_settings_repo.get_config(member.guild.id, fresco=True)
            if config.impostazioni.saldo_uscita == "cancella":
                await economia_repo.cancella_saldo(member.guild.id, member.id)
        except Exception:
            logger.warning("Saldo di chi esce non cancellato (server %s)", member.guild.id, exc_info=True)

    # ---------------------------------------------------------------- /level movimenti (ECO-007)
    @comando_di_gruppo("level", nome="movimenti", descrizione="Gli ultimi movimenti delle tue monete (si tengono 30 giorni).")
    @app_commands.describe(pagina="Quale pagina (15 movimenti per pagina)")
    async def movimenti(self, interaction: discord.Interaction, pagina: app_commands.Range[int, 1, 100] = 1) -> None:
        if await _comando_rifiutato(interaction):
            return
        righe = await economia_repo.movimenti(interaction.guild.id, interaction.user.id, pagina)
        if not righe:
            await interaction.response.send_message(await testo_per(interaction, "mov_nessuno"), ephemeral=True)
            return
        testo = "\n".join(f"`{r['delta']:+d}` {discord.utils.escape_markdown(r['motivo'])} · <t:{int(r['at'].timestamp())}:R>" for r in righe)
        await interaction.response.send_message(testo[:3900], ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    # ---------------------------------------------------------------- /monete conto portafoglio (ECO-017)
    @comando_di_gruppo("monete", nome="portafoglio", descrizione="Il tuo saldo come immagine.", sottogruppo=("conto", "Banca e lavoro"))
    async def portafoglio(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        await interaction.response.defer()
        g, u = interaction.guild.id, interaction.user.id
        totali = await leveling_repo.get_totals(g, u)
        banca = (await rischio_repo.banca(g, u)).banca
        posizione = await leveling_repo.get_coins_position(g, u)
        moneta = (await leveling_settings_repo.get_config(g)).impostazioni.currency_name
        immagine = await leveling_settings_repo.get_immagine_moneta(g)
        try:
            png = await run_image_task(render_wallet_card, interaction.user.display_name, totali.coins_total, banca, posizione, moneta, immagine)
        except Exception:
            logger.warning("Portafoglio non disegnato", exc_info=True)
            await interaction.followup.send(f"**{totali.coins_total}** {moneta} · banca **{banca}**")
            return
        await interaction.followup.send(file=discord.File(io.BytesIO(png), filename="portafoglio.png"))

    # ---------------------------------------------------------------- /monete settimanale e mensile
    async def _riscuoti(self, interaction: discord.Interaction, tipo: str) -> None:
        if await _comando_rifiutato(interaction):
            return
        guild = interaction.guild
        impostazioni = (await leveling_settings_repo.get_config(guild.id)).impostazioni
        importo = impostazioni.settimanale_coins if tipo == "settimanale" else impostazioni.mensile_coins
        if importo <= 0:
            await interaction.response.send_message(await testo_per(interaction, "eco_premio_spento"), ephemeral=True)
            return
        attesa_s = ATTESA_PERIODICI[tipo]
        adesso = datetime.now(timezone.utc)
        if not await economia_repo.riscuoti_periodico(guild.id, interaction.user.id, tipo, importo, attesa_s, adesso):
            ultima = await economia_repo.ultima_riscossione(guild.id, interaction.user.id, tipo)
            resto = seconds_until_next_claim(ultima, attesa_s, adesso)
            await interaction.response.send_message(
                await testo_per(interaction, "eco_premio_gia_preso", tempo=_format_seconds(resto)), ephemeral=True
            )
            return
        await interaction.response.send_message(
            await testo_per(interaction, "eco_premio_preso", importo=importo, moneta=impostazioni.currency_name, pubblica=True),
            allowed_mentions=NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("monete", nome="settimanale", descrizione="Riscuoti il premio della settimana.")
    async def settimanale(self, interaction: discord.Interaction) -> None:
        await self._riscuoti(interaction, "settimanale")

    @comando_di_gruppo("monete", nome="mensile", descrizione="Riscuoti il premio del mese.")
    async def mensile(self, interaction: discord.Interaction) -> None:
        await self._riscuoti(interaction, "mensile")

    # ---------------------------------------------------------------- /admin-economia: regole
    async def _salva(self, interaction: discord.Interaction, campi: dict) -> None:
        if not campi:
            await interaction.response.send_message(await testo_per(interaction, "eco_scegli_un_valore"), ephemeral=True)
            return
        try:
            await leveling_settings_repo.set_options(interaction.guild.id, **campi)
        except ValueError as errore:
            await interaction.response.send_message(f"❌ {errore}", ephemeral=True)
            return
        await interaction.response.send_message(await testo_per(interaction, "eco_salvato"), ephemeral=True)

    @comando_di_gruppo(
        "admin-economia",
        nome="premi",
        descrizione="Premio giornaliero, serie di giorni, settimanale, mensile e lavoro.",
    )
    @app_commands.describe(
        daily="Monete del premio periodico (0-10000)",
        daily_ore="Ogni quante ore si riscuote (1-720; di base 24)",
        bonus_serie="Monete in più per ogni giorno di fila (0-1000; 0 = spento)",
        serie_max="Giorni di fila che contano per il bonus (1-365)",
        settimanale="Monete del premio settimanale (0 = spento)",
        mensile="Monete del premio mensile (0 = spento)",
        lavoro_min="Paga minima del lavoro (0-10000)",
        lavoro_max="Paga massima del lavoro (0-10000)",
        lavoro_attesa="Minuti tra due lavori (1-1440; di base 60)",
    )
    async def premi(
        self,
        interaction: discord.Interaction,
        daily: app_commands.Range[int, 0, 10_000] | None = None,
        daily_ore: app_commands.Range[int, 1, 720] | None = None,
        bonus_serie: app_commands.Range[int, 0, 1000] | None = None,
        serie_max: app_commands.Range[int, 1, 365] | None = None,
        settimanale: app_commands.Range[int, 0, 100_000] | None = None,
        mensile: app_commands.Range[int, 0, 1_000_000] | None = None,
        lavoro_min: app_commands.Range[int, 0, 10_000] | None = None,
        lavoro_max: app_commands.Range[int, 0, 10_000] | None = None,
        lavoro_attesa: app_commands.Range[int, 1, 1440] | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        scelti = {
            "daily_coins": daily, "daily_ore": daily_ore, "daily_bonus_serie": bonus_serie,
            "daily_serie_max": serie_max, "settimanale_coins": settimanale, "mensile_coins": mensile,
            "work_min": lavoro_min, "work_max": lavoro_max, "work_attesa_min": lavoro_attesa,
        }
        await self._salva(interaction, {k: v for k, v in scelti.items() if v is not None})

    @comando_di_gruppo(
        "admin-economia",
        nome="limiti",
        descrizione="Saldo di partenza, tetto al saldo, puntate dei giochi e saldo di chi esce.",
    )
    @app_commands.describe(
        saldo_iniziale="Monete date a chi entra nel server, una volta sola (0 = niente)",
        tetto_saldo="Saldo massimo di ogni membro (0 = nessun tetto)",
        puntata_min="Puntata minima dei giochi",
        puntata_max="Puntata massima dei giochi",
        attesa_gioco="Secondi tra una partita e l'altra (0-3600)",
        saldo_uscita="Cosa fare del saldo di chi esce dal server",
        furto="Sì = si possono rubare i contanti agli altri (spento di base)",
        furto_quota="Quota dei contanti della vittima che si può rubare, in % (1-50)",
        furto_successo="Probabilità che un furto riesca, in % (1-90)",
        colpo_successo="Probabilità che un colpo riesca, in % (1-90)",
        controllo="Probabilità (in millesimi, 0-500) del controllo anti-automazione nei comandi di guadagno (0 = spento)",
        negozio_web="Sì = il negozio si vede anche sul sito, in sola lettura (spento di base)",
    )
    @app_commands.choices(saldo_uscita=_SCELTE_USCITA)
    async def limiti(
        self,
        interaction: discord.Interaction,
        saldo_iniziale: app_commands.Range[int, 0, 1_000_000] | None = None,
        tetto_saldo: app_commands.Range[int, 0, 1_000_000_000] | None = None,
        puntata_min: app_commands.Range[int, 1, 1_000_000] | None = None,
        puntata_max: app_commands.Range[int, 1, 1_000_000] | None = None,
        attesa_gioco: app_commands.Range[int, 0, 3600] | None = None,
        saldo_uscita: app_commands.Choice[str] | None = None,
        furto: bool | None = None,
        furto_quota: app_commands.Range[int, 1, 50] | None = None,
        furto_successo: app_commands.Range[int, 1, 90] | None = None,
        colpo_successo: app_commands.Range[int, 1, 90] | None = None,
        controllo: app_commands.Range[int, 0, 500] | None = None,
        negozio_web: bool | None = None,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        if negozio_web is not None:  # ECO-080
            await db.set_guild_setting(interaction.guild.id, pubblico.SETTING_NEGOZIO_WEB, negozio_web, changed_by=interaction.user.id)
            altri = (saldo_iniziale, tetto_saldo, puntata_min, puntata_max, attesa_gioco, saldo_uscita, furto, furto_quota, furto_successo, colpo_successo, controllo)
            if all(v is None for v in altri):  # solo l'interruttore: si risponde qui; con altre opzioni risponde il salvataggio
                chiave = "eco_negozio_web_acceso" if negozio_web else "eco_negozio_web_spento"
                await interaction.response.send_message(
                    await testo_per(interaction, chiave, indirizzo=f"/n/{interaction.guild.id}"), ephemeral=True
                )
                return
        scelti = {
            "saldo_iniziale": saldo_iniziale, "tetto_saldo": tetto_saldo, "puntata_min": puntata_min,
            "puntata_max": puntata_max, "attesa_gioco": attesa_gioco,
            "saldo_uscita": saldo_uscita.value if saldo_uscita else None,
            "furto_attivo": furto, "furto_percentuale": furto_quota, "furto_successo": furto_successo,
            "colpo_successo": colpo_successo, "controllo_per_mille": controllo,  # ECO-030, ECO-031, ECO-158
        }
        await self._salva(interaction, {k: v for k, v in scelti.items() if v is not None})

    @comando_di_gruppo("admin-economia", nome="stato", descrizione="Tutte le regole dell'economia in un colpo.")
    async def stato(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        impostazioni = (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni
        embed = discord.Embed(title=await testo_per(interaction, "eco_stato_titolo"), color=discord.Color.gold())
        for chiave, valore in righe_stato(impostazioni):
            embed.add_field(name=await testo_per(interaction, chiave), value=f"`{valore}`"[:1024], inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo(
        "admin-economia", nome="statistiche", descrizione="Monete in giro nel server e come sono distribuite."
    )
    async def statistiche(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        s = await economia_repo.statistiche(interaction.guild.id)
        embed = discord.Embed(title=await testo_per(interaction, "eco_stat_titolo"), color=discord.Color.gold())
        for chiave, valore in (
            ("eco_stat_totale", s.totale), ("eco_stat_persone", s.persone), ("eco_stat_massimo", s.massimo),
            ("eco_stat_mediana", s.mediana), ("eco_stat_primi10", f"{s.quota_primi_10}%"), ("eco_stat_cassa", s.cassa),
        ):
            embed.add_field(name=await testo_per(interaction, chiave), value=f"`{valore}`", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------------------------------------------------------------- /admin-economia: azioni
    @comando_di_gruppo(
        "admin-economia", nome="ruolo", descrizione="Aggiungi o togli monete a tutti i membri di un ruolo."
    )
    @app_commands.describe(ruolo="Il ruolo", azione="Aggiungi o togli", importo="Monete a testa (1-1000000)")
    @app_commands.choices(azione=_SCELTE_AZIONE_RUOLO)
    async def ruolo(
        self,
        interaction: discord.Interaction,
        ruolo: discord.Role,
        azione: app_commands.Choice[str],
        importo: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        ids = [m.id for m in ruolo.members if not m.bot]
        if len(ids) > MAX_MEMBRI_PER_RUOLO:
            await interaction.response.send_message(
                await testo_per(interaction, "eco_ruolo_troppi", massimo=MAX_MEMBRI_PER_RUOLO), ephemeral=True
            )
            return
        if not ids:
            await interaction.response.send_message(await testo_per(interaction, "eco_ruolo_vuoto"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        toccati = await economia_repo.monete_a_ruolo(interaction.guild.id, ids, importo, azione.value == "togli")
        logger.info(
            "Monete a un ruolo: server %s, staff %s, ruolo %s, %s %s, %s persone.",
            interaction.guild.id, interaction.user.id, ruolo.id, azione.value, importo, toccati,
        )
        await interaction.followup.send(
            await testo_per(interaction, "eco_ruolo_fatto", persone=toccati, importo=importo, azione=azione.value),
            ephemeral=True,
            allowed_mentions=NESSUNA_MENZIONE,
        )

    @comando_di_gruppo(
        "admin-economia", nome="azzera", descrizione="Azzera i saldi di tutto il server (scrivi il nome del server)."
    )
    @app_commands.describe(conferma="Scrivi qui il nome esatto del server per confermare")
    async def azzera(self, interaction: discord.Interaction, conferma: app_commands.Range[str, 1, 100]) -> None:
        if await _comando_rifiutato(interaction):
            return
        guild = interaction.guild
        if not interaction.permissions.manage_guild:  # ricontrollo del permesso al momento dell'azione
            await interaction.response.send_message(await testo_per(interaction, "azz_serve_gestire_server"), ephemeral=True)
            return
        if not nome_confermato(conferma, guild.name):
            await interaction.response.send_message(await testo_per(interaction, "eco_azzera_nome_sbagliato"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        toccati = await economia_repo.azzera_economia(guild.id)
        logger.info("Economia azzerata: server %s, staff %s, %s saldi.", guild.id, interaction.user.id, toccati)
        await interaction.followup.send(await testo_per(interaction, "eco_azzera_fatto", saldi=toccati), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EconomiaCog(bot))

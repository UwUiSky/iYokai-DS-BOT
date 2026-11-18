"""
cogs/utility/alert_ruolo_live.py
================================
Ruolo «in diretta» automatico, con /admin-alert ruolo-live: fino a 5 regole per server, ognuna con il suo ruolo,
il ruolo richiesto, gli esclusi, parole del titolo o giochi, le eccezioni e un annuncio. Si basa sullo stato
«in diretta» che Discord mostra sul profilo: serve l'intent delle presenze (lo accende l'owner del bot).
Funzioni coperte: SPEC §10.13 (#129 ALR-042, 043, 044, 045, 046, 047, 048)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.role_safety import check_role_assignable
from core.alert_options_logic import MAX_FILTRO
from core.automod_eventi import chiede_intent_presenze
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import testo_per
from core.live_role_logic import MAX_MODELLO_ANNUNCIO, applica_regole, diretta_da_attivita
from core.repositories.live_role_repo import MAX_REGOLE, MAX_VOCI, live_role_repo

logger = logging.getLogger("iyokai.alert_ruolo_live")

GRUPPO = "admin-alert"
SOTTOGRUPPO = ("ruolo-live", "Ruolo «in diretta»: regole, filtri, esclusi, eccezioni, annuncio")
VALIDITA_CACHE = 60.0
RICONCILIA_MINUTI = 15
_NESSUNA = discord.AllowedMentions.none()


def ruolo_assegnabile(ruolo: discord.Role, guild: discord.Guild) -> str | None:
    """Chiave del testo d'errore se il bot non potrebbe dare questo ruolo, altrimenti None."""
    me = guild.me
    if ruolo.is_default() or ruolo.managed:
        return "alertlive_ruolo_non_valido"
    if me is None or not me.guild_permissions.manage_roles or ruolo >= me.top_role:
        return "alertlive_ruolo_sopra_il_bot"
    return None


class AlertRuoloLiveCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._cache: dict[int, tuple[float, list]] = {}

    async def cog_load(self) -> None:
        await super().cog_load()
        if not self._riconcilia.is_running():
            self._riconcilia.start()

    async def cog_unload(self) -> None:
        self._riconcilia.cancel()
        await super().cog_unload()

    # ------------------------------------------------------------ regole in memoria
    async def _regole(self, guild_id: int) -> list:
        voce = self._cache.get(guild_id)
        if voce and time.monotonic() - voce[0] < VALIDITA_CACHE:
            return voce[1]
        regole = await live_role_repo.regole(guild_id)
        if len(self._cache) > 5000:
            self._cache.clear()
        self._cache[guild_id] = (time.monotonic(), regole)
        return regole

    def _invalida(self, guild_id: int) -> None:
        self._cache.pop(guild_id, None)

    # ------------------------------------------------------------ eventi
    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        if after.bot or not chiede_intent_presenze():
            return
        prima, dopo = diretta_da_attivita(before.activities), diretta_da_attivita(after.activities)
        if prima is None and dopo is None or prima == dopo:
            return  # niente di cui occuparsi: la maggior parte degli aggiornamenti finisce qui
        regole = await self._regole(after.guild.id)
        if regole:
            await applica_regole(after.guild, after, regole, dopo, datetime.now(timezone.utc))

    @tasks.loop(minutes=RICONCILIA_MINUTI)
    async def _riconcilia(self) -> None:
        """Rimette in ordine chi ha il ruolo ma non è più in diretta (bot spento durante la diretta)."""
        if not chiede_intent_presenze():
            return
        for guild_id in await live_role_repo.server_con_regole():
            guild = self.bot.get_guild(guild_id)
            regole = await live_role_repo.regole(guild_id) if guild else []
            ruoli = {r.role_id for r in regole}
            for membro in list(guild.members) if guild else ():
                diretta = diretta_da_attivita(membro.activities)
                if diretta is not None or any(r.id in ruoli for r in membro.roles):
                    await applica_regole(guild, membro, regole, diretta, datetime.now(timezone.utc))

    @_riconcilia.before_loop
    async def _prima_di_riconciliare(self) -> None:
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------ comandi
    async def _regola(self, interaction: discord.Interaction, numero: int):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return None
        for r in await live_role_repo.regole(guild.id):
            if r.id == numero:
                return r
        await interaction.response.send_message(await testo_per(interaction, "alertlive_regola_non_trovata"), ephemeral=True)
        return None

    @comando_di_gruppo(GRUPPO, nome="aggiungi", descrizione="Nuova regola: dà un ruolo a chi va in diretta.", sottogruppo=SOTTOGRUPPO)
    @app_commands.describe(ruolo="Il ruolo «in diretta»", solo_ruolo="Lo riceve solo chi ha già questo ruolo (vuoto: tutti)")
    async def aggiungi(self, interaction: discord.Interaction, ruolo: discord.Role, solo_ruolo: discord.Role | None = None) -> None:
        """ALR-042 (ruolo in diretta), ALR-043 (solo chi ha un ruolo), ALR-048 (più regole nello stesso server)."""
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        errore = ruolo_assegnabile(ruolo, guild)
        if errore:
            await interaction.response.send_message(await testo_per(interaction, errore), ephemeral=True)
            return
        # Il ruolo arriva da solo a chi va in diretta: niente permessi pericolosi, e mai sopra chi lo imposta.
        motivo = check_role_assignable(guild, ruolo, interaction.user, self_service=True)
        if motivo is not None:
            await interaction.response.send_message(f"❌ {motivo}", ephemeral=True, allowed_mentions=_NESSUNA)
            return
        numero = await live_role_repo.aggiungi(guild.id, ruolo.id, interaction.user.id, solo_ruolo.id if solo_ruolo else None)
        if numero is None:
            await interaction.response.send_message(await testo_per(interaction, "alertlive_tetto", v1=MAX_REGOLE), ephemeral=True)
            return
        self._invalida(guild.id)
        avviso = "" if chiede_intent_presenze() else "\n" + await testo_per(interaction, "alertlive_senza_presenze")
        await interaction.response.send_message(
            await testo_per(interaction, "alertlive_creata", v1=numero, v2=ruolo.name[:100]) + avviso, ephemeral=True, allowed_mentions=_NESSUNA,
        )

    @comando_di_gruppo(GRUPPO, nome="elenco", descrizione="Le regole del ruolo «in diretta» del server.", sottogruppo=SOTTOGRUPPO)
    async def elenco(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        regole = await live_role_repo.regole(guild.id)
        if not regole:
            await interaction.response.send_message(await testo_per(interaction, "alertlive_nessuna"), ephemeral=True)
            return
        righe = []
        for r in regole:
            righe.append(
                f"**{r.id}** · <@&{r.role_id}>"
                + (f" · solo <@&{r.only_role_id}>" if r.only_role_id else "")
                + (f" · parole: {r.keywords[:60]}" if r.keywords else "")
                + (f" · giochi: {r.games[:60]}" if r.games else "")
                + f" · esclusi {len(r.esclusi_ruoli) + len(r.esclusi_membri)} · eccezioni {len(r.eccezioni)}"
                + (f" · annuncio <#{r.announce_channel_id}>" if r.announce_channel_id else "")
            )
        await interaction.response.send_message("\n".join(righe)[:1900], ephemeral=True, allowed_mentions=_NESSUNA)

    @comando_di_gruppo(GRUPPO, nome="rimuovi", descrizione="Toglie una regola del ruolo «in diretta».", sottogruppo=SOTTOGRUPPO)
    @app_commands.describe(numero="Il numero della regola (lo vedi in /admin-alert ruolo-live elenco)")
    async def rimuovi(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2_000_000_000]) -> None:
        guild = interaction.guild
        if guild is None:
            return
        fatto = await live_role_repo.rimuovi(guild.id, numero)
        self._invalida(guild.id)
        await interaction.response.send_message(
            await testo_per(interaction, "alertlive_rimossa" if fatto else "alertlive_regola_non_trovata"), ephemeral=True
        )

    @comando_di_gruppo(GRUPPO, nome="filtri", descrizione="Parole del titolo, giochi e ruolo richiesto di una regola.", sottogruppo=SOTTOGRUPPO)
    @app_commands.describe(
        numero="Il numero della regola", parole="Parole del titolo separate da virgola; «-parola» esclude; «-» da solo toglie il filtro",
        giochi="Solo questi giochi, separati da virgola; «-» li ammette tutti", solo_ruolo="Ruolo richiesto", tutti="Togli il ruolo richiesto",
    )
    async def filtri(
        self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2_000_000_000],
        parole: app_commands.Range[str, 0, MAX_FILTRO] | None = None, giochi: app_commands.Range[str, 0, MAX_FILTRO] | None = None,
        solo_ruolo: discord.Role | None = None, tutti: bool = False,
    ) -> None:
        """ALR-043 (ruolo richiesto) e ALR-045 (parole del titolo o giochi)."""
        regola = await self._regola(interaction, numero)
        if regola is None:
            return
        campi: dict = {}
        if parole is not None:
            campi["keywords"] = "" if parole.strip() == "-" else parole.strip()
        if giochi is not None:
            campi["games"] = "" if giochi.strip() == "-" else giochi.strip()
        if solo_ruolo is not None:
            campi["only_role_id"] = solo_ruolo.id
        if tutti:
            campi["only_role_id"] = None
        if campi:
            await live_role_repo.imposta(interaction.guild.id, regola.id, **campi)
            self._invalida(interaction.guild.id)
        await interaction.response.send_message(await testo_per(interaction, "alertlive_filtri_ok", v1=regola.id), ephemeral=True)

    @comando_di_gruppo(GRUPPO, nome="esclusi", descrizione="Membri o ruoli che non ricevono mai il ruolo di una regola.", sottogruppo=SOTTOGRUPPO)
    @app_commands.describe(numero="Il numero della regola", chi="Il membro o il ruolo", togli="Togli dall'elenco degli esclusi")
    async def esclusi(
        self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2_000_000_000],
        chi: discord.Member | discord.Role, togli: bool = False,
    ) -> None:
        """ALR-044."""
        regola = await self._regola(interaction, numero)
        if regola is None:
            return
        tipo = "escluso_ruolo" if isinstance(chi, discord.Role) else "escluso_membro"
        esito = await live_role_repo.voce(interaction.guild.id, regola.id, tipo, chi.id, aggiungi=not togli)
        self._invalida(interaction.guild.id)
        chiave = {"ok": "alertlive_voce_ok", "pieno": "alertlive_voci_piene", "manca": "alertlive_regola_non_trovata"}[esito]
        await interaction.response.send_message(await testo_per(interaction, chiave, v1=MAX_VOCI), ephemeral=True)

    @comando_di_gruppo(GRUPPO, nome="eccezioni", descrizione="Membri che ricevono il ruolo anche senza le parole o il gioco.", sottogruppo=SOTTOGRUPPO)
    @app_commands.describe(numero="Il numero della regola", membro="Il membro", togli="Togli dalle eccezioni")
    async def eccezioni(
        self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2_000_000_000],
        membro: discord.Member, togli: bool = False,
    ) -> None:
        """ALR-046."""
        regola = await self._regola(interaction, numero)
        if regola is None:
            return
        esito = await live_role_repo.voce(interaction.guild.id, regola.id, "eccezione", membro.id, aggiungi=not togli)
        self._invalida(interaction.guild.id)
        chiave = {"ok": "alertlive_voce_ok", "pieno": "alertlive_voci_piene", "manca": "alertlive_regola_non_trovata"}[esito]
        await interaction.response.send_message(await testo_per(interaction, chiave, v1=MAX_VOCI), ephemeral=True)

    @comando_di_gruppo(GRUPPO, nome="annuncio", descrizione="Annuncia in un canale chi va in diretta.", sottogruppo=SOTTOGRUPPO)
    @app_commands.describe(
        numero="Il numero della regola", canale="Dove annunciare (vuoto: spegni)",
        testo="Con {utente} {titolo} {gioco} {link}", pausa="Minuti minimi tra due annunci dello stesso membro (predefinito 360)",
    )
    async def annuncio(
        self, interaction: discord.Interaction, numero: app_commands.Range[int, 1, 2_000_000_000],
        canale: discord.TextChannel | None = None, testo: app_commands.Range[str, 1, MAX_MODELLO_ANNUNCIO] | None = None,
        pausa: app_commands.Range[int, 1, 10080] | None = None,
    ) -> None:
        """ALR-047."""
        regola = await self._regola(interaction, numero)
        if regola is None:
            return
        guild = interaction.guild
        if canale is not None:
            permessi = canale.permissions_for(guild.me) if guild.me else discord.Permissions.none()
            if canale.guild.id != guild.id or not permessi.view_channel or not permessi.send_messages:
                await interaction.response.send_message(await testo_per(interaction, "alertgest_canale_senza_permessi", v1=canale.mention), ephemeral=True)
                return
        campi: dict = {"announce_channel_id": canale.id if canale else None}
        if testo is not None:
            campi["announce_template"] = testo
        if pausa is not None:
            campi["announce_gap_minutes"] = pausa
        await live_role_repo.imposta(guild.id, regola.id, **campi)
        self._invalida(guild.id)
        await interaction.response.send_message(await testo_per(interaction, "alertlive_annuncio_ok", v1=regola.id), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AlertRuoloLiveCog(bot))

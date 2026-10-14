"""
cogs/utility/politica.py
========================
`/utility politica`: l'admin decide quali comandi girano nel suo server (CFG-008, CFG-009, CFG-010, CFG-018, #122).
Spegne un singolo comando, limita i comandi ad alcuni canali, fa ignorare ruoli e utenti, e con `diagnosi` scopre
perché un comando non risponde. La logica e i dati sono in `core/command_policy.py` (un solo punto, D16).
Funzioni coperte: SPEC §20 (NF-05), catalogo #122
Dipende da: core/command_policy.py, core/command_access.py (livello admin su ogni comando)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core import command_policy as pol
from core.command_access import Livello, autocomplete_protetto, puo_usare, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.command_search_logic import raccogli_comandi
from core.i18n import testo_per
from core.premium import guild_has_premium_access, registry

SOTTOGRUPPO = ("politica", "Politica dei comandi: spegni, limita, ignora, diagnosi")
MAX_SUGGERIMENTI = 25
MAX_RIGHE_ELENCO = 15

_ELENCHI = {
    "comandi": (pol.CHIAVE_COMANDI_OFF, "pol_riga_comandi"),
    "solo_canali": (pol.CHIAVE_CANALI_OK, "pol_riga_canali_ok"),
    "mai_canali": (pol.CHIAVE_CANALI_NO, "pol_riga_canali_no"),
    "ruoli": (pol.CHIAVE_RUOLI_IGNORATI, "pol_riga_ruoli"),
    "utenti": (pol.CHIAVE_UTENTI_IGNORATI, "pol_riga_utenti"),
}


def _menzione(chiave: str, valore) -> str:
    if chiave == pol.CHIAVE_COMANDI_OFF:
        return f"`/{valore}`"
    if chiave in (pol.CHIAVE_CANALI_OK, pol.CHIAVE_CANALI_NO):
        return f"<#{valore}>"
    if chiave == pol.CHIAVE_RUOLI_IGNORATI:
        return f"<@&{valore}>"
    return f"<@{valore}>"


def righe_politica(politica: pol.Politica, testi: dict[str, str], nessuno: str) -> str:
    """Il riepilogo della politica, una riga per elenco, tagliato per stare in un embed."""
    valori = {
        pol.CHIAVE_COMANDI_OFF: sorted(politica.comandi_off),
        pol.CHIAVE_CANALI_OK: sorted(politica.canali_ok),
        pol.CHIAVE_CANALI_NO: sorted(politica.canali_no),
        pol.CHIAVE_RUOLI_IGNORATI: sorted(politica.ruoli_ignorati),
        pol.CHIAVE_UTENTI_IGNORATI: sorted(politica.utenti_ignorati),
    }
    righe = []
    for chiave, titolo in ((c, t) for c, t in _ELENCHI.values()):
        voci = valori[chiave]
        mostrate = ", ".join(_menzione(chiave, v) for v in voci[:MAX_RIGHE_ELENCO]) or nessuno
        if len(voci) > MAX_RIGHE_ELENCO:
            mostrate += f" (+{len(voci) - MAX_RIGHE_ELENCO})"
        righe.append(f"**{testi[titolo]}**: {mostrate}")
    return "\n".join(righe)[:3900]


class PoliticaCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _percorsi(self) -> list[str]:
        return pol.percorsi_dei_comandi(self.bot.tree.get_commands())

    @autocomplete_protetto(Livello.ADMIN)
    async def _suggerisci(self, interaction: discord.Interaction, corrente: str) -> list[app_commands.Choice[str]]:
        cercato = corrente.strip().lower().lstrip("/")
        trovati = [p for p in self._percorsi() if cercato in p.lower()]
        return [app_commands.Choice(name=p[:100], value=p[:100]) for p in sorted(trovati)[:MAX_SUGGERIMENTI]]

    # ------------------------------------------------------------------
    @comando_di_gruppo("utility", nome="comando", descrizione="Spegne o riaccende un singolo comando.", sottogruppo=SOTTOGRUPPO)
    @richiedi(Livello.ADMIN)
    @app_commands.describe(comando="Il comando, es. «fun meme»", acceso="Sì = riaccendi, No = spegni")
    @app_commands.autocomplete(comando=_suggerisci)
    async def comando(
        self, interaction: discord.Interaction, comando: app_commands.Range[str, 1, 100], acceso: bool = False
    ) -> None:
        percorso = comando.strip().lstrip("/")
        if pol.sempre_aperto(percorso):
            await interaction.response.send_message(await testo_per(interaction, "pol_sempre_aperto"), ephemeral=True)
            return
        if percorso not in self._percorsi():
            await interaction.response.send_message(
                await testo_per(interaction, "pol_non_trovato", comando=percorso[:100]), ephemeral=True
            )
            return
        try:
            cambiato = await pol.modifica_elenco(
                interaction.guild.id, pol.CHIAVE_COMANDI_OFF, percorso, aggiungi=not acceso, changed_by=interaction.user.id
            )
        except pol.ElencoPieno:
            await interaction.response.send_message(
                await testo_per(interaction, "pol_elenco_pieno", massimo=pol.MAX_VOCI), ephemeral=True
            )
            return
        chiave = "pol_gia" if not cambiato else ("pol_riacceso" if acceso else "pol_spento")
        await interaction.response.send_message(await testo_per(interaction, chiave, comando=percorso), ephemeral=True)

    # ------------------------------------------------------------------
    @comando_di_gruppo("utility", nome="canali", descrizione="Dove il bot risponde ai comandi.", sottogruppo=SOTTOGRUPPO)
    @richiedi(Livello.ADMIN)
    @app_commands.describe(regola="Solo in questo canale, o mai in questo canale", canale="Canale o categoria", togli="Sì = togli la regola")
    @app_commands.choices(
        regola=[
            app_commands.Choice(name="solo in questo", value="solo_canali"),
            app_commands.Choice(name="mai in questo", value="mai_canali"),
        ]
    )
    async def canali(
        self,
        interaction: discord.Interaction,
        regola: app_commands.Choice[str],
        canale: discord.abc.GuildChannel,
        togli: bool = False,
    ) -> None:
        await self._modifica_id(interaction, _ELENCHI[regola.value][0], canale.id, aggiungi=not togli)

    @comando_di_gruppo("utility", nome="ignora", descrizione="Il bot ignora un ruolo o un utente.", sottogruppo=SOTTOGRUPPO)
    @richiedi(Livello.ADMIN)
    @app_commands.describe(ruolo="Ruolo da ignorare", utente="Utente da ignorare", togli="Sì = togli la regola")
    async def ignora(
        self,
        interaction: discord.Interaction,
        ruolo: discord.Role | None = None,
        utente: discord.User | None = None,
        togli: bool = False,
    ) -> None:
        if (ruolo is None) == (utente is None):
            await interaction.response.send_message(await testo_per(interaction, "pol_serve_bersaglio"), ephemeral=True)
            return
        if ruolo is not None:
            await self._modifica_id(interaction, pol.CHIAVE_RUOLI_IGNORATI, ruolo.id, aggiungi=not togli)
        else:
            await self._modifica_id(interaction, pol.CHIAVE_UTENTI_IGNORATI, utente.id, aggiungi=not togli)

    async def _modifica_id(self, interaction: discord.Interaction, chiave: str, valore: int, *, aggiungi: bool) -> None:
        try:
            cambiato = await pol.modifica_elenco(
                interaction.guild.id, chiave, valore, aggiungi=aggiungi, changed_by=interaction.user.id
            )
        except pol.ElencoPieno:
            await interaction.response.send_message(
                await testo_per(interaction, "pol_elenco_pieno", massimo=pol.MAX_VOCI), ephemeral=True
            )
            return
        testo = "pol_gia" if not cambiato else ("pol_aggiunto" if aggiungi else "pol_tolto")
        await interaction.response.send_message(await testo_per(interaction, testo), ephemeral=True)

    # ------------------------------------------------------------------
    @comando_di_gruppo("utility", nome="elenco", descrizione="Mostra la politica dei comandi e, se vuoi, azzera un elenco.", sottogruppo=SOTTOGRUPPO)
    @richiedi(Livello.ADMIN)
    @app_commands.describe(azzera="Elenco da svuotare (vuoto = solo mostra)")
    @app_commands.choices(
        azzera=[
            app_commands.Choice(name="comandi spenti", value="comandi"),
            app_commands.Choice(name="solo canali", value="solo_canali"),
            app_commands.Choice(name="mai canali", value="mai_canali"),
            app_commands.Choice(name="ruoli ignorati", value="ruoli"),
            app_commands.Choice(name="utenti ignorati", value="utenti"),
        ]
    )
    async def elenco(self, interaction: discord.Interaction, azzera: app_commands.Choice[str] | None = None) -> None:
        guild_id = interaction.guild.id
        avviso = None
        if azzera is not None:
            await pol.azzera_elenco(guild_id, _ELENCHI[azzera.value][0], changed_by=interaction.user.id)
            avviso = await testo_per(interaction, "pol_elenco_azzerato")
        politica = await pol.leggi_politica(guild_id)
        if politica.vuota:
            corpo = await testo_per(interaction, "pol_vuota")
        else:
            testi = {titolo: await testo_per(interaction, titolo) for _, titolo in _ELENCHI.values()}
            corpo = righe_politica(politica, testi, await testo_per(interaction, "pol_nessuno"))
            corpo += "\n\n" + await testo_per(interaction, "pol_esenti")
        embed = discord.Embed(title=await testo_per(interaction, "pol_titolo"), description=corpo, color=discord.Color.blurple())
        await interaction.response.send_message(content=avviso, embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    @comando_di_gruppo("utility", nome="diagnosi", descrizione="Scopre perché un comando non funziona qui.", sottogruppo=SOTTOGRUPPO)
    @richiedi(Livello.ADMIN)
    @app_commands.describe(comando="Il comando da controllare, es. «fun meme»")
    @app_commands.autocomplete(comando=_suggerisci)
    async def diagnosi(self, interaction: discord.Interaction, comando: app_commands.Range[str, 1, 100]) -> None:
        percorso = comando.strip().lstrip("/")
        info = next((c for c in raccogli_comandi(self.bot.tree.get_commands()) if c.percorso == percorso), None)
        if info is None:
            await interaction.response.send_message(
                await testo_per(interaction, "pol_non_trovato", comando=percorso[:100]), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        problemi = await self.problemi_del_comando(interaction, info)
        corpo = "\n".join(f"- {p}" for p in problemi) or await testo_per(interaction, "diag_ok")
        embed = discord.Embed(
            title=await testo_per(interaction, "diag_titolo", comando=percorso),
            description=corpo[:3900],
            color=discord.Color.orange() if problemi else discord.Color.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def problemi_del_comando(self, interaction: discord.Interaction, info) -> list[str]:
        """I motivi per cui il comando non gira in questo server: modulo spento, premium, livello, politica."""
        from core.database import db

        guild_id = interaction.guild.id
        problemi: list[str] = []
        if info.moduli:
            attivi = [m for m in info.moduli if await db.is_module_active_for_guild(guild_id, m)]
            if not attivi:
                problemi.append(await testo_per(interaction, "diag_modulo_spento", modulo=info.moduli[0]))
            for modulo in info.moduli:
                if registry.is_module_premium(modulo) and not await guild_has_premium_access(
                    guild_id, modulo, bot=self.bot
                ):
                    problemi.append(await testo_per(interaction, "diag_premium", modulo=modulo))
                    break
        for livello in dict.fromkeys(info.livelli):
            if not await puo_usare(interaction, livello):
                problemi.append(await testo_per(interaction, "diag_livello", livello=livello.value))
        politica = await pol.leggi_politica(guild_id)
        motivo = pol.valuta(
            politica,
            percorso=info.percorso,
            canali=pol._canali_dell_interazione(interaction),
            ruoli=[r.id for r in getattr(interaction.user, "roles", ())],
            user_id=interaction.user.id,
            esente=pol._e_esente(interaction),
        )
        if motivo is not None:
            problemi.append(await testo_per(interaction, motivo))
        return problemi


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PoliticaCog(bot))

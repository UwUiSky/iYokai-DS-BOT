"""
cogs/fun/gif.py
===============
GIF di reazione e di azione (#131, D70): `/gif reazione`, `/gif azione` (con il bottone «Ricambia») e
`/gif privacy` (chi non vuole ricevere azioni). Gratuite per tutti, solo SFW; la fonte e il credito
sono sempre mostrati. Le azioni tra utenti si spengono con `/admin-bot politica` su `gif azione`.
Funzioni coperte: SPEC §16 (FUN-081..135, 137, 139; D70)
Dipende da: core/gif_catalogo.py, core/gif_fonti.py, core/gif_logic.py, core/repositories/gif_privacy_repo.py
"""

from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fun.entertainment import MODULE_FUN
from core import gif_catalogo as catalogo
from core import gif_logic as logica
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.gif_fonti import Gif, servizio_gif
from core.i18n import da_locale_discord, t, testo_per
from core.repositories.gif_privacy_repo import MAX_BLOCCHI, gif_privacy_repo
from core.ui_base import BaseView

NESSUNA_MENZIONE = discord.AllowedMentions.none()
SCADENZA_BOTTONE_SECONDI = 600


async def _completa_reazione(interaction: discord.Interaction, digitato: str) -> list[app_commands.Choice[str]]:
    return _scelte("reazione", interaction, digitato)


async def _completa_azione(interaction: discord.Interaction, digitato: str) -> list[app_commands.Choice[str]]:
    return _scelte("azione", interaction, digitato)


def _scelte(tipo: str, interaction: discord.Interaction, digitato: str) -> list[app_commands.Choice[str]]:
    """Solo dati locali: nessuna rete e nessun database (il completamento ha 3 secondi)."""
    lingua = da_locale_discord(getattr(interaction, "locale", None))
    return [app_commands.Choice(name=n, value=v) for n, v in catalogo.suggerimenti(tipo, digitato, lingua)]


def _embed(gif: Gif, lingua: str, descrizione: str | None = None) -> discord.Embed:
    embed = discord.Embed(description=descrizione, color=discord.Color.blurple())
    embed.set_image(url=gif.url)
    if gif.dettaglio:
        credito = t("gif_credito_dettaglio", lingua, fonte=gif.fonte, dettaglio=gif.dettaglio)
    else:
        credito = t("gif_credito", lingua, fonte=gif.fonte)
    embed.set_footer(text=credito[:2000])
    if gif.link:
        riga = f"-# [{credito}]({gif.link})"
        embed.description = f"{descrizione}\n{riga}" if descrizione else riga
    return embed


class RicambiaView(BaseView):
    """Il bottone «Ricambia»: lo preme solo chi ha ricevuto l'azione, una volta sola."""

    def __init__(self, cog: "GifCog", voce: catalogo.Voce, autore_id: int, bersaglio_id: int, etichetta: str) -> None:
        super().__init__(timeout=SCADENZA_BOTTONE_SECONDI)
        self._cog = cog
        self._voce = voce
        self._autore_id = autore_id
        self._bersaglio_id = bersaglio_id
        self.bottone = discord.ui.Button(
            label=etichetta[:80], style=discord.ButtonStyle.secondary,
            custom_id=f"gif:ric:{voce.id}:{autore_id}:{bersaglio_id}"[:100],
        )
        self.bottone.callback = self._premuto
        self.add_item(self.bottone)

    async def _premuto(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self._bersaglio_id:
            await interaction.response.send_message(
                await testo_per(interaction, "gif_ricambia_solo_bersaglio", bersaglio=f"<@{self._bersaglio_id}>"),
                ephemeral=True, allowed_mentions=NESSUNA_MENZIONE,
            )
            return
        if not await self._cog.azione_permessa(interaction):
            await interaction.response.send_message(await testo_per(interaction, "gif_modulo_spento"), ephemeral=True)
            return
        self.bottone.disabled = True  # un solo clic: la risposta è una sola
        await interaction.response.edit_message(view=self)
        autore = interaction.guild.get_member(self._autore_id) if interaction.guild else None
        if autore is None:
            return
        motivo = await self._cog.controlla_azione(interaction.user, autore)
        if motivo:
            await interaction.followup.send(await testo_per(interaction, motivo), ephemeral=True)
            return
        await self._cog.manda_azione(interaction, self._voce, interaction.user, autore, con_bottone=False)


class GifCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _modulo_attivo(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "gif_solo_server"), ephemeral=True)
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_FUN):
            await interaction.response.send_message(await testo_per(interaction, "gif_modulo_spento"), ephemeral=True)
            return False
        return True

    async def azione_permessa(self, interaction: discord.Interaction) -> bool:
        """Modulo acceso e `gif azione` non spenta dalla politica del server (il bottone non passa dai controlli del comando)."""
        from core.command_policy import valuta_percorso

        if interaction.guild is None or not await db.is_module_active_for_guild(interaction.guild.id, MODULE_FUN):
            return False
        return await valuta_percorso(interaction, "gif azione") is None

    async def controlla_azione(self, autore: discord.abc.User, bersaglio: discord.abc.User) -> str | None:
        return await logica.esito_azione(gif_privacy_repo, autore.id, bersaglio.id, bool(bersaglio.bot))

    async def _niente_gif(self, interaction: discord.Interaction, dopo_defer_pubblico: bool) -> None:
        testo = await testo_per(interaction, "gif_non_trovata")
        if dopo_defer_pubblico:
            await interaction.delete_original_response()
        await interaction.followup.send(testo, ephemeral=True)

    async def manda_azione(
        self, interaction: discord.Interaction, voce: catalogo.Voce, autore: discord.abc.User,
        bersaglio: discord.abc.User, *, con_bottone: bool, dopo_defer_pubblico: bool = False,
    ) -> None:
        """Manda la GIF e la frase; la risposta all'interazione è già stata data (defer o bottone)."""
        gif = await servizio_gif.prendi(voce)
        if gif is None:
            await self._niente_gif(interaction, dopo_defer_pubblico)
            return
        lingua = await _lingua_pubblica(interaction)
        testo = logica.frase(voce, lingua, autore.mention, bersaglio.mention)
        vista = RicambiaView(self, voce, autore.id, bersaglio.id, t("gif_ricambia", lingua)) if con_bottone else None
        extra = {"view": vista} if vista else {}
        await interaction.followup.send(
            content=testo, embed=_embed(gif, lingua),
            allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=bersaglio.id)], everyone=False, roles=False),
            **extra,
        )

    @comando_di_gruppo("gif", nome="reazione", descrizione="Una GIF di reazione: piangi, balli, ridi...")
    @app_commands.describe(nome="Quale reazione", testo="Un testo da mettere accanto alla GIF (massimo 200 caratteri)")
    @app_commands.autocomplete(nome=_completa_reazione)
    async def reazione(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 100],
        testo: Optional[app_commands.Range[str, 1, logica.MAX_TESTO]] = None,
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        voce = catalogo.trova("reazione", nome)  # il completamento non è obbligatorio: si riconvalida
        if voce is None:
            await interaction.response.send_message(await testo_per(interaction, "gif_voce_sconosciuta"), ephemeral=True)
            return
        await interaction.response.defer()
        gif = await servizio_gif.prendi(voce)
        if gif is None:
            await self._niente_gif(interaction, True)
            return
        lingua = await _lingua_pubblica(interaction)
        frase = logica.frase(voce, lingua, interaction.user.display_name, testo=testo)
        await interaction.followup.send(embed=_embed(gif, lingua, frase), allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo("gif", nome="azione", descrizione="Una GIF di azione verso un utente: abbraccio, bacio, schiaffo...")
    @app_commands.describe(nome="Quale azione", utente="Verso chi")
    @app_commands.autocomplete(nome=_completa_azione)
    async def azione(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 100], utente: discord.Member
    ) -> None:
        if not await self._modulo_attivo(interaction):
            return
        voce = catalogo.trova("azione", nome)
        if voce is None:
            await interaction.response.send_message(await testo_per(interaction, "gif_voce_sconosciuta"), ephemeral=True)
            return
        motivo = await self.controlla_azione(interaction.user, utente)
        if motivo:
            await interaction.response.send_message(await testo_per(interaction, motivo), ephemeral=True)
            return
        await interaction.response.defer()
        await self.manda_azione(interaction, voce, interaction.user, utente, con_bottone=True, dopo_defer_pubblico=True)

    @comando_di_gruppo("gif", nome="privacy", descrizione="Scegli chi può farti le azioni con le GIF.")
    @app_commands.describe(modo="Cosa vuoi fare", utente="L'utente (solo per bloccare o sbloccare)")
    @app_commands.choices(
        modo=[
            app_commands.Choice(name="Consenti a tutti", value="consenti-tutti"),
            app_commands.Choice(name="Blocca tutti", value="blocca-tutti"),
            app_commands.Choice(name="Blocca un utente", value="blocca-utente"),
            app_commands.Choice(name="Sblocca un utente", value="sblocca-utente"),
            app_commands.Choice(name="Mostra l'elenco", value="elenco"),
        ]
    )
    async def privacy(
        self, interaction: discord.Interaction, modo: app_commands.Choice[str], utente: Optional[discord.User] = None
    ) -> None:
        # Un diritto della persona: funziona anche con il modulo spento. Risposta sempre nascosta.
        me = interaction.user.id
        scelta = modo.value
        if scelta in ("consenti-tutti", "blocca-tutti"):
            tutti = scelta == "blocca-tutti"
            await gif_privacy_repo.imposta_blocca_tutti(me, tutti)
            chiave = "gif_privacy_tutti_no" if tutti else "gif_privacy_tutti_ok"
            await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)
            return
        if scelta == "elenco":
            ids = await gif_privacy_repo.elenco(me)
            stato = await testo_per(
                interaction, "gif_stato_bloccate" if await gif_privacy_repo.blocca_tutti(me) else "gif_stato_consentite"
            )
            if ids:
                testo = await testo_per(
                    interaction, "gif_privacy_elenco", numero=len(ids), massimo=MAX_BLOCCHI, stato=stato,
                    elenco="\n".join(f"<@{i}>" for i in ids),
                )
            else:
                testo = await testo_per(interaction, "gif_privacy_elenco_vuoto", stato=stato)
            embed = discord.Embed(title=await testo_per(interaction, "gif_privacy_titolo"), description=testo[:4000])
            await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)
            return
        if utente is None:
            await interaction.response.send_message(await testo_per(interaction, "gif_privacy_serve_utente"), ephemeral=True)
            return
        if utente.id == me:
            await interaction.response.send_message(await testo_per(interaction, "gif_te_stesso"), ephemeral=True)
            return
        nome = utente.mention
        if scelta == "blocca-utente":
            esito = await gif_privacy_repo.blocca(me, utente.id)
            chiave = {"ok": "gif_privacy_bloccato", "gia": "gif_privacy_gia", "tetto": "gif_privacy_tetto"}[esito]
        else:
            chiave = "gif_privacy_sbloccato" if await gif_privacy_repo.sblocca(me, utente.id) else "gif_privacy_non_bloccato"
        await interaction.response.send_message(
            await testo_per(interaction, chiave, utente=nome, massimo=MAX_BLOCCHI),
            ephemeral=True, allowed_mentions=NESSUNA_MENZIONE,
        )


async def _lingua_pubblica(interaction: discord.Interaction) -> str:
    from core.i18n import lingua_interazione

    return await lingua_interazione(interaction, pubblica=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GifCog(bot))

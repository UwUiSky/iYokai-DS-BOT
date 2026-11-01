"""
cogs/utility/embed_builder.py
=============================
Costruttore di embed (NF-17, SPEC §22.6): l'admin compone un embed con titolo,
testo, colore, immagini e campi, lo vede in anteprima, lo pubblica e lo modifica
anche dopo. Comandi in `/moduli embed *`. Tutti i limiti si controllano
al salvataggio (core/embed_builder_logic.py).
Funzioni coperte: SPEC §22 (NF-17)
"""

from __future__ import annotations

import asyncio
import logging
import weakref

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.embed_builder_logic import (
    MAX_CAMPI,
    MAX_DESCRIZIONE,
    MAX_EMBED,
    MAX_NOME,
    MAX_NOME_CAMPO,
    MAX_PIEDE,
    MAX_TITOLO,
    MAX_URL,
    MAX_VALORE_CAMPO,
    DatiEmbed,
    a_json,
    costruisci,
    da_json,
    valida,
)
from core.i18n import testo_per
from core.lista_limiti_logic import righe_entro_limite
from core.nome_logic import normalizza_nome
from core.premium import PremiumModule, registry
from core.repositories.saved_embed_repo import saved_embed_repo
from core.safe_http import url_e_sicuro

logger = logging.getLogger("iyokai.embed_builder")

MODULE_EMBED_BUILDER = "embed_builder"

_SG_MESSAGGI = ("embed", "Costruttore di embed")
_NESSUNA_MENZIONE = discord.AllowedMentions.none()
_CANCELLA = "-"  # in modifica, "-" toglie il valore


class EmbedBuilderCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._blocchi: "weakref.WeakValueDictionary[tuple[int, str], asyncio.Lock]" = weakref.WeakValueDictionary()

    def _blocco(self, guild_id: int, nome: str) -> asyncio.Lock:
        chiave = (guild_id, nome.lower())
        blocco = self._blocchi.get(chiave)
        if blocco is None:
            blocco = asyncio.Lock()
            self._blocchi[chiave] = blocco
        return blocco

    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_EMBED_BUILDER):
            await interaction.response.send_message(
                await testo_per(interaction, "ping_questo_modulo_non_attivo_su"),
                ephemeral=True,
            )
            return False
        return True

    @staticmethod
    async def _indirizzi_sicuri(dati: DatiEmbed) -> str | None:
        """Ogni indirizzo scritto da un utente passa da safe_http (SEC): None se tutti ammessi."""
        for etichetta, url in (("immagine", dati.image_url), ("miniatura", dati.thumbnail_url)):
            if url and not await url_e_sicuro(url):
                return f"L'indirizzo della {etichetta} non è ammesso (indirizzo interno o porta non consentita)."
        return None

    @staticmethod
    def _errori_testo(errori: list[str]) -> str:
        return "L'embed non è valido:\n" + "\n".join(f"• {e}" for e in errori[:10])

    # ================================================================
    # Crea
    # ================================================================
    @comando_di_gruppo("moduli", nome="crea", descrizione="Crea un embed e guarda l'anteprima.", sottogruppo=_SG_MESSAGGI)
    @app_commands.describe(
        nome=f"Il nome per ritrovarlo (a-z, cifre, - e _; massimo {MAX_NOME})",
        titolo="Il titolo",
        descrizione="Il testo",
        colore="Colore #RRGGBB",
        immagine="Indirizzo (https) di un'immagine grande",
        miniatura="Indirizzo (https) di una miniatura",
        piede="Il testo in fondo",
    )
    async def crea(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, MAX_NOME],
        titolo: app_commands.Range[str, 1, MAX_TITOLO] | None = None,
        descrizione: app_commands.Range[str, 1, MAX_DESCRIZIONE] | None = None,
        colore: app_commands.Range[str, 4, 7] | None = None,
        immagine: app_commands.Range[str, 1, MAX_URL] | None = None,
        miniatura: app_commands.Range[str, 1, MAX_URL] | None = None,
        piede: app_commands.Range[str, 1, MAX_PIEDE] | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        normalizzato = normalizza_nome(nome)
        if normalizzato is None:
            await interaction.response.send_message(
                await testo_per(interaction, "forms_il_nome_puo_avere_solo"), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        dati = DatiEmbed(
            title=titolo, description=descrizione, color=colore, image_url=immagine,
            thumbnail_url=miniatura, footer=piede,
        )
        errori = valida(dati)
        if errori:
            await interaction.followup.send(self._errori_testo(errori), ephemeral=True)
            return
        non_sicuro = await self._indirizzi_sicuri(dati)
        if non_sicuro is not None:
            await interaction.followup.send(non_sicuro, ephemeral=True)
            return
        esito = await saved_embed_repo.create(interaction.guild.id, normalizzato, a_json(dati), interaction.user.id)
        if esito == "esiste":
            await interaction.followup.send(await testo_per(interaction, "embedbuilder_esiste_gia_un_embed_usa", normalizzato=normalizzato), ephemeral=True)
            return
        if esito == "pieno":
            await interaction.followup.send(await testo_per(interaction, "embedbuilder_questo_server_ha_gia_embed", v1=MAX_EMBED), ephemeral=True)
            return
        await interaction.followup.send(
            await testo_per(interaction, "embedbuilder_embed_salvato_anteprima_qui_sotto", normalizzato=normalizzato),
            embed=costruisci(dati),
            ephemeral=True,
        )

    # ================================================================
    # Modifica
    # ================================================================
    @comando_di_gruppo("moduli", nome="modifica", descrizione="Cambia un embed salvato (e il messaggio già pubblicato).", sottogruppo=_SG_MESSAGGI)
    @app_commands.describe(
        nome="L'embed da cambiare",
        titolo=f"Nuovo titolo (\"{_CANCELLA}\" lo toglie)",
        descrizione=f"Nuovo testo (\"{_CANCELLA}\" lo toglie)",
        colore="Nuovo colore #RRGGBB",
        immagine=f"Nuova immagine (\"{_CANCELLA}\" la toglie)",
        miniatura=f"Nuova miniatura (\"{_CANCELLA}\" la toglie)",
        piede=f"Nuovo piede (\"{_CANCELLA}\" lo toglie)",
        campo_nome="Aggiungi un campo: il suo nome",
        campo_valore="Aggiungi un campo: il suo testo",
        campo_inline="Il campo sta in riga con gli altri?",
        togli_campo=f"Il numero (1-{MAX_CAMPI}) di un campo da togliere",
    )
    async def modifica(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, MAX_NOME],
        titolo: app_commands.Range[str, 1, MAX_TITOLO] | None = None,
        descrizione: app_commands.Range[str, 1, MAX_DESCRIZIONE] | None = None,
        colore: app_commands.Range[str, 1, 7] | None = None,
        immagine: app_commands.Range[str, 1, MAX_URL] | None = None,
        miniatura: app_commands.Range[str, 1, MAX_URL] | None = None,
        piede: app_commands.Range[str, 1, MAX_PIEDE] | None = None,
        campo_nome: app_commands.Range[str, 1, MAX_NOME_CAMPO] | None = None,
        campo_valore: app_commands.Range[str, 1, MAX_VALORE_CAMPO] | None = None,
        campo_inline: bool = False,
        togli_campo: app_commands.Range[int, 1, MAX_CAMPI] | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        # Un blocco per embed: due modifiche insieme (es. due campi aggiunti) si mettono in fila,
        # altrimenti la seconda riparte dallo stato vecchio e cancella il campo della prima.
        async with self._blocco(interaction.guild.id, nome):
            await self._applica_modifica(
                interaction, nome, titolo, descrizione, colore, immagine, miniatura, piede,
                campo_nome, campo_valore, campo_inline, togli_campo,
            )

    async def _applica_modifica(
        self, interaction, nome, titolo, descrizione, colore, immagine, miniatura, piede,
        campo_nome, campo_valore, campo_inline, togli_campo,
    ) -> None:
        salvato = await saved_embed_repo.get(interaction.guild.id, nome)
        if salvato is None:
            await interaction.followup.send(await testo_per(interaction, "embedbuilder_non_un_embed_con_quel"), ephemeral=True)
            return
        if (campo_nome is None) != (campo_valore is None):
            await interaction.followup.send(await testo_per(interaction, "embedbuilder_per_aggiungere_un_campo_servono"), ephemeral=True)
            return
        attuale = da_json(salvato.data)

        def cambia(nuovo: str | None, vecchio: str | None) -> str | None:
            if nuovo is None:
                return vecchio
            return None if nuovo == _CANCELLA else nuovo

        campi = list(attuale.fields)
        if togli_campo is not None:
            if togli_campo > len(campi):
                await interaction.followup.send(await testo_per(interaction, "embedbuilder_embed_ha_campi", v1=len(campi)), ephemeral=True)
                return
            del campi[togli_campo - 1]
        if campo_nome is not None:
            campi.append((campo_nome, campo_valore, campo_inline))
        dati = DatiEmbed(
            title=cambia(titolo, attuale.title),
            description=cambia(descrizione, attuale.description),
            color=cambia(colore, attuale.color),
            image_url=cambia(immagine, attuale.image_url),
            thumbnail_url=cambia(miniatura, attuale.thumbnail_url),
            footer=cambia(piede, attuale.footer),
            fields=tuple(campi),
        )
        errori = valida(dati)
        if errori:
            await interaction.followup.send(self._errori_testo(errori), ephemeral=True)
            return
        non_sicuro = await self._indirizzi_sicuri(dati)
        if non_sicuro is not None:
            await interaction.followup.send(non_sicuro, ephemeral=True)
            return
        embed = costruisci(dati)

        nota = ""
        if salvato.message_id is not None:
            # Prima il messaggio già pubblicato, poi il database: se Discord rifiuta, resta com'era.
            canale = interaction.guild.get_channel(salvato.channel_id)
            aggiornato = False
            if canale is not None:
                try:
                    messaggio = await canale.fetch_message(salvato.message_id)
                    await messaggio.edit(embed=embed, allowed_mentions=_NESSUNA_MENZIONE)
                    aggiornato = True
                except discord.NotFound:
                    pass  # messaggio cancellato a mano
                except discord.HTTPException as errore:
                    logger.warning("Embed %s: messaggio non aggiornato: %s", nome, errore)
                    await interaction.followup.send(
                        await testo_per(interaction, "embedbuilder_embed_non_stato_cambiato_discord"),
                        ephemeral=True,
                    )
                    return
            if aggiornato:
                nota = " Il messaggio pubblicato è stato aggiornato."
            else:
                await saved_embed_repo.set_published(interaction.guild.id, nome, None, None)
                nota = " Il messaggio pubblicato non c'era più: ripubblicalo con `/moduli embed pubblica`."
        await saved_embed_repo.update_data(interaction.guild.id, nome, a_json(dati))
        await interaction.followup.send(await testo_per(interaction, "embedbuilder_embed_aggiornato", nota=nota), embed=embed, ephemeral=True)

    # ================================================================
    # Pubblica, elenco, elimina
    # ================================================================
    @comando_di_gruppo("moduli", nome="pubblica", descrizione="Manda un embed salvato in un canale.", sottogruppo=_SG_MESSAGGI)
    @app_commands.describe(nome="L'embed da mandare", canale="Il canale (di norma quello dove sei)")
    async def pubblica(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, MAX_NOME],
        canale: discord.TextChannel | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        destinazione = canale or interaction.channel
        if not isinstance(destinazione, discord.TextChannel):
            await interaction.response.send_message(await testo_per(interaction, "embedbuilder_scegli_un_canale_di_testo"), ephemeral=True)
            return
        salvato = await saved_embed_repo.get(interaction.guild.id, nome)
        if salvato is None:
            await interaction.response.send_message(await testo_per(interaction, "embedbuilder_non_un_embed_con_quel"), ephemeral=True)
            return
        permessi = destinazione.permissions_for(interaction.guild.me)
        if not (permessi.send_messages and permessi.embed_links):
            await interaction.response.send_message(
                await testo_per(interaction, "embedbuilder_in_al_bot_servono_permessi", mention=destinazione.mention),
                ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
            )
            return
        try:
            inviato = await destinazione.send(
                embed=costruisci(da_json(salvato.data)), allowed_mentions=_NESSUNA_MENZIONE
            )
        except discord.HTTPException:
            await interaction.response.send_message(await testo_per(interaction, "embedbuilder_discord_non_ha_accettato_il"), ephemeral=True)
            return
        await saved_embed_repo.set_published(interaction.guild.id, nome, destinazione.id, inviato.id)
        await interaction.response.send_message(
            await testo_per(interaction, "embedbuilder_embed_pubblicato_in_se_lo", mention=destinazione.mention),
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("moduli", nome="elenco", descrizione="Mostra gli embed salvati.", sottogruppo=_SG_MESSAGGI)
    async def elenco(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        salvati = await saved_embed_repo.list(interaction.guild.id)
        righe = [
            f"`{s.name}`" + (f" · pubblicato in <#{s.channel_id}>" if s.message_id else "")
            for s in salvati
        ] or ["Nessun embed salvato."]
        testo, _ = righe_entro_limite(righe, 3900)
        await interaction.response.send_message(
            embed=discord.Embed(title=await testo_per(interaction, "embedbuilder_embed_salvati", v1=len(salvati), v2=MAX_EMBED), description=testo),
            ephemeral=True, allowed_mentions=_NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("moduli", nome="elimina", descrizione="Elimina un embed salvato (il messaggio pubblicato resta).", sottogruppo=_SG_MESSAGGI)
    @app_commands.describe(nome="L'embed da eliminare")
    async def elimina(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, MAX_NOME]) -> None:
        if not await self._pronto(interaction):
            return
        fatto = await saved_embed_repo.delete(interaction.guild.id, nome)
        await interaction.response.send_message(
            await testo_per(interaction, "embedbuilder_embed_eliminato") if fatto else await testo_per(interaction, "embedbuilder_non_un_embed_con_quel"), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_EMBED_BUILDER,
            display_name="Costruttore di embed",
            category="utility",
            description="Compone embed con titolo, testo, colore, immagini e campi; li pubblica e li modifica dopo.",
            premium_capable=False,
        )
    )
    await bot.add_cog(EmbedBuilderCog(bot))

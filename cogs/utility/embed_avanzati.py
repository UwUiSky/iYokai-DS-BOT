"""
cogs/utility/embed_avanzati.py
==============================
Embed avanzati: `/admin-messaggi embed json` (importa ed esporta), `embed bottoni` (link e «mostra tag»,
massimo 25) e la costruzione del messaggio per `embed pubblica` (più embed, formato classico o componenti V2).
I bottoni «mostra tag» sono DynamicItem: funzionano dopo il riavvio.
Funzioni coperte: catalogo #128 UTL-075, 076, 079, 080, 081 (D69, B4)
"""

from __future__ import annotations

import io
import json
import logging

import discord
from discord import app_commands
from discord.ext import commands

from core import embed_builder_logic as L
from core.command_groups import SOTTOGRUPPI, CogConGruppi, comando_di_gruppo
from core.embed_builder_logic import DatiEmbed, a_json, costruisci, valida
from core.i18n import lingua_interazione, t
from core.messaggi_auto_logic import link_ai_messaggi
from core.nome_logic import normalizza_nome
from core.phishing_logic import carica_lista_locale, e_phishing
from core.repositories.custom_command_repo import custom_command_repo
from core.repositories.embed_bottoni_repo import MAX_BOTTONI, embed_bottoni_repo
from core.repositories.saved_embed_repo import saved_embed_repo
from core.repositories.tag_inneschi_repo import tag_inneschi_repo
from core.safe_http import url_e_sicuro
from core.ui_base import BaseLayoutView, BaseModal, BaseView, _utente_o_server_in_blacklist

logger = logging.getLogger("iyokai.embed_avanzati")
_NESSUNA = discord.AllowedMentions.none()


class BottoneTag(
    discord.ui.DynamicItem[discord.ui.Button], template=r"eb:(?P<g>[0-9]+):(?P<e>[a-z0-9_-]+):(?P<n>[0-9]+)"
):
    def __init__(self, guild_id: int, embed: str, posizione: int, etichetta: str = "Tag") -> None:
        super().__init__(
            discord.ui.Button(
                label=etichetta[: L.MAX_TESTO_BOTTONE],
                style=discord.ButtonStyle.secondary,
                custom_id=f"eb:{guild_id}:{embed}:{posizione}",
            )
        )
        self.guild_id, self.embed, self.posizione = guild_id, embed, posizione

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["g"]), match["e"], int(match["n"]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        # SEC-10: un bottone dinamico non ha una BaseView sopra di sé, il controllo blacklist si fa qui.
        return not await _utente_o_server_in_blacklist(interaction)

    async def callback(self, interaction: discord.Interaction) -> None:
        lingua = await lingua_interazione(interaction)
        if interaction.guild is None or interaction.guild.id != self.guild_id:
            return
        innesco = await tag_inneschi_repo.bottone(self.guild_id, self.embed, self.posizione)
        cog = interaction.client.get_cog("CustomCommandsCog")
        if innesco is not None and cog is not None and isinstance(interaction.user, discord.Member):
            # innesco «bottone» (B27): il tag risponde nel canale, davanti a tutti; a chi preme resta un avviso privato
            await interaction.response.defer(ephemeral=True)
            motivo = await cog.esegui_innesco(interaction.guild, innesco["tag"], interaction.channel, membro=interaction.user)
            await interaction.followup.send(t(motivo or "inn_bottone_fatto", lingua), ephemeral=True)
            return
        b = await embed_bottoni_repo.prendi(self.guild_id, self.embed, self.posizione)
        tag = await custom_command_repo.get_tag(self.guild_id, b.valore) if b and b.tipo == "tag" else None
        if tag is None:
            await interaction.response.send_message(t("bottoni_tag_sparito", lingua), ephemeral=True)
            return
        testo = tag.response
        if cog is not None and isinstance(interaction.user, discord.Member):
            await interaction.response.defer(ephemeral=True)
            testo, _ = await cog._prepara(tag, interaction.user, interaction.channel, "")
            await interaction.followup.send(testo[:2000], ephemeral=True, allowed_mentions=_NESSUNA)
            return
        await interaction.response.send_message(testo[:2000], ephemeral=True, allowed_mentions=_NESSUNA)


def _pulsanti(guild_id: int, embed: str, bottoni) -> list[discord.ui.Item]:
    voci: list[discord.ui.Item] = []
    for b in bottoni[:MAX_BOTTONI]:
        if b.tipo == "link":
            voci.append(discord.ui.Button(label=b.etichetta[:80], url=b.valore[:512]))
        else:
            voci.append(BottoneTag(guild_id, embed, b.posizione, b.etichetta))
    return voci


def costruisci_v2(dati: DatiEmbed, voci: list[discord.ui.Item]) -> discord.ui.LayoutView:
    """Un contenitore con testo, galleria e piede; i bottoni in righe da 5 sotto il contenitore."""
    colore = L.colore_valido(dati.color) if dati.color else None
    figli: list[discord.ui.Item] = []
    testa = "\n".join(x for x in (f"## {dati.title}" if dati.title else "", dati.description or "") if x)
    if testa:
        if dati.thumbnail_url:
            figli.append(discord.ui.Section(testa, accessory=discord.ui.Thumbnail(dati.thumbnail_url)))
        else:
            figli.append(discord.ui.TextDisplay(testa))
    for nome, valore, _ in dati.fields:
        figli.append(discord.ui.TextDisplay(f"**{nome}**\n{valore}"))
    if dati.image_url:
        figli.append(discord.ui.MediaGallery(discord.MediaGalleryItem(dati.image_url)))
    if dati.footer:
        figli.append(discord.ui.TextDisplay(f"-# {dati.footer}"))
    vista = BaseLayoutView(timeout=None)
    vista.add_item(discord.ui.Container(*figli, accent_colour=int(colore[1:], 16) if colore else None))
    for i in range(0, len(voci), 5):
        riga = discord.ui.ActionRow()
        for voce in voci[i : i + 5]:
            riga.add_item(voce)
        vista.add_item(riga)
    return vista


async def contenuto_messaggio(guild_id: int, nome: str, dati: DatiEmbed, formato: str) -> dict:
    """Gli argomenti di send/edit per l'embed `nome`: classico (embed + bottoni) oppure V2 (solo vista)."""
    voci = _pulsanti(guild_id, nome, await embed_bottoni_repo.elenco(guild_id, nome))
    if formato == "v2":
        return {"view": costruisci_v2(dati, voci)}
    contenuto: dict = {"embed": costruisci(dati)}
    if voci:
        vista = BaseView(timeout=None)
        for v in voci:
            vista.add_item(v)
        contenuto["view"] = vista
    return contenuto


async def indirizzi_non_ammessi(dati: DatiEmbed) -> str | None:
    for etichetta, url in (("immagine", dati.image_url), ("miniatura", dati.thumbnail_url)):
        if url and not await url_e_sicuro(url):
            return f"L'indirizzo della {etichetta} non è ammesso (indirizzo interno o porta non consentita)."
    return None


class JsonModal(BaseModal):
    def __init__(self, cog: "EmbedAvanzatiCog", nome: str, lingua: str) -> None:
        super().__init__(title=t("json_titolo", lingua)[:45], timeout=600)
        self.cog, self.nome, self.lingua = cog, nome, lingua
        self.testo = discord.ui.TextInput(
            label=t("json_etichetta", lingua)[:45], style=discord.TextStyle.paragraph, max_length=L.MAX_JSON_FINESTRA
        )
        self.add_item(self.testo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(await self.cog.importa(interaction, self.nome, self.testo.value), ephemeral=True)


class EmbedAvanzatiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await super().cog_load()
        self.bot.add_dynamic_items(BottoneTag)

    async def cog_unload(self) -> None:
        self.bot.remove_dynamic_items(BottoneTag)
        await super().cog_unload()

    async def importa(self, interaction: discord.Interaction, nome: str, testo: str) -> str:
        lingua = await lingua_interazione(interaction)
        dati, errore = L.da_testo_json(testo)
        if dati is None:
            return errore or t("json_illeggibile", lingua)
        errori = valida(dati) or ([e for e in [await indirizzi_non_ammessi(dati)] if e])
        if errori:
            return "L'embed non è valido:\n" + "\n".join(f"• {e}" for e in errori[:10])
        esito = await saved_embed_repo.create(interaction.guild.id, nome, a_json(dati), interaction.user.id)
        return t({"ok": "json_importato", "esiste": "json_esiste", "pieno": "json_pieno"}[esito], lingua, nome=nome, massimo=L.MAX_EMBED)

    @comando_di_gruppo("admin-messaggi", nome="json", descrizione="Importa un embed da un JSON o esportalo in un file.", sottogruppo=SOTTOGRUPPI["admin-messaggi embed"])
    @app_commands.describe(
        azione="Importare o esportare",
        nome=f"Il nome dell'embed salvato (massimo {L.MAX_NOME})",
        file="Importa: il file .json (massimo 1 MiB); senza file si apre una finestra per incollarlo",
        messaggio="Esporta: il link a un messaggio con un embed (senza link si esporta quello salvato)",
    )
    @app_commands.choices(azione=[app_commands.Choice(name="importa", value="importa"), app_commands.Choice(name="esporta", value="esporta")])
    async def json_(
        self,
        interaction: discord.Interaction,
        azione: str,
        nome: app_commands.Range[str, 1, L.MAX_NOME],
        file: discord.Attachment | None = None,
        messaggio: app_commands.Range[str, 1, 200] | None = None,
    ) -> None:
        lingua = await lingua_interazione(interaction)
        nome = normalizza_nome(nome)
        if not nome:
            await interaction.response.send_message(t("json_nome_non_valido", lingua), ephemeral=True)
            return
        if azione == "importa":
            if file is None:
                await interaction.response.send_modal(JsonModal(self, nome, lingua))
                return
            if file.size > L.MAX_JSON_BYTE:
                await interaction.response.send_message(t("json_file_grande", lingua), ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            try:
                testo = (await file.read()).decode("utf-8")
            except (discord.HTTPException, UnicodeDecodeError):
                await interaction.followup.send(t("json_illeggibile", lingua), ephemeral=True)
                return
            await interaction.followup.send(await self.importa(interaction, nome, testo), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        dati = await self._dati_da_esportare(interaction, nome, messaggio)
        if isinstance(dati, str):
            await interaction.followup.send(t(dati, lingua), ephemeral=True)
            return
        contenuto = json.dumps(json.loads(a_json(dati)), ensure_ascii=False, indent=2).encode("utf-8")
        await interaction.followup.send(file=discord.File(io.BytesIO(contenuto), filename=f"{nome}.json"), ephemeral=True)

    async def _dati_da_esportare(self, interaction, nome: str, link: str | None) -> DatiEmbed | str:
        guild = interaction.guild
        if not link:
            salvato = await saved_embed_repo.get(guild.id, nome)
            return L.da_json(salvato.data) if salvato else "json_non_trovato"
        trovati = link_ai_messaggi(link, guild.id)
        canale = guild.get_channel_or_thread(trovati[0][0]) if trovati else None
        if canale is None or not hasattr(canale, "fetch_message"):
            return "json_link_non_valido"
        permessi = canale.permissions_for(interaction.user)
        if not (permessi.view_channel and permessi.read_message_history):
            return "json_link_non_valido"
        try:
            messaggio = await canale.fetch_message(trovati[0][1])
        except discord.HTTPException:
            return "json_link_non_valido"
        return L.embed_di_discord_a_dati(messaggio.embeds[0]) if messaggio.embeds else "json_senza_embed"

    @comando_di_gruppo("admin-messaggi", nome="bottoni", descrizione="Aggiungi o togli i bottoni di un embed (link o mostra tag).", sottogruppo=SOTTOGRUPPI["admin-messaggi embed"])
    @app_commands.describe(
        azione="Cosa fare",
        nome="L'embed salvato",
        tipo="Aggiungi: link o tag (di base link)",
        etichetta=f"Aggiungi: il testo sul bottone (massimo {L.MAX_TESTO_BOTTONE})",
        valore="Aggiungi: l'indirizzo (link) o il nome del tag",
        numero="Togli: il numero del bottone (vedi elenco)",
    )
    @app_commands.choices(
        azione=[app_commands.Choice(name=n, value=n) for n in ("aggiungi", "togli", "elenco")],
        tipo=[app_commands.Choice(name="link", value="link"), app_commands.Choice(name="tag", value="tag")],
    )
    async def bottoni(
        self,
        interaction: discord.Interaction,
        azione: str,
        nome: app_commands.Range[str, 1, L.MAX_NOME],
        tipo: str = "link",
        etichetta: app_commands.Range[str, 1, L.MAX_TESTO_BOTTONE] | None = None,
        valore: app_commands.Range[str, 1, 512] | None = None,
        numero: app_commands.Range[int, 1, MAX_BOTTONI] | None = None,
    ) -> None:
        lingua = await lingua_interazione(interaction)
        gid = interaction.guild.id
        nome = normalizza_nome(nome) or nome.lower()
        salvato = await saved_embed_repo.get(gid, nome)
        if salvato is None:
            await interaction.response.send_message(t("bottoni_embed_non_trovato", lingua), ephemeral=True)
            return
        if azione == "elenco":
            righe = [f"{b.posizione + 1}. [{b.tipo}] {b.etichetta[:80]} → {b.valore[:100]}" for b in await embed_bottoni_repo.elenco(gid, nome)]
            await interaction.response.send_message(("\n".join(righe) or t("bottoni_nessuno", lingua))[:2000], ephemeral=True, allowed_mentions=_NESSUNA)
            return
        await interaction.response.defer(ephemeral=True)
        if azione == "togli":
            if numero is None or not await embed_bottoni_repo.togli(gid, nome, numero - 1):
                await interaction.followup.send(t("bottoni_numero_sbagliato", lingua), ephemeral=True)
                return
            esito = t("bottoni_tolto", lingua)
        else:
            errore = L.errore_bottone(tipo, etichetta, valore)
            if errore is None and tipo == "link" and (e_phishing([_host(valore)], carica_lista_locale()) or not await url_e_sicuro(valore)):
                errore = t("bottoni_link_pericoloso", lingua)
            if errore is None and tipo == "tag" and await custom_command_repo.get_tag(gid, normalizza_nome(valore) or "") is None:
                errore = t("bottoni_tag_non_esiste", lingua)
            if errore is not None:
                await interaction.followup.send(errore, ephemeral=True)
                return
            risultato = await embed_bottoni_repo.aggiungi(gid, nome, tipo, etichetta.strip(), valore.strip() if tipo == "link" else normalizza_nome(valore))
            if risultato != "ok":
                await interaction.followup.send(t("bottoni_pieno" if risultato == "pieno" else "bottoni_embed_non_trovato", lingua, massimo=MAX_BOTTONI), ephemeral=True)
                return
            esito = t("bottoni_aggiunto", lingua)
        if salvato.formato == "v2":
            errori = L.valida_v2(L.da_json(salvato.data), len(await embed_bottoni_repo.elenco(gid, nome)))
            if errori:
                esito += "\n" + errori[0]
        esito += await self._aggiorna_messaggio(interaction.guild, salvato, lingua)
        await interaction.followup.send(esito[:2000], ephemeral=True)

    async def _aggiorna_messaggio(self, guild: discord.Guild, salvato, lingua: str) -> str:
        """Se l'embed è già pubblicato ne aggiorna i bottoni. Testo da accodare alla risposta."""
        if salvato.message_id is None or salvato.channel_id is None:
            return ""
        canale = guild.get_channel(salvato.channel_id)
        if canale is None:
            return ""
        try:
            messaggio = await canale.fetch_message(salvato.message_id)
            contenuto = await contenuto_messaggio(guild.id, salvato.name, L.da_json(salvato.data), salvato.formato)
            contenuto.pop("embed", None)
            if "view" not in contenuto:
                contenuto["view"] = BaseView(timeout=None)  # nessun bottone rimasto: toglie quelli vecchi
            await messaggio.edit(allowed_mentions=_NESSUNA, **contenuto)
        except discord.HTTPException:
            return " " + t("bottoni_messaggio_non_aggiornato", lingua)
        return " " + t("bottoni_messaggio_aggiornato", lingua)


def _host(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).hostname or ""


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EmbedAvanzatiCog(bot))

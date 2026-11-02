"""
core/automod_liste_pannello.py
==============================
Pannello delle liste con nome dell'AutoMod (`/admin-automod liste`): menu delle liste (al massimo 20 del server
più 3 di sistema in sola lettura), bottoni per aggiungere, togliere ed eliminare, voci a pagine da 50.
Messaggio privato di chi lo apre, dura 14 minuti.
Funzioni coperte: SPEC §6 (AMD-015, AMD-016, AMD-028), D63
"""

from __future__ import annotations

import discord

from core import automod_liste_service as servizio
from core.automod_regole_logic import MAX_LUNG_VOCE, MAX_NOME, MAX_TESTO_PROVA, RegolaNonValida
from core.automod_regole_pannello import DURATA_PANNELLO_S, ModaleCampi, campo, opz
from core.i18n import lingua_interazione, t

VOCI_PER_PAGINA = 50


class PannelloListe(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, lingua: str):
        super().__init__(timeout=DURATA_PANNELLO_S)
        self.guild_id = interaction.guild.id
        self.autore_id = interaction.user.id
        self.lingua = lingua
        self.liste: dict[str, tuple[str, tuple[str, ...]]] = {}
        self.scelta: str | None = None
        self.pagina = 0
        self.messaggio = ""
        self.elimina_armato = False

    def tx(self, chiave: str, **valori) -> str:
        return t(f"amliste_{chiave}", self.lingua, **valori)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.autore_id

    async def carica(self) -> None:
        self.liste = {n: servizio.lista_di_sistema(n) for n in servizio.LISTE_DI_SISTEMA}
        self.liste.update(await servizio.liste_del_server(self.guild_id))
        if self.scelta not in self.liste:
            self.scelta = None

    def _di_sistema(self) -> bool:
        return bool(self.scelta) and self.scelta.startswith("@")

    def schermata(self) -> discord.Embed:
        self.clear_items()
        menu = discord.ui.Select(custom_id="am:l:sel", placeholder=self.tx("ph_lista"), options=[
            opz(("🔒 " if n.startswith("@") else "") + n, n, self.tx("tipo_" + tipo), default=n == self.scelta)
            for n, (tipo, _) in self.liste.items()][:25])
        menu.callback = self._scelta
        self.add_item(menu)
        sistema = self._di_sistema()
        for etichetta, id_, fn, off, stile in (
            (self.tx("btn_nuova"), "am:l:nuova", self._nuova, False, discord.ButtonStyle.primary),
            (self.tx("btn_aggiungi"), "am:l:agg", self._aggiungi, self.scelta is None or sistema, discord.ButtonStyle.secondary),
            (self.tx("btn_togli"), "am:l:togli", self._togli, self.scelta is None or sistema, discord.ButtonStyle.secondary),
            (self.tx("btn_elimina_si" if self.elimina_armato else "btn_elimina"), "am:l:elimina", self._elimina,
             self.scelta is None or sistema, discord.ButtonStyle.danger),
        ):
            b = discord.ui.Button(label=etichetta[:45], custom_id=id_, disabled=off, style=stile)
            b.callback = fn
            self.add_item(b)
        embed = discord.Embed(title=self.tx("titolo_pannello"), color=discord.Color.orange())
        if self.scelta is None:
            embed.description = self.tx("scegli") if self.liste else self.tx("nessuna_lista")
        else:
            tipo, voci = self.liste[self.scelta]
            pagine = max(1, -(-len(voci) // VOCI_PER_PAGINA))
            self.pagina = min(self.pagina, pagine - 1)
            blocco = voci[self.pagina * VOCI_PER_PAGINA:(self.pagina + 1) * VOCI_PER_PAGINA]
            embed.title = self.tx("titolo_lista", nome=self.scelta, tipo=self.tx("tipo_" + tipo), n=len(voci))[:256]
            embed.description = ("\n".join(f"• {v}" for v in blocco) or self.tx("vuota"))[:4000]
            embed.set_footer(text=self.tx("pagina", pagina=self.pagina + 1, pagine=pagine))
            for etichetta, id_, delta, off in (("◀", "am:l:prec", -1, self.pagina == 0), ("▶", "am:l:succ", 1, self.pagina >= pagine - 1)):
                b = discord.ui.Button(label=etichetta, custom_id=id_, disabled=off)
                b.callback = self._pagina(delta)
                self.add_item(b)
        if self.messaggio:
            embed.add_field(name="ℹ️", value=self.messaggio[:1024], inline=False)
        return embed

    async def _ridisegna(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(embed=self.schermata(), view=self)

    async def _scelta(self, interaction: discord.Interaction) -> None:
        self.scelta, self.pagina, self.messaggio, self.elimina_armato = interaction.data["values"][0], 0, "", False
        await self._ridisegna(interaction)

    def _pagina(self, delta: int):
        async def callback(interaction: discord.Interaction) -> None:
            self.pagina = max(0, self.pagina + delta)
            await self._ridisegna(interaction)

        return callback

    async def _esito(self, interaction: discord.Interaction, azione) -> None:
        try:
            self.messaggio = await azione()
        except RegolaNonValida as errore:
            self.messaggio = self.tx("errore", testo=str(errore))
        await self.carica()
        await self._ridisegna(interaction)

    async def _nuova(self, interaction: discord.Interaction) -> None:
        async def invio(i, v):
            async def fa():
                voci = servizio.leggi_voci(v["voci"])
                await servizio.salva_lista(self.guild_id, v["nome"], v["tipo"].strip().lower() or "parole", voci)
                self.scelta = v["nome"].strip()
                return self.tx("creata", n=len(voci))

            await self._esito(i, fa)

        await interaction.response.send_modal(ModaleCampi(self.tx("modale_nuova"), [
            campo("nome", self.tx("f_nome"), MAX_NOME), campo("tipo", self.tx("f_tipo"), 8, "parole", segnaposto="parole / domini"),
            campo("voci", self.tx("f_voci"), MAX_TESTO_PROVA, lungo=True)], invio))

    async def _aggiungi(self, interaction: discord.Interaction) -> None:
        async def invio(i, v):
            async def fa():
                voci = await servizio.aggiungi_voci(self.guild_id, self.scelta, servizio.leggi_voci(v["voci"]))
                return self.tx("aggiunte", n=len(voci))

            await self._esito(i, fa)

        await interaction.response.send_modal(ModaleCampi(self.tx("modale_aggiungi"), [
            campo("voci", self.tx("f_voci"), MAX_TESTO_PROVA, lungo=True)], invio))

    async def _togli(self, interaction: discord.Interaction) -> None:
        async def invio(i, v):
            async def fa():
                voci = await servizio.togli_voci(self.guild_id, self.scelta, servizio.leggi_voci(v["voci"]))
                return self.tx("tolte", n=len(voci))

            await self._esito(i, fa)

        await interaction.response.send_modal(ModaleCampi(self.tx("modale_togli"), [
            campo("voci", self.tx("f_voci"), MAX_TESTO_PROVA, lungo=True)], invio))

    async def _elimina(self, interaction: discord.Interaction) -> None:
        if not self.elimina_armato:
            self.elimina_armato = True
            await self._ridisegna(interaction)
            return
        await servizio.elimina_lista(self.guild_id, self.scelta)
        self.scelta, self.elimina_armato, self.messaggio = None, False, self.tx("eliminata")
        await self.carica()
        await self._ridisegna(interaction)


async def apri_liste(interaction: discord.Interaction, lista: str | None = None) -> None:
    vista = PannelloListe(interaction, await lingua_interazione(interaction))
    await vista.carica()
    if lista in vista.liste:
        vista.scelta = lista
    await interaction.response.send_message(embed=vista.schermata(), view=vista, ephemeral=True)

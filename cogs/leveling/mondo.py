"""
cogs/leveling/mondo.py
======================
/mondo: diretta (serie giornaliera), casa con i gettoni (seconda moneta globale), fattoria, personaggi con
una domanda al giorno, avventura a scelte, borsa finta con ordini a soglia, vendita automatica, vacanza della serie.
Per lo staff, in /admin-negozio: codice in chat, bonus a tempo da raccogliere, eventi casuali del server.
Un lavoro orario fa avanzare la borsa, vende gli oggetti con la soglia raggiunta e lancia gli eventi casuali.
Funzioni coperte: ECO-018, 027, 045, 054, 056, 083, 084, 085, 087, 142, 144, 145, 146, 147
Dipende da: core/repositories/mondo_repo.py, core/mondo_logic.py
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.leveling.leveling import _comando_rifiutato
from core import mondo_logic as ml
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_guild, testo_per
from core.leveling_logic import tasso_del_giorno
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.mondo_repo import COSTO_VACANZA_GIORNO, VACANZA_GIORNI_MAX, mondo_repo
from core.ui_base import BaseModal, BaseView

logger = logging.getLogger("iyokai.mondo")
RNG = random.SystemRandom()
NESSUNA_MENZIONE = discord.AllowedMentions.none()
SG_BORSA = ("borsa", "Borsa finta: prezzi, scambi e ordini")
SG_EVENTO = ("evento", "Eventi in chat: codice, bonus a tempo e casuali")
PAUSA_AVVENTURA = 6 * 3600
SIMBOLI = [app_commands.Choice(name=s, value=s) for s in ml.SIMBOLI]
LATI = [app_commands.Choice(name="compra", value="compra"), app_commands.Choice(name="vendi", value="vendi")]
COLTURE = [app_commands.Choice(name=c, value=c) for c in ml.COLTURE]
MOBILI = [app_commands.Choice(name=m, value=m) for m in ml.MOBILI]
NPC = [app_commands.Choice(name=p["nome"][:100], value=str(i)) for i, p in enumerate(ml.personaggi())]


class VistaScelte(BaseView):
    """Bottoni a scelta per una sola persona (missione, avventura): solo chi ha dato il comando preme."""

    def __init__(self, autore: int, scelte: list[tuple[str, object]], azione, secondi: int = 90) -> None:
        super().__init__(timeout=secondi)
        self.autore, self.azione = autore, azione
        for etichetta, valore in scelte[:5]:
            b = discord.ui.Button(label=etichetta[:80], style=discord.ButtonStyle.primary)
            b.callback = self._premuto(valore)
            self.add_item(b)

    def _premuto(self, valore):
        async def callback(interaction: discord.Interaction) -> None:
            if interaction.user.id != self.autore:
                await interaction.response.send_message(await testo_per(interaction, "sfd_non_tuo"), ephemeral=True)
                return
            self.stop()  # una scelta sola
            await self.azione(interaction, valore)
        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await super().interaction_check(interaction)


class ModaleCodice(BaseModal):
    def __init__(self, evento_id: int, titolo: str, etichetta: str) -> None:
        super().__init__(title=titolo[:45])
        self.evento_id = evento_id
        self.codice = discord.ui.TextInput(label=etichetta[:45], min_length=1, max_length=20, required=True)
        self.add_item(self.codice)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await prendi(interaction, self.evento_id, self.codice.value)


async def prendi(interaction: discord.Interaction, evento_id: int, codice: str | None) -> None:
    esito, dati = await mondo_repo.prendi_evento(interaction.guild.id, evento_id, interaction.user.id, codice)
    if esito != "ok":
        await interaction.response.send_message(await testo_per(interaction, f"mon_evento_{esito}"), ephemeral=True)
        return
    moneta = (await leveling_settings_repo.get_config(interaction.guild.id)).impostazioni.currency_name
    await interaction.response.send_message(
        await testo_per(interaction, f"mon_preso_{dati['tipo']}", pubblica=True, chi=interaction.user.mention, monete=dati["monete"], moneta=moneta,
                        percento=dati["percento"], minuti=dati["minuti"]), allowed_mentions=discord.AllowedMentions(users=[interaction.user]),
    )


class VistaEvento(BaseView):
    """Il primo che preme il bottone (o scrive il codice giusto) vince; il resto lo decide il database."""

    def __init__(self, evento_id: int, con_codice: bool, etichetta: str, titolo: str, campo: str, secondi: int) -> None:
        super().__init__(timeout=secondi)
        self.evento_id, self.con_codice, self.titolo, self.campo = evento_id, con_codice, titolo, campo
        self.prendi.label = etichetta[:45]

    @discord.ui.button(style=discord.ButtonStyle.success, label="…")
    async def prendi(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.con_codice:
            await interaction.response.send_modal(ModaleCodice(self.evento_id, self.titolo, self.campo))
        else:
            await prendi(interaction, self.evento_id, None)


async def pubblica_evento(canale, guild_id: int, tipo: str, codice, monete: int, percento: int, minuti: int, scade_min: int, autore: int) -> bool:
    """Crea l'evento e lo annuncia nel canale (messaggio pubblico: lingua del server)."""
    evento_id = await mondo_repo.crea_evento(guild_id, tipo, codice, monete, percento, minuti, scade_min, autore)

    async def t(chiave, **kw):
        return await testo_guild(guild_id, chiave, **kw)

    moneta = (await leveling_settings_repo.get_config(guild_id)).impostazioni.currency_name
    vista = VistaEvento(evento_id, tipo == "codice", await t("mon_bottone_" + tipo), await t("mon_codice_titolo"), await t("mon_codice_campo"), max(1, scade_min) * 60)
    testo = await t("mon_annuncio_" + tipo, codice=codice or "", monete=monete, moneta=moneta, percento=percento, minuti=minuti, scade=scade_min)
    try:
        await canale.send(testo[:2000], view=vista, allowed_mentions=NESSUNA_MENZIONE)
    except discord.HTTPException:
        return False
    return True


class MondoCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._giro.start()

    def cog_unload(self) -> None:
        self._giro.cancel()
        togli_comandi_del_cog(self)

    async def _moneta(self, g: int) -> str:
        return (await leveling_settings_repo.get_config(g)).impostazioni.currency_name

    # ------------------------------------------------------------------ lavoro orario
    @tasks.loop(hours=1)
    async def _giro(self) -> None:
        oggi = datetime.now(timezone.utc).date()
        for nome, f in (
            ("borsa", mondo_repo.prezzi),
            ("autovendite", lambda: mondo_repo.autovendite_del_giorno(lambda g: tasso_del_giorno(g, oggi))),
            ("pulizia", mondo_repo.pulisci),
            ("eventi", self._eventi_casuali),
        ):
            try:
                await f()
            except Exception:
                logger.exception("Giro orario di /mondo: %s", nome)

    @_giro.before_loop
    async def _prima(self) -> None:
        await self.bot.wait_until_ready()

    async def _eventi_casuali(self) -> None:
        """ECO-144/145: nei server che li hanno accesi, ogni 6 ore circa, una volta su tre, un bonus del server o un evento raro."""
        for r in await mondo_repo.eventi_pronti():
            if RNG.random() > 1 / 3:
                continue
            canale = self.bot.get_channel(r["canale_id"])
            if canale is None or not hasattr(canale, "send"):
                continue
            if RNG.random() < 0.7:
                percento = RNG.choice([25, 50])
                await mondo_repo.bonus_server(r["guild_id"], percento, 60)
                await canale.send(await testo_guild(r["guild_id"], "mon_evento_bonus_server", percento=percento, minuti=60), allowed_mentions=NESSUNA_MENZIONE)
            else:
                await pubblica_evento(canale, r["guild_id"], "raro", None, 200, 0, 0, 10, 0)

    # ------------------------------------------------------------------ giocatori
    @comando_di_gruppo("mondo", nome="diretta", descrizione="La tua diretta di oggi: più giorni di fila, più monete.")
    async def diretta(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        esito = await mondo_repo.diretta(interaction.guild.id, interaction.user.id, datetime.now(timezone.utc).date())
        if esito is None:
            await interaction.response.send_message(await testo_per(interaction, "mon_diretta_gia"), ephemeral=True)
            return
        serie, monete = esito
        await interaction.response.send_message(await testo_per(interaction, "mon_diretta_ok", serie=serie, monete=monete, moneta=await self._moneta(interaction.guild.id), pubblica=True))

    @comando_di_gruppo("mondo", nome="vacanza", descrizione="Ferma la serie del premio giornaliero mentre sei via.")
    @app_commands.describe(giorni=f"Giorni (1-{VACANZA_GIORNI_MAX}), {COSTO_VACANZA_GIORNO} monete al giorno")
    async def vacanza(self, interaction: discord.Interaction, giorni: app_commands.Range[int, 1, VACANZA_GIORNI_MAX]) -> None:
        if await _comando_rifiutato(interaction):
            return
        esito = await mondo_repo.compra_vacanza(interaction.guild.id, interaction.user.id, giorni)
        await interaction.response.send_message(
            await testo_per(interaction, f"mon_vacanza_{esito}", giorni=giorni, costo=giorni * COSTO_VACANZA_GIORNO, moneta=await self._moneta(interaction.guild.id)), ephemeral=esito != "ok"
        )

    @comando_di_gruppo("mondo", nome="casa", descrizione="La tua casa: arredala con i gettoni (la moneta di tutti i server).")
    @app_commands.describe(compra="Il mobile da comprare (senza scelta vedi la casa)")
    @app_commands.choices(compra=MOBILI)
    async def casa(self, interaction: discord.Interaction, compra: app_commands.Choice[str] | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        u = interaction.user.id
        if compra is not None:
            esito = await mondo_repo.compra_mobile(u, compra.value)
            if esito != "ok":
                await interaction.response.send_message(await testo_per(interaction, f"mon_casa_{esito}", costo=ml.MOBILI[compra.value][0]), ephemeral=True)
                return
        posseduti = await mondo_repo.casa(u)
        listino = ", ".join(f"{e} {n} ({c})" for n, (c, e, _) in ml.MOBILI.items() if n not in posseduti)
        await interaction.response.send_message(
            await testo_per(interaction, "mon_casa", stanza=ml.disegna_casa(posseduti), gettoni=await mondo_repo.gettoni(u), listino=listino or "-"), ephemeral=True
        )

    @comando_di_gruppo("mondo", nome="fattoria", descrizione="Pianta nel tuo orto e raccogli quando è maturo (3 posti).")
    @app_commands.describe(posto="Il posto dove piantare (1-3)", coltura="Cosa piantare", raccogli="Raccogli quello che è maturo")
    @app_commands.choices(coltura=COLTURE)
    async def fattoria(
        self, interaction: discord.Interaction, posto: app_commands.Range[int, 1, ml.POSTI_FATTORIA] | None = None,
        coltura: app_commands.Choice[str] | None = None, raccogli: bool = False,
    ) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        moneta = await self._moneta(g)
        if raccogli:
            colture, totale = await mondo_repo.raccogli(g, u)
            if not colture:
                await interaction.response.send_message(await testo_per(interaction, "mon_fattoria_niente"), ephemeral=True)
                return
            await interaction.response.send_message(await testo_per(interaction, "mon_fattoria_raccolto", n=len(colture), monete=totale, moneta=moneta), ephemeral=True)
            return
        if posto is not None and coltura is not None:
            esito = await mondo_repo.pianta(g, u, posto, coltura.value)
            if esito != "ok":
                await interaction.response.send_message(await testo_per(interaction, f"mon_fattoria_{esito}", costo=ml.COLTURE[coltura.value][0], moneta=moneta), ephemeral=True)
                return
        adesso = datetime.now(timezone.utc)
        righe = [
            f"{r['posto']}. {r['coltura']} — " + ("✅" if ml.pronto(r["piantato_at"], adesso, r["coltura"]) else f"<t:{int(r['piantato_at'].timestamp()) + ml.COLTURE[r['coltura']][1] * 3600}:R>")
            for r in await mondo_repo.orto(g, u)
        ]
        listino = ", ".join(f"{n}: {c} → {y} in {h} h" for n, (c, h, y) in ml.COLTURE.items())
        await interaction.response.send_message(await testo_per(interaction, "mon_fattoria", orto="\n".join(righe) or "-", listino=listino, moneta=moneta), ephemeral=True)

    @comando_di_gruppo("mondo", nome="personaggio", descrizione="Parla con un personaggio: una domanda al giorno, un regalo se rispondi bene.")
    @app_commands.describe(chi="Con chi parli")
    @app_commands.choices(chi=NPC)
    async def personaggio(self, interaction: discord.Interaction, chi: app_commands.Choice[str]) -> None:
        if await _comando_rifiutato(interaction):
            return
        p = ml.personaggi()[int(chi.value)]
        g, u = interaction.guild.id, interaction.user.id
        moneta = await self._moneta(g)

        async def risposta(i: discord.Interaction, indice: int) -> None:
            esito = await mondo_repo.missione(g, u, p["nome"], datetime.now(timezone.utc).date(), indice == p["g"], p["regalo"])
            await i.response.edit_message(content=await testo_per(i, f"mon_npc_{esito}", nome=p["nome"], monete=p["regalo"], moneta=moneta), view=None)

        await interaction.response.send_message(
            await testo_per(interaction, "mon_npc", nome=p["nome"], testo=p["saluto"]), ephemeral=True,
            view=VistaScelte(u, [(r, i) for i, r in enumerate(p["r"])], risposta),
        )

    @comando_di_gruppo("mondo", nome="avventura", descrizione="Una storia a scelte: il finale dà monete (una volta ogni 6 ore).")
    async def avventura(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        storia = ml.avventura()
        moneta = await self._moneta(g)

        def vista(nodo: str) -> tuple[str, discord.ui.View | None]:
            n = storia["nodi"][nodo]
            if n.get("fine"):
                return n["t"], None
            return n["t"], VistaScelte(u, [(e, nuovo) for e, nuovo in n["s"]], passo, 300)

        async def passo(i: discord.Interaction, nodo: str) -> None:
            testo, v = vista(nodo)
            if v is None:
                n = storia["nodi"][nodo]
                dato = await mondo_repo.finale_avventura(g, u, n["monete"], n["gettoni"], PAUSA_AVVENTURA)
                coda = await testo_per(i, "mon_avv_premio" if dato else "mon_avv_pausa", monete=n["monete"], gettoni=n["gettoni"], moneta=moneta)
                await i.response.edit_message(content=f"{testo}\n{coda}"[:2000], view=None)
                return
            await i.response.edit_message(content=testo, view=v)

        testo, v = vista(storia["inizio"])
        await interaction.response.send_message(testo, view=v, ephemeral=True)

    # ------------------------------------------------------------------ borsa
    @comando_di_gruppo("mondo", nome="prezzi", descrizione="I prezzi della borsa finta e i tuoi titoli.", sottogruppo=SG_BORSA)
    async def borsa_prezzi(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        prezzi = await mondo_repo.prezzi()
        mio = await mondo_repo.portafoglio(interaction.guild.id, interaction.user.id)
        righe = [f"**{s}** {p} (base {ml.SIMBOLI[s]}) · tuoi: {mio.get(s, 0)}" for s, p in prezzi.items()]
        await interaction.response.send_message(await testo_per(interaction, "mon_borsa", righe="\n".join(righe), comm=ml.COMMISSIONE_PCT), ephemeral=True)

    @comando_di_gruppo("mondo", nome="scambia", descrizione="Compra o vendi titoli della borsa finta al prezzo di adesso.", sottogruppo=SG_BORSA)
    @app_commands.describe(titolo="Il titolo", lato="Compra o vendi", quote="Quante quote (1-100)")
    @app_commands.choices(titolo=SIMBOLI, lato=LATI)
    async def borsa_scambia(self, interaction: discord.Interaction, titolo: app_commands.Choice[str], lato: app_commands.Choice[str], quote: app_commands.Range[int, 1, 100]) -> None:
        if await _comando_rifiutato(interaction):
            return
        esito, prezzo = await mondo_repo.scambia(interaction.guild.id, interaction.user.id, titolo.value, quote, lato.value)
        await interaction.response.send_message(
            await testo_per(interaction, f"mon_scambio_{esito}", titolo=titolo.value, quote=quote, prezzo=prezzo, massimo=ml.MAX_QUOTE_PER_TITOLO, lato=lato.value),
            ephemeral=esito != "ok",
        )

    @comando_di_gruppo("mondo", nome="ordine", descrizione="Un ordine automatico: compra o vendi quando il prezzo arriva alla soglia.", sottogruppo=SG_BORSA)
    @app_commands.describe(titolo="Il titolo", lato="Compra (scatta se il prezzo scende) o vendi (se sale)", quote="Quante quote", soglia="Il prezzo di soglia")
    @app_commands.choices(titolo=SIMBOLI, lato=LATI)
    async def borsa_ordine(self, interaction: discord.Interaction, titolo: app_commands.Choice[str], lato: app_commands.Choice[str], quote: app_commands.Range[int, 1, 100], soglia: app_commands.Range[int, 1, 100000]) -> None:
        if await _comando_rifiutato(interaction):
            return
        esito = await mondo_repo.ordine(interaction.guild.id, interaction.user.id, titolo.value, lato.value, quote, soglia)
        await interaction.response.send_message(await testo_per(interaction, f"mon_ordine_{esito}", massimo=ml.MAX_ORDINI), ephemeral=True)

    @comando_di_gruppo("mondo", nome="ordini", descrizione="I tuoi ordini automatici (con un numero lo annulli).", sottogruppo=SG_BORSA)
    @app_commands.describe(annulla="Numero dell'ordine da annullare")
    async def borsa_ordini(self, interaction: discord.Interaction, annulla: app_commands.Range[int, 1, 9_000_000_000_000_000] | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        if annulla is not None:
            ok = await mondo_repo.togli_ordine(g, u, annulla)
            await interaction.response.send_message(await testo_per(interaction, "mon_ordine_tolto" if ok else "mon_ordine_no"), ephemeral=True)
            return
        righe = [f"`{o['id']}` {o['lato']} {o['quote']}× {o['simbolo']} a {o['soglia']}" for o in await mondo_repo.ordini(g, u)]
        await interaction.response.send_message("\n".join(righe) or await testo_per(interaction, "mon_nessun_ordine"), ephemeral=True)

    @comando_di_gruppo("mondo", nome="autovendita", descrizione="Vendi un oggetto da solo quando il cambio del giorno arriva alla soglia.")
    @app_commands.describe(oggetto="ID dell'oggetto (senza: elenco)", soglia="Cambio minimo, da 40 a 60 (0 = togli la regola)")
    async def autovendita(self, interaction: discord.Interaction, oggetto: app_commands.Range[int, 1, 2_147_483_647] | None = None, soglia: app_commands.Range[int, 0, 60] = 50) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        if oggetto is None:
            righe = [f"`{r['item_id']}` {r['name'][:40]} ≥ {r['soglia']}%" for r in await mondo_repo.autovendite(g, u)]
            await interaction.response.send_message("\n".join(righe) or await testo_per(interaction, "mon_nessuna_regola"), ephemeral=True)
            return
        if soglia == 0:
            ok = await mondo_repo.togli_autovendita(g, u, oggetto)
            await interaction.response.send_message(await testo_per(interaction, "mon_regola_tolta" if ok else "mon_regola_no"), ephemeral=True)
            return
        if soglia < 40:
            await interaction.response.send_message(await testo_per(interaction, "mon_soglia_no"), ephemeral=True)
            return
        esito = await mondo_repo.autovendita(g, u, oggetto, soglia)
        await interaction.response.send_message(await testo_per(interaction, f"mon_regola_{esito}", soglia=soglia), ephemeral=True)

    # ------------------------------------------------------------------ staff
    async def _canale_ok(self, interaction: discord.Interaction, canale) -> bool:
        if not canale.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(await testo_per(interaction, "neg_canale_no"), ephemeral=True)
            return False
        return True

    @comando_di_gruppo("admin-negozio", nome="codice", descrizione="Lancia un codice in chat: chi lo scrive per primo vince le monete.", sottogruppo=SG_EVENTO)
    @app_commands.describe(codice="Il codice da scrivere (lettere e numeri)", monete="Monete in palio", minuti="Quanto dura", canale="Dove lanciarlo (vuoto = qui)")
    async def evento_codice(self, interaction: discord.Interaction, codice: app_commands.Range[str, 3, 20], monete: app_commands.Range[int, 1, 100_000], minuti: app_commands.Range[int, 1, 60] = 10, canale: discord.TextChannel | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        dove = canale or interaction.channel
        if not codice.isascii() or not codice.isalnum() or not await self._canale_ok(interaction, dove):
            if not codice.isascii() or not codice.isalnum():
                await interaction.response.send_message(await testo_per(interaction, "mon_codice_no"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ok = await pubblica_evento(dove, interaction.guild.id, "codice", codice, monete, 0, 0, minuti, interaction.user.id)
        await interaction.followup.send(await testo_per(interaction, "neg_lampo_ok" if ok else "neg_canale_no"), ephemeral=True)

    @comando_di_gruppo("admin-negozio", nome="bonus", descrizione="Lascia in chat un bonus a tempo: il primo che lo prende guadagna di più per un po'.", sottogruppo=SG_EVENTO)
    @app_commands.describe(percento="Bonus a lavoro e premio (1-100)", durata="Minuti di bonus (1-1440)", scade="Minuti per prenderlo (1-60)", canale="Dove (vuoto = qui)")
    async def evento_bonus(self, interaction: discord.Interaction, percento: app_commands.Range[int, 1, 100], durata: app_commands.Range[int, 1, 1440] = 60, scade: app_commands.Range[int, 1, 60] = 10, canale: discord.TextChannel | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        dove = canale or interaction.channel
        if not await self._canale_ok(interaction, dove):
            return
        await interaction.response.defer(ephemeral=True)
        ok = await pubblica_evento(dove, interaction.guild.id, "bonus", None, 0, percento, durata, scade, interaction.user.id)
        await interaction.followup.send(await testo_per(interaction, "neg_lampo_ok" if ok else "neg_canale_no"), ephemeral=True)

    @comando_di_gruppo("admin-negozio", nome="casuali", descrizione="Accendi o spegni gli eventi casuali del server in un canale.", sottogruppo=SG_EVENTO)
    @app_commands.describe(canale="Dove annunciarli", attivi="Sì = accesi")
    async def evento_casuali(self, interaction: discord.Interaction, canale: discord.TextChannel, attivi: bool = True) -> None:
        if await _comando_rifiutato(interaction):
            return
        if attivi and not await self._canale_ok(interaction, canale):
            return
        await mondo_repo.imposta_eventi(interaction.guild.id, canale.id, attivi)
        await interaction.response.send_message(await testo_per(interaction, "mon_casuali_ok" if attivi else "mon_casuali_off"), ephemeral=True)

    @comando_di_gruppo("admin-negozio", nome="server", descrizione="Bonus a tempo per tutto il server, subito (lavoro e premio).", sottogruppo=SG_EVENTO)
    @app_commands.describe(percento="Bonus (1-100)", minuti="Durata in minuti (1-1440)")
    async def evento_server(self, interaction: discord.Interaction, percento: app_commands.Range[int, 1, 100], minuti: app_commands.Range[int, 1, 1440]) -> None:
        if await _comando_rifiutato(interaction):
            return
        await mondo_repo.bonus_server(interaction.guild.id, percento, minuti)
        await interaction.response.send_message(await testo_per(interaction, "mon_server_ok", percento=percento, minuti=minuti), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MondoCog(bot))

"""
cogs/fun/animali_avanzati.py
============================
Animali avanzati (/fun animali sitter, lotta, incontro, abbandona, adozioni, adotta) e pesca avanzata
(/fun pesca abilita, attrezzi, stagione, rete, acquario, storico). Nessuna puntata: monete solo dalle
casse e dalle riscossioni già previste; gli scambi tra utenti rispettano il blocco personale.
Funzioni coperte: ECO-125, 126, 127, 128, 129, 135, 136, 137, 139, 140, 141
Dipende da: core/repositories/animali_avanzati_repo.py, core/repositories/pesca_repo.py
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fun.animali import IdAnimale, SG_ANIMALI, SG_PESCA
from cogs.leveling.leveling import _comando_rifiutato
from core import animali_avanzati_logic as lg
from core.animali_logic import LUOGHI_PESCA, PESCI, livello
from core.command_groups import CogConGruppi, comando_di_gruppo, togli_comandi_del_cog
from core.i18n import testo_per
from core.repositories.animali_avanzati_repo import animali_avanzati_repo
from core.repositories.animali_repo import animali_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from core.repositories.pesca_repo import pesca_repo
from core.repositories.sociale_repo import sociale_repo
from core.ui_base import BaseView

RNG = random.SystemRandom()
NESSUNA_MENZIONE = discord.AllowedMentions.none()
ABILITA_SCELTE = [app_commands.Choice(name=a, value=a) for a in lg.ABILITA]
ATTREZZI_SCELTE = [app_commands.Choice(name=n, value=n) for n in ("esca", "rete", "canna")]


class IncontroView(BaseView):
    """L'altro giocatore accetta l'incontro con un bottone che solo lui può premere (60 s)."""

    def __init__(self, guild_id: int, mio_id: int, mio_user: int, suo_id: int, suo_user: int, etichetta: str) -> None:
        super().__init__(timeout=60)
        self.dati = (guild_id, mio_id, mio_user, suo_id, suo_user)
        self._usata = False
        self.accetta.label = etichetta[:45]

    @discord.ui.button(style=discord.ButtonStyle.success, label="…")
    async def accetta(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        g, mio_id, mio_user, suo_id, suo_user = self.dati
        if interaction.user.id != suo_user:
            await interaction.response.send_message(await testo_per(interaction, "sfd_solo_sfidato"), ephemeral=True)
            return
        if self._usata:  # nessun await tra controllo e segno
            await interaction.response.send_message(await testo_per(interaction, "leveling_gia_fatto"), ephemeral=True)
            return
        self._usata = True
        self.stop()
        animali = {r["id"]: r for r in [*await animali_repo.elenco(g, mio_user), *await animali_repo.elenco(g, suo_user)]}
        specie = lg.specie_cucciolo(RNG, animali[mio_id]["specie"], animali[suo_id]["specie"]) if mio_id in animali and suo_id in animali else "gatto"
        esito, nato = await animali_avanzati_repo.incontro(
            g, datetime.now(timezone.utc).date(), mio_id, mio_user, suo_id, suo_user, lg.nasce_cucciolo(RNG), specie
        )
        chiave = "ava_incontro_nato" if nato else f"ava_incontro_{esito}"
        await interaction.response.edit_message(content=await testo_per(interaction, chiave, pubblica=True), view=None)


class AnimaliAvanzatiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        togli_comandi_del_cog(self)

    async def _moneta(self, guild_id: int) -> str:
        return (await leveling_settings_repo.get_config(guild_id)).impostazioni.currency_name

    async def _avversario(self, interaction: discord.Interaction, membro: discord.Member, animale_suo: int):
        """Controlli comuni a lotta e incontro: non a se stessi, non ai bot, nessun blocco. Restituisce la riga dell'animale altrui o None."""
        if membro.id == interaction.user.id or membro.bot:
            await interaction.response.send_message(await testo_per(interaction, "sfd_bersaglio"), ephemeral=True)
            return None
        if await sociale_repo.ha_bloccato(membro.id, interaction.user.id) or await sociale_repo.ha_bloccato(interaction.user.id, membro.id):
            await interaction.response.send_message(await testo_per(interaction, "soc_bloccato"), ephemeral=True)
            return None
        suo = next((r for r in await animali_repo.elenco(interaction.guild.id, membro.id) if r["id"] == animale_suo), None)
        if suo is None:
            await interaction.response.send_message(await testo_per(interaction, "ava_non_suo"), ephemeral=True)
        return suo

    # ---------------------------------------------------------------- animali
    @comando_di_gruppo("fun", nome="sitter", descrizione="Paga un pet sitter: i bisogni dell'animale restano pieni per i giorni scelti.", sottogruppo=SG_ANIMALI)
    @app_commands.describe(animale="ID dell'animale", giorni=f"Giorni (1-{lg.SITTER_GIORNI_MAX}), {lg.COSTO_SITTER_GIORNO} monete al giorno")
    async def sitter(self, interaction: discord.Interaction, animale: IdAnimale, giorni: app_commands.Range[int, 1, lg.SITTER_GIORNI_MAX]) -> None:
        if await _comando_rifiutato(interaction):
            return
        esito = await animali_avanzati_repo.sitter(interaction.guild.id, interaction.user.id, animale, giorni)
        await interaction.response.send_message(
            await testo_per(interaction, f"ava_sitter_{esito}", costo=lg.costo_sitter(giorni), moneta=await self._moneta(interaction.guild.id)), ephemeral=esito != "ok"
        )

    @comando_di_gruppo("fun", nome="lotta", descrizione="Fai lottare il tuo animale con quello di un altro membro (senza puntata).", sottogruppo=SG_ANIMALI)
    @app_commands.describe(animale="Il tuo animale", membro="L'avversario", suo_animale="ID dell'animale dell'avversario")
    async def lotta(self, interaction: discord.Interaction, animale: IdAnimale, membro: discord.Member, suo_animale: IdAnimale) -> None:
        if await _comando_rifiutato(interaction):
            return
        suo = await self._avversario(interaction, membro, suo_animale)
        if suo is None:
            return
        g = interaction.guild.id
        mio = next((r for r in await animali_repo.elenco(g, interaction.user.id) if r["id"] == animale), None)
        if mio is None:
            await interaction.response.send_message(await testo_per(interaction, "ava_non_tuo"), ephemeral=True)
            return
        forze = {mio["id"]: lg_forza(mio), suo["id"]: lg_forza(suo)}
        from core.sala_logic import lotta as gira_lotta

        vincitore, _ = gira_lotta(forze, RNG)
        esito = await animali_avanzati_repo.lotta(g, mio["id"], interaction.user.id, suo["id"], membro.id, vincitore == mio["id"])
        if esito != "ok":
            await interaction.response.send_message(await testo_per(interaction, f"ava_lotta_{esito}"), ephemeral=True)
            return
        vinto = vincitore == mio["id"]
        await interaction.response.send_message(
            await testo_per(interaction, "ava_lotta_fine", pubblica=True, vincitore=(interaction.user.mention if vinto else membro.mention),
                            nome=(mio if vinto else suo)["nome"][:20]), allowed_mentions=NESSUNA_MENZIONE,
        )

    @comando_di_gruppo("fun", nome="incontro", descrizione="Fai incontrare due animali: giocano insieme e può nascere un cucciolo.", sottogruppo=SG_ANIMALI)
    @app_commands.describe(animale="Il tuo animale", membro="L'altro padrone", suo_animale="ID del suo animale")
    async def incontro(self, interaction: discord.Interaction, animale: IdAnimale, membro: discord.Member, suo_animale: IdAnimale) -> None:
        if await _comando_rifiutato(interaction):
            return
        suo = await self._avversario(interaction, membro, suo_animale)
        if suo is None:
            return
        if not any(r["id"] == animale for r in await animali_repo.elenco(interaction.guild.id, interaction.user.id)):
            await interaction.response.send_message(await testo_per(interaction, "ava_non_tuo"), ephemeral=True)
            return
        etichetta = await testo_per(interaction, "ava_accetta", pubblica=True)
        vista = IncontroView(interaction.guild.id, animale, interaction.user.id, suo_animale, membro.id, etichetta)
        await interaction.response.send_message(
            await testo_per(interaction, "ava_incontro_invito", pubblica=True, chi=interaction.user.mention, altro=membro.mention),
            view=vista, allowed_mentions=discord.AllowedMentions(users=[membro]),
        )

    @comando_di_gruppo("fun", nome="abbandona", descrizione="Lascia un tuo animale nella coda di adozione del server.", sottogruppo=SG_ANIMALI)
    @app_commands.describe(animale="ID dell'animale")
    async def abbandona(self, interaction: discord.Interaction, animale: IdAnimale) -> None:
        if await _comando_rifiutato(interaction):
            return
        esito = await animali_avanzati_repo.abbandona(interaction.guild.id, interaction.user.id, animale)
        await interaction.response.send_message(await testo_per(interaction, f"ava_abbandona_{esito}"), ephemeral=esito != "ok")

    @comando_di_gruppo("fun", nome="adozioni", descrizione="Gli animali in attesa di una famiglia.", sottogruppo=SG_ANIMALI)
    async def adozioni(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        righe = await animali_avanzati_repo.da_adottare(interaction.guild.id)
        testo = "\n".join(f"`{r['id']}` {r['specie']} · {r['nome'][:20]} · lv {livello(r['xp'])}" for r in righe) or await testo_per(interaction, "ava_nessuno")
        await interaction.response.send_message(testo, ephemeral=True)

    @comando_di_gruppo("fun", nome="adotta", descrizione="Adotta un animale della coda (serve un posto libero).", sottogruppo=SG_ANIMALI)
    @app_commands.describe(animale="ID dell'animale (vedi /fun animali adozioni)")
    async def adotta(self, interaction: discord.Interaction, animale: IdAnimale) -> None:
        if await _comando_rifiutato(interaction):
            return
        esito = await animali_avanzati_repo.adotta(interaction.guild.id, interaction.user.id, animale)
        await interaction.response.send_message(await testo_per(interaction, f"ava_adotta_{esito}"), ephemeral=esito != "ok")

    # ---------------------------------------------------------------- pesca avanzata
    @comando_di_gruppo("fun", nome="abilita", descrizione="Le abilità di pesca: si sbloccano con i punti delle sfide.", sottogruppo=SG_PESCA)
    @app_commands.describe(sblocca="L'abilità da sbloccare (senza scelta vedi l'elenco)")
    @app_commands.choices(sblocca=ABILITA_SCELTE)
    async def abilita(self, interaction: discord.Interaction, sblocca: app_commands.Choice[str] | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        if sblocca is not None:
            esito = await pesca_repo.sblocca(g, u, sblocca.value)
            if esito != "ok":
                await interaction.response.send_message(await testo_per(interaction, f"ava_abilita_{esito}"), ephemeral=True)
                return
        p = await pesca_repo.profilo(g, u)
        righe = [f"{'✅' if a in p.abilita else '🔒'} **{a}** ({c}): " + await testo_per(interaction, f"ava_ab_{a}") for a, c in lg.ABILITA.items()]
        righe.append(await testo_per(interaction, "ava_ab_punti", punti=await pesca_repo.punti_liberi(g, u)))
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    @comando_di_gruppo("fun", nome="attrezzi", descrizione="Il negozio di attrezzi: si pagano con le perle che trovi pescando.", sottogruppo=SG_PESCA)
    @app_commands.describe(compra="Cosa comprare (senza scelta vedi i prezzi)")
    @app_commands.choices(compra=ATTREZZI_SCELTE)
    async def attrezzi(self, interaction: discord.Interaction, compra: app_commands.Choice[str] | None = None) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        if compra is not None:
            esito, costo = await pesca_repo.compra_attrezzo(g, u, compra.value)
            if esito != "ok":
                await interaction.response.send_message(await testo_per(interaction, f"ava_attrezzo_{esito}", costo=costo), ephemeral=True)
                return
        p = await pesca_repo.profilo(g, u)
        await interaction.response.send_message(
            await testo_per(interaction, "ava_attrezzi", perle=p.perle, esche=p.esche, canna=p.canna, rete="✅" if p.rete_at else "—",
                            p_esca=lg.PERLE_ESCA, p_rete=lg.PERLE_RETE, p_canna="/".join(map(str, lg.PERLE_CANNA))), ephemeral=True
        )

    @comando_di_gruppo("fun", nome="stagione", descrizione="Il pass del mese: ogni 100 punti di pesca un premio (traccia gratuita).", sottogruppo=SG_PESCA)
    @app_commands.describe(riscuoti="Riscuoti il prossimo livello pronto")
    async def stagione(self, interaction: discord.Interaction, riscuoti: bool = False) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u, oggi = interaction.guild.id, interaction.user.id, datetime.now(timezone.utc).date()
        moneta = await self._moneta(g)
        if riscuoti:
            monete = await pesca_repo.riscuoti_stagione(g, u, oggi)
            if monete is None:
                await interaction.response.send_message(await testo_per(interaction, "ava_stagione_niente"), ephemeral=True)
                return
            await interaction.response.send_message(await testo_per(interaction, "ava_stagione_ok", monete=monete, moneta=moneta), ephemeral=True)
            return
        punti, riscossi = await pesca_repo.stagione_stato(g, u, oggi)
        await interaction.response.send_message(
            await testo_per(interaction, "ava_stagione", punti=punti, livello=lg.livello_stagione(punti), riscossi=riscossi, massimo=lg.LIVELLI_STAGIONE,
                            prossimo=min(lg.LIVELLI_STAGIONE, riscossi + 1) * lg.SOGLIA_STAGIONE), ephemeral=True
        )

    @comando_di_gruppo("fun", nome="rete", descrizione="Raccogli i pesci che la tua rete ha preso mentre eri via (un lancio all'ora).", sottogruppo=SG_PESCA)
    async def rete(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        prese = await pesca_repo.riscuoti_rete(g, u, datetime.now(timezone.utc).date(), lambda n: [lg.pesca_con(RNG, "stagno", set(), False) for _ in range(n)])
        if prese is None:
            await interaction.response.send_message(await testo_per(interaction, "ava_rete_no"), ephemeral=True)
            return
        elenco = ", ".join(f"{PESCI[s][1]} {s}" for s in prese if s) or "-"
        await interaction.response.send_message(await testo_per(interaction, "ava_rete_ok", n=len(prese), elenco=elenco), ephemeral=True)

    @comando_di_gruppo("fun", nome="acquario", descrizione="Il tuo acquario: le specie trovate e quanti ne hai.", sottogruppo=SG_PESCA)
    async def acquario(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        g, u = interaction.guild.id, interaction.user.id
        deposito, visti = await animali_repo.deposito(g, u), await animali_repo.visti(g, u)
        vasca = "\n".join(
            f"🌊 {PESCI[s][1]} {s} ×{deposito.get(s, 0)}" if s in visti else "🌊 ❔ ???" for s in PESCI
        )
        await interaction.response.send_message(f"```\n{'~' * 24}\n{vasca}\n{'~' * 24}\n```"[:1900], ephemeral=False)

    @comando_di_gruppo("fun", nome="storico", descrizione="Gli ultimi pesci presi e le ultime vendite (30 giorni).", sottogruppo=SG_PESCA)
    async def storico(self, interaction: discord.Interaction) -> None:
        if await _comando_rifiutato(interaction):
            return
        righe = await pesca_repo.storico(interaction.guild.id, interaction.user.id)
        testo = "\n".join(
            f"<t:{int(r['quando'].timestamp())}:R> " + (f"🎣 {r['specie']} ({r['valore']})" if r["tipo"] == "pesca" else f"💰 {r['valore']}") for r in righe
        ) or await testo_per(interaction, "pes_nessuno")
        await interaction.response.send_message(testo[:1900], ephemeral=True)


def lg_forza(riga) -> int:
    from core.sala_logic import forza_lottatore

    return forza_lottatore(livello(riga["xp"]))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AnimaliAvanzatiCog(bot))

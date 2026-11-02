"""
core/automod_regole_pannello.py
===============================
Pannello a embed, menu e bottoni per le regole AutoMod (`/admin-automod regole`). Messaggio privato di chi lo apre,
dura 14 minuti. Ogni modifica va in una bozza; «Salva» chiama il punto unico `core/automod_regole_service.py`.
Le finestre hanno al massimo 5 campi, ogni campo ha `max_length`, le etichette stanno sotto i 45 caratteri.
Funzioni coperte: SPEC §6 (AMD-029..056, AMD-067), D63
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import discord

from core import automod_pannello_logic as L
from core import automod_liste_service as servizio_liste
from core import automod_regole_service as servizio
from core.automod_modelli import MODELLI, modello
from core.automod_contesto import contesto_da_membro
from core.automod_regole_logic import (
    AZIONI_CANALE_STAFF_MENU,
    AZIONI_UTENTE_MENU,
    MAX_AVVISO_CANALE,
    MAX_CANCELLA_ULTIMI,
    MAX_NICKNAME,
    MAX_NOME,
    MAX_NOME_THREAD,
    MAX_TESTO_DM,
    MAX_TESTO_PROVA,
    innesco_da_json,
    Contatore,
    Regola,
    RegolaNonValida,
    Soglia,
    azione_da_json,
    azioni_dai_nomi_vecchi,
    condizioni_ok,
)
from core.i18n import lingua_interazione, t

DURATA_PANNELLO_S = 14 * 60  # il token dell'interazione dura 15 minuti
COSA_MODIFICARE = (
    "canali_inclusi", "canali_esclusi", "ruoli_inclusi", "ruoli_esclusi", "utenti_esclusi", "chi", "sanzioni",
    "messaggi", "canale", "contatore", "gruppo", "innesco",
)
SELEZIONI = {  # sezione -> (campo delle condizioni, tipo di menu nativo)
    "canali_inclusi": ("canali_inclusi", "canale"), "canali_esclusi": ("canali_esclusi", "canale"),
    "ruoli_inclusi": ("ruoli_inclusi", "ruolo"), "ruoli_esclusi": ("ruoli_esclusi", "ruolo"),
    "utenti_esclusi": ("utenti_esclusi", "utente"),
}
TIPI_CANALE = [discord.ChannelType.text, discord.ChannelType.voice, discord.ChannelType.category,
               discord.ChannelType.forum, discord.ChannelType.news, discord.ChannelType.stage_voice]


def opz(label: str, value: str, descr: str | None = None, default: bool = False) -> discord.SelectOption:
    return discord.SelectOption(label=label[:80], value=value, description=descr[:100] if descr else None, default=default)


class ModaleCampi(discord.ui.Modal):
    """Una finestra con al massimo 5 campi di testo; `su_invio(interaction, valori)` legge le risposte."""

    def __init__(self, titolo: str, campi: list[discord.ui.TextInput], su_invio):
        super().__init__(title=titolo[:45], timeout=DURATA_PANNELLO_S)
        assert len(campi) <= 5
        self._campi = campi
        self._su_invio = su_invio
        for c in campi:
            self.add_item(c)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._su_invio(interaction, {c.custom_id: c.value for c in self._campi})


def campo(id_: str, etichetta: str, massimo: int, valore: str = "", *, lungo: bool = False, segnaposto: str = "") -> discord.ui.TextInput:
    return discord.ui.TextInput(
        custom_id=id_, label=etichetta[:45], required=False, max_length=massimo, default=(valore or None),
        placeholder=segnaposto[:100] or None,
        style=discord.TextStyle.paragraph if lungo else discord.TextStyle.short,
    )


class PannelloRegole(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, lingua: str, etichette: dict[str, str]):
        super().__init__(timeout=DURATA_PANNELLO_S)
        self.guild = interaction.guild
        self.autore_id = interaction.user.id
        self.lingua = lingua
        self.etichette = etichette  # chiave del filtro -> nome mostrato
        self.categoria = "testo"
        self.pagina = 0
        self.bozza: Regola | None = None
        self.nuova = False
        self.sezione: str | None = None
        self.messaggio = ""
        self.elimina_armato = False
        self.scelta_modello = False
        self.regole: tuple[Regola, ...] = ()

    # ------------------------------------------------------------ utilità
    def tx(self, chiave: str, **valori) -> str:
        return t(f"amregole_{chiave}", self.lingua, **valori)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.autore_id

    def _nome(self, r: Regola) -> str:
        return self.etichette.get(r.chiave, r.nome)

    async def _carica(self) -> None:
        self.regole = await servizio.regole_del_server(self.guild.id)

    async def regola_filtro(self, chiave: str) -> Regola:
        from core.automod_advanced_logic import AZIONI_DI_PARTENZA, AZIONI_DI_PARTENZA_GENERALI
        from core.repositories.automod_advanced_repo import automod_advanced_repo

        impostazioni = await automod_advanced_repo.get_settings(self.guild.id)
        base = azioni_dai_nomi_vecchi(AZIONI_DI_PARTENZA.get(chiave, AZIONI_DI_PARTENZA_GENERALI), impostazioni.mute_duration_seconds)
        regola = await servizio.regola_effettiva(self.guild.id, chiave, base)
        return replace(regola, nome=self.etichette.get(chiave, chiave)[:MAX_NOME])

    # ------------------------------------------------------------ schermata 1: scegli la regola
    def _voci_categoria(self) -> list[tuple[str, str, bool]]:
        """(chiave, nome, accesa) delle regole della categoria."""
        per_chiave = {r.chiave: r for r in self.regole}
        if self.categoria in L.FILTRI_PER_CATEGORIA:
            return [(k, self.etichette.get(k, k), per_chiave[k].attiva if k in per_chiave else True)
                    for k in L.FILTRI_PER_CATEGORIA[self.categoria]]
        return [(r.chiave, r.nome, r.attiva) for r in self.regole
                if r.tipo == "personale" and L.categoria_di_regola(r) == self.categoria]

    def schermata_elenco(self) -> discord.Embed:
        self.clear_items()
        voci, pagine = L.pagina_di(self._voci_categoria(), self.pagina)
        self.pagina = min(self.pagina, pagine - 1)
        cat = discord.ui.Select(custom_id="am:r:cat", placeholder=self.tx("ph_categoria"), options=[
            opz(self.tx(f"cat_{c}"), c, default=c == self.categoria) for c in L.CATEGORIE])
        cat.callback = self._scelta_categoria
        self.add_item(cat)
        if voci:
            reg = discord.ui.Select(custom_id="am:r:reg", placeholder=self.tx("ph_regola"), options=[
                opz(f"{'🟢' if acc else '⚪'} {nome}", chiave) for chiave, nome, acc in voci])
            reg.callback = self._scelta_regola
            self.add_item(reg)
        if self.scelta_modello:
            mod = discord.ui.Select(custom_id="am:r:mod", placeholder=self.tx("ph_modello"),
                                    options=[opz(self.tx(f"mod_{m}"), m) for m in MODELLI])
            mod.callback = self._scelto_modello
            self.add_item(mod)
        for etichetta, id_, fn, off in (
            ("◀", "am:r:prec", self._prec, self.pagina == 0), ("▶", "am:r:succ", self._succ, self.pagina >= pagine - 1),
            (self.tx("btn_nuova"), "am:r:nuova", self._nuova, False),
            (self.tx("btn_modello"), "am:r:modello", self._mostra_modelli, False),
        ):
            b = discord.ui.Button(label=etichetta[:45], custom_id=id_, disabled=off)
            b.callback = fn
            self.add_item(b)
        righe = [f"{'🟢' if acc else '⚪'} {nome}"[:100] for _, nome, acc in voci] or [self.tx("nessuna_regola")]
        embed = discord.Embed(title=self.tx("titolo_elenco", categoria=self.tx(f"cat_{self.categoria}")),
                              description="\n".join(righe), color=discord.Color.orange())
        embed.set_footer(text=self.tx("pagina", pagina=self.pagina + 1, pagine=pagine))
        if self.messaggio:
            embed.add_field(name="ℹ️", value=self.messaggio[:1024], inline=False)
        return embed

    # ------------------------------------------------------------ schermata 2: modifica
    def schermata_regola(self) -> discord.Embed:
        self.clear_items()
        r = self.bozza
        cosa = discord.ui.Select(custom_id="am:r:cosa", placeholder=self.tx("ph_cosa"), options=[
            opz(self.tx(f"cosa_{c}"), c, default=c == self.sezione) for c in COSA_MODIFICARE
            if c != "innesco" or r.tipo == "personale"])
        cosa.callback = self._scelta_cosa
        self.add_item(cosa)
        if self.sezione in SELEZIONI:
            campo_cond, tipo = SELEZIONI[self.sezione]
            self.add_item(self._menu_nativo(tipo, campo_cond))
        for gruppo, tipi, ph, id_ in ((AZIONI_UTENTE_MENU, AZIONI_UTENTE_MENU, "ph_azioni_utente", "am:r:au"),
                                      (AZIONI_CANALE_STAFF_MENU, AZIONI_CANALE_STAFF_MENU, "ph_azioni_canale", "am:r:ac")):
            attive = {a.t for a in r.azioni}
            m = discord.ui.Select(custom_id=id_, placeholder=self.tx(ph), min_values=0, max_values=len(tipi), options=[
                opz(self.tx(f"az_{x}"), x, default=x in attive) for x in tipi])
            m.callback = self._scelta_azioni(gruppo)
            self.add_item(m)
        for etichetta, id_, fn, stile in (
            (self.tx("btn_prova"), "am:r:prova", self._prova, discord.ButtonStyle.secondary),
            (self.tx("btn_spento" if r.attiva else "btn_acceso"), "am:r:onoff", self._onoff, discord.ButtonStyle.secondary),
            (self.tx("btn_salva"), "am:r:salva", self._salva, discord.ButtonStyle.success),
            (self.tx("btn_indietro"), "am:r:indietro", self._indietro, discord.ButtonStyle.secondary),
        ):
            b = discord.ui.Button(label=etichetta[:45], custom_id=id_, style=stile)
            b.callback = fn
            self.add_item(b)
        if r.tipo == "personale" and not self.nuova:
            b = discord.ui.Button(label=self.tx("btn_elimina_si" if self.elimina_armato else "btn_elimina")[:45],
                                  custom_id="am:r:elimina", style=discord.ButtonStyle.danger, row=4)
            b.callback = self._elimina
            self.add_item(b)
        embed = discord.Embed(title=f"{r.nome} ({r.chiave})"[:256], color=discord.Color.orange() if r.attiva else discord.Color.dark_grey())
        for nome, valore in L.campi_embed(r):
            embed.add_field(name=nome, value=valore, inline=False)
        if self.messaggio:
            embed.description = self.messaggio[:1500]
        return embed

    def _menu_nativo(self, tipo: str, campo_cond: str):
        if tipo == "canale":
            m = discord.ui.ChannelSelect(custom_id="am:r:sel", placeholder=self.tx("ph_canali"), min_values=0, max_values=25,
                                         channel_types=TIPI_CANALE)
        elif tipo == "ruolo":
            m = discord.ui.RoleSelect(custom_id="am:r:sel", placeholder=self.tx("ph_ruoli"), min_values=0, max_values=25)
        else:
            m = discord.ui.UserSelect(custom_id="am:r:sel", placeholder=self.tx("ph_utenti"), min_values=0, max_values=25)

        async def callback(interaction: discord.Interaction) -> None:
            ids = tuple(v.id for v in m.values)
            self._condizioni(**{campo_cond: ids})
            await self._ridisegna(interaction)

        m.callback = callback
        return m

    def _condizioni(self, **cambi) -> None:
        self.bozza = replace(self.bozza, condizioni=replace(self.bozza.condizioni, **cambi))

    async def _ridisegna(self, interaction: discord.Interaction) -> None:
        embed = self.schermata_regola() if self.bozza is not None else self.schermata_elenco()
        await interaction.response.edit_message(embed=embed, view=self)

    # ------------------------------------------------------------ callback dell'elenco
    async def _scelta_categoria(self, interaction: discord.Interaction) -> None:
        self.categoria, self.pagina, self.messaggio = interaction.data["values"][0], 0, ""
        await self._carica()
        await self._ridisegna(interaction)

    async def _prec(self, interaction: discord.Interaction) -> None:
        self.pagina = max(0, self.pagina - 1)
        await self._ridisegna(interaction)

    async def _succ(self, interaction: discord.Interaction) -> None:
        self.pagina += 1
        await self._ridisegna(interaction)

    async def _scelta_regola(self, interaction: discord.Interaction) -> None:
        chiave = interaction.data["values"][0]
        if chiave.startswith("p:"):
            self.bozza = next((r for r in self.regole if r.chiave == chiave), None)
        else:
            self.bozza = await self.regola_filtro(chiave)
        self.nuova, self.sezione, self.messaggio, self.elimina_armato = False, None, "", False
        await self._ridisegna(interaction)

    async def _mostra_modelli(self, interaction: discord.Interaction) -> None:
        self.scelta_modello = True
        await self._ridisegna(interaction)

    async def _scelto_modello(self, interaction: discord.Interaction) -> None:
        chiave = interaction.data["values"][0]
        self.bozza = modello(chiave, self.tx(f"mod_{chiave}"))
        self.nuova, self.sezione, self.messaggio, self.scelta_modello = True, None, "", False
        await self._ridisegna(interaction)

    async def _nuova(self, interaction: discord.Interaction) -> None:
        async def invio(i: discord.Interaction, v: dict) -> None:
            nome = (v["nome"] or "").strip()
            if not nome:
                self.messaggio = self.tx("errore", testo=self.tx("serve_nome"))
                await i.response.edit_message(embed=self.schermata_elenco(), view=self)
                return
            evento = (v["evento"] or "messaggio").strip().lower()
            try:
                self.bozza = Regola(chiave="p:0", tipo="personale", nome=nome[:MAX_NOME], evento=evento)
                servizio_valida = replace(self.bozza)  # solo per controllare l'evento
                from core.automod_regole_logic import regola_a_json, regola_da_json
                regola_da_json(regola_a_json(servizio_valida))
            except RegolaNonValida as errore:
                self.bozza = None
                self.messaggio = self.tx("errore", testo=str(errore))
                await i.response.edit_message(embed=self.schermata_elenco(), view=self)
                return
            self.nuova, self.sezione, self.messaggio = True, None, ""
            await i.response.edit_message(embed=self.schermata_regola(), view=self)

        await interaction.response.send_modal(ModaleCampi(self.tx("modale_nuova"), [
            campo("nome", self.tx("f_nome"), MAX_NOME),
            campo("evento", self.tx("f_evento"), 20, "messaggio", segnaposto="messaggio, ingresso, uscita, nome…"),
        ], invio))

    # ------------------------------------------------------------ callback della regola
    async def _scelta_cosa(self, interaction: discord.Interaction) -> None:
        self.sezione = interaction.data["values"][0]
        self.messaggio = ""
        if self.sezione in SELEZIONI:
            await self._ridisegna(interaction)
            return
        await interaction.response.send_modal(self._modale(self.sezione))
        # il pannello resta com'è finché la finestra non viene inviata

    def _scelta_azioni(self, gruppo):
        async def callback(interaction: discord.Interaction) -> None:
            scelte = set(interaction.data.get("values", []))
            try:
                self.bozza = replace(self.bozza, azioni=L.imposta_azioni(self.bozza.azioni, scelte, gruppo))
            except RegolaNonValida as errore:
                self.messaggio = self.tx("errore", testo=str(errore))
            else:
                mancano = [x for x in scelte if x in L.SOLO_DA_FINESTRA]
                self.messaggio = self.tx("da_finestra") if mancano else ""
            await self._ridisegna(interaction)

        return callback

    async def _onoff(self, interaction: discord.Interaction) -> None:
        self.bozza = replace(self.bozza, attiva=not self.bozza.attiva)
        await self._ridisegna(interaction)

    async def _indietro(self, interaction: discord.Interaction) -> None:
        self.bozza, self.sezione, self.messaggio, self.scelta_modello = None, None, "", False
        await self._carica()
        await self._ridisegna(interaction)

    async def _salva(self, interaction: discord.Interaction) -> None:
        mancano = L.permessi_mancanti(self.bozza.azioni, self.guild.me.guild_permissions if self.guild.me else None)
        try:
            if self.nuova:
                salvata = await servizio.crea_personale(self.guild.id, self.bozza, interaction.user.id)
            else:
                salvata = await servizio.salva(self.guild.id, self.bozza, interaction.user.id)
        except RegolaNonValida as errore:
            self.messaggio = self.tx("errore", testo=str(errore))
            await self._ridisegna(interaction)
            return
        self.bozza, self.nuova = salvata, False
        self.messaggio = self.tx("salvato") + (self.tx("mancano_permessi", permessi=", ".join(mancano)) if mancano else "")
        await self._carica()
        await self._ridisegna(interaction)

    async def _elimina(self, interaction: discord.Interaction) -> None:
        if not self.elimina_armato:
            self.elimina_armato = True
            await self._ridisegna(interaction)
            return
        await servizio.elimina(self.guild.id, self.bozza.chiave)
        self.bozza, self.sezione, self.elimina_armato = None, None, False
        self.messaggio = self.tx("eliminata")
        await self._carica()
        await self._ridisegna(interaction)

    async def _prova(self, interaction: discord.Interaction) -> None:
        async def invio(i: discord.Interaction, v: dict) -> None:
            try:
                utente = L.leggi_id(v["utente"])
            except RegolaNonValida as errore:
                self.messaggio = self.tx("errore", testo=str(errore))
                await i.response.edit_message(embed=self.schermata_regola(), view=self)
                return
            membro = self.guild.get_member(utente) if utente else None
            if membro is None:
                self.messaggio = self.tx("prova_nessun_membro")
            else:
                ctx = contesto_da_membro(membro, i.channel, evento=self.bozza.evento)
                vale = condizioni_ok(self.bozza.condizioni, ctx)
                self.messaggio = self.tx("prova_vale" if vale else "prova_non_vale", utente=membro.display_name)
            await i.response.edit_message(embed=self.schermata_regola(), view=self)

        await interaction.response.send_modal(ModaleCampi(self.tx("btn_prova"), [
            campo("utente", self.tx("f_utente_prova"), 40, segnaposto="ID o @menzione")], invio))

    # ------------------------------------------------------------ finestre
    def _modale(self, sezione: str) -> ModaleCampi:
        costruttori = {"chi": self._m_chi, "sanzioni": self._m_sanzioni, "messaggi": self._m_messaggi,
                       "canale": self._m_canale, "contatore": self._m_contatore, "gruppo": self._m_gruppo,
                       "innesco": self._m_innesco}
        return costruttori[sezione]()

    async def _chiudi_modale(self, i: discord.Interaction, errore: RegolaNonValida | None = None) -> None:
        self.messaggio = self.tx("errore", testo=str(errore)) if errore else ""
        await i.response.edit_message(embed=self.schermata_regola(), view=self)

    def _m_chi(self) -> ModaleCampi:
        c = self.bozza.condizioni
        fmt = lambda p: "" if p == (None, None) else f"{'' if p[0] is None else p[0]}-{'' if p[1] is None else p[1]}"
        o = c.orari

        async def invio(i, v):
            try:
                self._condizioni(
                    eta_account_giorni=L.leggi_intervallo(v["eta"]), nel_server_giorni=L.leggi_intervallo(v["server"]),
                    livello=L.leggi_intervallo(v["livello"], 1000), orari=L.leggi_orario(v["orario"], v["giorni"]))
            except RegolaNonValida as e:
                return await self._chiudi_modale(i, e)
            await self._chiudi_modale(i)

        return ModaleCampi(self.tx("cosa_chi"), [
            campo("eta", self.tx("f_eta"), 12, fmt(c.eta_account_giorni), segnaposto="-7"),
            campo("server", self.tx("f_server"), 12, fmt(c.nel_server_giorni), segnaposto="-3"),
            campo("livello", self.tx("f_livello"), 12, fmt(c.livello), segnaposto="-5"),
            campo("orario", self.tx("f_orario"), 11, f"{o.dalle}-{o.alle}" if o else "", segnaposto="23:00-08:00"),
            campo("giorni", self.tx("f_giorni"), 20, ",".join(map(str, o.giorni)) if o else "", segnaposto="1,2,3,4,5,6,7"),
        ], invio)

    def _m_sanzioni(self) -> ModaleCampi:
        d = {a.t: a for a in self.bozza.azioni}
        durata = lambda t_, k: str(d[t_].get(k)) + "s" if t_ in d else ""

        async def invio(i, v):
            try:
                az = self.bozza.azioni
                if (s := L.leggi_durata(v["timeout"], 1, 2_419_200)):
                    az = L.metti_azione(az, azione_da_json({"t": "timeout", "secondi": s}))
                if v["ban"].strip():
                    az = L.metti_azione(az, azione_da_json({"t": "ban_tempo", "giorni": max(1, (L.leggi_durata(v["ban"], 86400, 365 * 86400) or 86400) // 86400)}))
                if (s := L.leggi_durata(v["mute"], 60, 2_419_200)):
                    az = L.metti_azione(az, azione_da_json({"t": "mute_ruolo", "secondi": s}))
                if v["nick"].strip():
                    az = L.metti_azione(az, azione_da_json({"t": "nickname", "testo": v["nick"].strip()}))
                if v["ultimi"].strip():
                    az = L.metti_azione(az, azione_da_json({"t": "cancella_ultimi", "n": int(v["ultimi"]), "minuti": 10}))
                self.bozza = replace(self.bozza, azioni=az)
            except (RegolaNonValida, ValueError) as e:
                return await self._chiudi_modale(i, e if isinstance(e, RegolaNonValida) else RegolaNonValida(self.tx("serve_numero")))
            await self._chiudi_modale(i)

        return ModaleCampi(self.tx("cosa_sanzioni"), [
            campo("timeout", self.tx("f_timeout"), 8, durata("timeout", "secondi"), segnaposto="10m"),
            campo("ban", self.tx("f_ban"), 8, f"{d['ban_tempo'].get('giorni')}d" if "ban_tempo" in d else "", segnaposto="7d"),
            campo("mute", self.tx("f_mute"), 8, durata("mute_ruolo", "secondi"), segnaposto="1h"),
            campo("nick", self.tx("f_nick"), MAX_NICKNAME, d["nickname"].get("testo", "") if "nickname" in d else ""),
            campo("ultimi", self.tx("f_ultimi"), 2, str(d["cancella_ultimi"].get("n")) if "cancella_ultimi" in d else "",
                  segnaposto=f"1-{MAX_CANCELLA_ULTIMI}"),
        ], invio)

    def _m_messaggi(self) -> ModaleCampi:
        d = {a.t: a for a in self.bozza.azioni}
        av, dm, lg, st = d.get("avviso_canale"), d.get("dm"), d.get("log"), d.get("dm_staff")

        async def invio(i, v):
            try:
                az = self.bozza.azioni
                if v["testo"].strip():
                    dopo = L.leggi_intervallo(v["dopo"] or "10")[1] or 10
                    az = L.metti_azione(az, azione_da_json({"t": "avviso_canale", "testo": v["testo"], "dopo_s": dopo}))
                else:
                    az = L.togli_azione(az, "avviso_canale")
                az = L.metti_azione(az, azione_da_json({"t": "dm", "testo": v["dm"]})) if v["dm"].strip() else L.togli_azione(az, "dm")
                if (ruolo := L.leggi_id(v["ping"])):
                    az = L.metti_azione(az, azione_da_json({"t": "log", "ping_ruolo": ruolo}))
                elif lg is not None:
                    az = L.metti_azione(az, azione_da_json({"t": "log"}))
                if (staff := L.leggi_ids(v["staff"], 5)):
                    az = L.metti_azione(az, azione_da_json({"t": "dm_staff", "utenti": staff}))
                else:
                    az = L.togli_azione(az, "dm_staff")
                self.bozza = replace(self.bozza, azioni=az)
            except RegolaNonValida as e:
                return await self._chiudi_modale(i, e)
            await self._chiudi_modale(i)

        return ModaleCampi(self.tx("cosa_messaggi"), [
            campo("testo", self.tx("f_avviso"), MAX_AVVISO_CANALE, av.get("testo", "") if av else "", lungo=True),
            campo("dopo", self.tx("f_dopo"), 2, str(av.get("dopo_s")) if av else "", segnaposto="10"),
            campo("dm", self.tx("f_dm"), MAX_TESTO_DM, dm.get("testo", "") if dm else "", lungo=True),
            campo("ping", self.tx("f_ping"), 40, str(lg.get("ping_ruolo", "")) if lg else "", segnaposto="ID o @ruolo"),
            campo("staff", self.tx("f_staff"), 200, " ".join(map(str, st.get("utenti", []))) if st else "", segnaposto="ID o @utente, max 5"),
        ], invio)

    def _m_canale(self) -> ModaleCampi:
        d = {a.t: a for a in self.bozza.azioni}

        async def invio(i, v):
            try:
                az = self.bozza.azioni
                if (s := L.leggi_intervallo(v["slow"])[1]):
                    durata = L.leggi_durata(v["slow_per"] or "10m", 60, 86_400)
                    az = L.metti_azione(az, azione_da_json({"t": "slowmode", "secondi": s, "durata_s": durata}))
                else:
                    az = L.togli_azione(az, "slowmode")
                if (p := L.leggi_durata(v["blocco"], 60, 86_400)):
                    az = L.metti_azione(az, azione_da_json({"t": "permessi", "modello": "blocca_scrittura", "durata_s": p}))
                else:
                    az = L.togli_azione(az, "permessi")
                if v["thread"].strip():
                    az = L.metti_azione(az, azione_da_json({"t": "thread_apri", "nome": v["thread"].strip()}))
                else:
                    az = L.togli_azione(az, "thread_apri")
                if v["ruolo"].strip():
                    parti = v["ruolo"].split()
                    op = parti[0].lower() if parti[0].lower() in ("dai", "togli") else "dai"
                    rid = L.leggi_id(parti[-1] if parti[0].lower() in ("dai", "togli") and len(parti) > 1 else parti[0])
                    extra = {"secondi": L.leggi_durata(parti[2], 60)} if len(parti) > 2 else {}
                    az = L.metti_azione(az, azione_da_json({"t": "ruolo", "ruolo_id": rid, "op": op, **extra}))
                else:
                    az = L.togli_azione(az, "ruolo")
                self.bozza = replace(self.bozza, azioni=az)
            except RegolaNonValida as e:
                return await self._chiudi_modale(i, e)
            await self._chiudi_modale(i)

        return ModaleCampi(self.tx("cosa_canale"), [
            campo("slow", self.tx("f_slow"), 5, str(d["slowmode"].get("secondi")) if "slowmode" in d else "", segnaposto="30"),
            campo("slow_per", self.tx("f_slow_per"), 8, f"{d['slowmode'].get('durata_s')}s" if "slowmode" in d else "", segnaposto="10m"),
            campo("blocco", self.tx("f_blocco"), 8, f"{d['permessi'].get('durata_s')}s" if "permessi" in d else "", segnaposto="10m"),
            campo("thread", self.tx("f_thread"), MAX_NOME_THREAD, d["thread_apri"].get("nome", "") if "thread_apri" in d else ""),
            campo("ruolo", self.tx("f_ruolo"), 60, f"{d['ruolo'].get('op')} {d['ruolo'].get('ruolo_id')}" if "ruolo" in d else "",
                  segnaposto="dai|togli ID [durata]"),
        ], invio)

    def _m_contatore(self) -> ModaleCampi:
        c = self.bozza.contatore
        s0 = c.soglie[0] if c and c.soglie else None

        async def invio(i, v):
            try:
                nome = v["nome"].strip()
                if not nome:
                    self.bozza = replace(self.bozza, contatore=None)
                    return await self._chiudi_modale(i)
                soglia = Soglia(int(v["x"]), int(v["y"]), (L.leggi_azione_soglia(v["azione"]),))
                scad = int(v["scad"]) if v["scad"].strip() else None
                self.bozza = replace(self.bozza, contatore=Contatore(nome, scad, (soglia,)))
                from core.automod_regole_logic import contatore_a_json, contatore_da_json
                contatore_da_json(contatore_a_json(self.bozza.contatore))
            except ValueError:
                return await self._chiudi_modale(i, RegolaNonValida(self.tx("serve_numero")))
            except RegolaNonValida as e:
                return await self._chiudi_modale(i, e)
            await self._chiudi_modale(i)

        return ModaleCampi(self.tx("cosa_contatore"), [
            campo("nome", self.tx("f_cont_nome"), MAX_NOME, c.nome if c else "", segnaposto=self.tx("vuoto_toglie")),
            campo("x", self.tx("f_cont_x"), 3, str(s0.violazioni) if s0 else "3"),
            campo("y", self.tx("f_cont_y"), 4, str(s0.minuti) if s0 else "10"),
            campo("scad", self.tx("f_cont_scad"), 3, str(c.scadenza_giorni or "") if c else ""),
            campo("azione", self.tx("f_cont_azione"), 30, (s0.azioni[0].t if s0 else "timeout 10m"), segnaposto="timeout 10m"),
        ], invio)

    def _m_innesco(self) -> ModaleCampi:
        i = self.bozza.innesco or {}
        contenuto = "\n".join(i.get("regex", i.get("parole", ())))

        async def invio(i_, v):
            try:
                tipo = v["tipo"].strip().lower()
                dati: dict = {"tipo": tipo}
                if tipo == "regex":  # una regex per riga: le virgole fanno parte della regex, il tetto è 260
                    dati["regex"] = [r.strip() for r in v["contenuto"].splitlines() if r.strip()]
                elif righe := servizio_liste.leggi_voci(v["contenuto"]):
                    dati["parole"] = list(righe)
                nomi = [n.strip() for n in v["liste"].split(",") if n.strip()]
                if nomi:
                    dati["liste"] = nomi
                if tipo == "domini":
                    dati["modo"] = (v["modo"].strip().lower() or "vietati")
                self.bozza = replace(self.bozza, innesco=innesco_da_json(dati))
            except RegolaNonValida as e:
                return await self._chiudi_modale(i_, e)
            await self._chiudi_modale(i_)

        return ModaleCampi(self.tx("cosa_innesco"), [
            campo("tipo", self.tx("f_tipo_innesco"), 14, i.get("tipo", ""), segnaposto="regex, lista, domini, solo_permesse, sempre"),
            campo("contenuto", self.tx("f_contenuto"), MAX_TESTO_PROVA, contenuto, lungo=True),
            campo("liste", self.tx("f_liste"), 200, ", ".join(i.get("liste", ())), segnaposto="@parolacce-it, mia-lista"),
            campo("modo", self.tx("f_modo"), 8, i.get("modo", ""), segnaposto="vietati / permessi"),
        ], invio)

    def _m_gruppo(self) -> ModaleCampi:
        async def invio(i, v):
            try:
                calore = int(v["calore"]) if v["calore"].strip() else 0
                gruppo = v["gruppo"].strip() or None
                self.bozza = replace(self.bozza, gruppo=gruppo, calore=calore)
                from core.automod_regole_logic import regola_a_json, regola_da_json
                regola_da_json(regola_a_json(self.bozza))
            except ValueError:
                return await self._chiudi_modale(i, RegolaNonValida(self.tx("serve_numero")))
            except RegolaNonValida as e:
                return await self._chiudi_modale(i, e)
            await self._chiudi_modale(i)

        return ModaleCampi(self.tx("cosa_gruppo"), [
            campo("gruppo", self.tx("f_gruppo"), 32, self.bozza.gruppo or ""),
            campo("calore", self.tx("f_calore"), 3, str(self.bozza.calore), segnaposto="0-100"),
        ], invio)


async def apri_pannello(interaction: discord.Interaction, etichette: dict[str, str], chiave: str | None = None) -> None:
    lingua = await lingua_interazione(interaction)
    vista = PannelloRegole(interaction, lingua, etichette)
    await vista._carica()
    if chiave:
        if chiave.startswith("p:"):
            vista.bozza = next((r for r in vista.regole if r.chiave == chiave), None)
        elif chiave in etichette:
            vista.bozza = await vista.regola_filtro(chiave)
    embed = vista.schermata_regola() if vista.bozza else vista.schermata_elenco()
    await interaction.response.send_message(embed=embed, view=vista, ephemeral=True)

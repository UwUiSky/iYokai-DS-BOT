"""
tests/test_automod_odio_d35.py
==============================
D35: parola sospetta giudicata dall'AI (cognomi che passano, insulti cancellati, AI ferma = lato sicuro,
richiami e timeout, cache), regola nativa di blocco preventivo nei limiti di Discord, libreria
mondiale (una candidata non diventa globale con un solo server). AI finta, database vero.
"""

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest

import cogs.automod.automod as modulo_automod
import core.automod_odio_azioni as azioni
import cogs.automod.parole_odio as modulo_parole
import cogs.moderation._shared as modulo_shared
from core import automod_parole_opzioni as opz_parole
from core import odio_moderazione as moderazione
from core import odio_opzioni as odio_opz
from core.ai_servizio import AINonDisponibile, RispostaAI
from core.automod_odio_nativo_logic import MAX_LUNGHEZZA_REGEX, MAX_REGEX, costruisci_regex
from core.automod_parole_logic import costruisci_sospette, trova
from core.automod_rate_tracker import AutomodRateTracker
from core.database import Database
from core.odio_giudizio_logic import CacheGiudizi, Giudizio, leggi_risposta
from core.odio_libreria_logic import SOGLIA_SERVER, pulisci_variante, stato_dopo_segnalazione
from core.odio_libreria_service import LibreriaOdio
from core.odio_richiami_logic import ContatoreRichiami
from core.repositories.automod_advanced_repo import automod_advanced_repo
from core.repositories.odio_libreria_repo import OdioLibreriaRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_message, fake_text_channel
from tests.support.router_fakes import router_senza_scelte

GUILD = 666
UTENTE = 4242
NORMALE = '{"verdetto": "normale", "parole": [], "lingua": "it"}'
INSULTO = '{"verdetto": "insulto", "parole": ["negri"], "lingua": "it"}'

COGNOMI = [
    "Simone Negri lavora al supermercato",
    "Ho parlato con la signora Negri ieri",
    "Il dottor Negri riceve il martedì",
    "Mario Negri e Luca Bianchi sono colleghi",
]
FRASI_D_ODIO = [
    "questa banda di negri rovina tutto",
    "fuori dai piedi zingari",
    "N3GR1 tornate a casa vostra",
]


class AIFinta:
    """Il servizio AI: risponde con `testo` oppure solleva `errore`. Registra le richieste."""

    def __init__(self, testo: str = NORMALE, errore: Exception | None = None) -> None:
        self.testo, self.errore, self.richieste = testo, errore, []

    async def richiedi(self, r):
        self.richieste.append(r)
        if self.errore is not None:
            raise self.errore
        return RispostaAI(testo=self.testo)


def _messaggio(contenuto):
    server = fake_guild(guild_id=GUILD)
    autore = fake_member(user_id=UTENTE)
    autore.guild = server
    autore.guild_permissions = discord.Permissions.none()
    m = fake_message(author=autore, guild=server, content=contenuto)
    m.channel = fake_text_channel(channel_id=111)
    m.channel.send = AsyncMock()
    m.mentions, m.role_mentions = [], []
    m.mention_everyone = False
    m.attachments, m.stickers = [], []
    return m


def _archivio(**valori):
    finto = create_autospec(Database, instance=True)
    finto.is_module_active_for_guild.return_value = True
    finto.get_guild_setting.side_effect = lambda gid, chiave, default=None: valori.get(chiave, default)
    return finto


def _ambiente_base(monkeypatch):
    monkeypatch.setattr(moderazione, "cache_giudizi", CacheGiudizi())
    monkeypatch.setattr(azioni, "contatore", ContatoreRichiami())
    router_senza_scelte(monkeypatch)
    monkeypatch.setattr(azioni.bot_roles, "isola", AsyncMock())
    monkeypatch.setattr(moderazione.libreria_odio, "segnala", AsyncMock(return_value=[]))
    monkeypatch.setattr(moderazione.libreria_odio, "candidate", AsyncMock(return_value=()))
    monkeypatch.setattr(moderazione.libreria_odio, "globali", AsyncMock(return_value=()))


@pytest.fixture
def ambiente(monkeypatch):
    """Cache e contatori puliti, nessuna rete, nessun database."""
    _ambiente_base(monkeypatch)
    monkeypatch.setattr(azioni.automod_advanced_repo, "log_action", AsyncMock())
    from core.repositories.automod_advanced_repo import AutomodAdvancedSettings

    impostazioni = MagicMock(spec=AutomodAdvancedSettings)
    impostazioni.log_channel_id = None
    monkeypatch.setattr(azioni.automod_advanced_repo, "get_settings", AsyncMock(return_value=impostazioni))


async def _controlla(monkeypatch, contenuto, ai, archivio=None, messaggio=None):
    monkeypatch.setattr(moderazione, "servizio_ai", lambda: ai)
    archivio = archivio or _archivio()
    m = messaggio or _messaggio(contenuto)
    filtro, _ = await opz_parole.filtro_sospette(GUILD, archivio)
    return m, await azioni.controlla_sospetta(m, contenuto, filtro, archivio)


# ---- il filtro delle parole sospette --------------------------------------
@pytest.mark.parametrize("frase", COGNOMI + FRASI_D_ODIO)
def test_le_parole_sospette_si_riconoscono(frase):
    assert trova(frase, costruisci_sospette()) is not None


def test_senza_parola_sospetta_il_filtro_tace():
    assert trova("ciao a tutti, domani si gioca alle otto", costruisci_sospette()) is None


def test_una_parola_lecita_del_server_salta_il_giudizio():
    assert trova("il negri della classe", costruisci_sospette((), ("negri",))) is None


# ---- il giudizio dell'AI ---------------------------------------------------
@pytest.mark.parametrize("frase", COGNOMI)
async def test_cognome_o_uso_normale_passa(monkeypatch, ambiente, frase):
    ai = AIFinta(NORMALE)
    m, trattato = await _controlla(monkeypatch, frase, ai)
    assert trattato is False
    m.delete.assert_not_awaited()
    m.channel.send.assert_not_awaited()
    assert len(ai.richieste) == 1


@pytest.mark.parametrize("frase", FRASI_D_ODIO)
async def test_frase_d_odio_viene_cancellata_con_richiamo(monkeypatch, ambiente, frase):
    m, trattato = await _controlla(monkeypatch, frase, AIFinta(INSULTO))
    assert trattato is True
    m.delete.assert_awaited_once()
    args, kw = m.channel.send.await_args
    assert kw["delete_after"] == azioni.SECONDI_RICHIAMO_VISIBILE  # il richiamo si cancella da solo
    assert "Richiamo 1 di 3" in args[0]


async def test_la_richiesta_all_ai_e_di_moderazione_e_non_conta_la_persona(monkeypatch, ambiente):
    ai = AIFinta(NORMALE)
    await _controlla(monkeypatch, COGNOMI[0], ai)
    r = ai.richieste[0]
    assert r.conta_utente is False and r.messaggi_utenti is True and r.tipo == "giudizio"
    assert r.funzione == moderazione.FUNZIONE_AI


@pytest.mark.parametrize("errore", [AINonDisponibile("fornitori_fermi"), AINonDisponibile("spenta"), RuntimeError("boom")])
async def test_con_l_ai_ferma_cancella_e_avvisa(monkeypatch, ambiente, errore):
    m, trattato = await _controlla(monkeypatch, COGNOMI[0], AIFinta(errore=errore))
    assert trattato is True
    m.delete.assert_awaited_once()
    assert "non ho potuto controllare" in m.channel.send.await_args.args[0]


async def test_risposta_illeggibile_vale_lato_sicuro(monkeypatch, ambiente):
    m, trattato = await _controlla(monkeypatch, COGNOMI[0], AIFinta("boh, non so"))
    assert trattato is True
    m.delete.assert_awaited_once()


async def test_la_decisione_va_in_cache_per_frase_normalizzata(monkeypatch, ambiente):
    ai = AIFinta(NORMALE)
    await _controlla(monkeypatch, "Simone Negri lavora al supermercato", ai)
    await _controlla(monkeypatch, "SIMONE   negri lavora al supermercato!", ai)
    assert len(ai.richieste) == 1


async def test_l_errore_dell_ai_non_resta_in_cache(monkeypatch, ambiente):
    await _controlla(monkeypatch, COGNOMI[0], AIFinta(errore=AINonDisponibile("fornitori_fermi")))
    ai = AIFinta(NORMALE)
    m, trattato = await _controlla(monkeypatch, COGNOMI[0], ai)
    assert trattato is False and len(ai.richieste) == 1


async def test_se_il_canale_non_permette_la_risposta_va_in_dm(monkeypatch, ambiente):
    m = _messaggio(FRASI_D_ODIO[0])
    m.channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "no"))
    m.author.send = AsyncMock()
    await _controlla(monkeypatch, FRASI_D_ODIO[0], AIFinta(INSULTO), messaggio=m)
    m.author.send.assert_awaited_once()


# ---- richiami e timeout ----------------------------------------------------
async def test_tre_richiami_in_un_ora_portano_al_timeout(monkeypatch, ambiente):
    ai = AIFinta(INSULTO)
    for numero in range(1, 4):
        frase = f"{FRASI_D_ODIO[0]} {numero * 'x'}"  # frasi diverse: niente cache
        m, _ = await _controlla(monkeypatch, frase, ai)
        if numero < 3:
            azioni.bot_roles.isola.assert_not_awaited()
    azioni.bot_roles.isola.assert_awaited_once()
    assert azioni.bot_roles.isola.await_args.args[1].total_seconds() == 3600
    assert "timeout di 60 minuti" in m.channel.send.await_args.args[0]


async def test_soglia_e_durata_sono_configurabili(monkeypatch, ambiente):
    archivio = _archivio(odio_richiami_soglia=1, odio_timeout_minuti=5)
    await _controlla(monkeypatch, FRASI_D_ODIO[0], AIFinta(INSULTO), archivio)
    assert azioni.bot_roles.isola.await_args.args[1].total_seconds() == 300


async def test_due_richiami_non_bastano(monkeypatch, ambiente):
    ai = AIFinta(INSULTO)
    await _controlla(monkeypatch, FRASI_D_ODIO[0], ai)
    await _controlla(monkeypatch, FRASI_D_ODIO[1], ai)
    azioni.bot_roles.isola.assert_not_awaited()


async def test_chi_gestisce_il_server_non_riceve_il_timeout(monkeypatch, ambiente):
    m = _messaggio(FRASI_D_ODIO[0])
    m.author.guild_permissions = discord.Permissions(manage_guild=True)
    archivio = _archivio(odio_richiami_soglia=1)
    await _controlla(monkeypatch, FRASI_D_ODIO[0], AIFinta(INSULTO), archivio, messaggio=m)
    azioni.bot_roles.isola.assert_not_awaited()
    m.delete.assert_awaited_once()


def test_contatore_conta_solo_nella_finestra_e_ha_un_tetto():
    c = ContatoreRichiami(massimo=3)
    assert [c.registra(1, 1, t, 60) for t in (0, 10, 20)] == [1, 2, 3]
    assert c.registra(1, 1, 100, 60) == 1  # i vecchi sono fuori dalla finestra
    for utente in range(10):
        c.registra(1, utente + 10, 0, 60)
    assert len(c) == 3


# ---- il filtro nel cog dell'AutoMod ---------------------------------------
@pytest.fixture
def cog(monkeypatch, clean_db):
    _ambiente_base(monkeypatch)
    archivio = _archivio()
    monkeypatch.setattr(modulo_shared, "db", archivio)
    monkeypatch.setattr(modulo_automod, "db", archivio)
    monkeypatch.setattr(automod_advanced_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(modulo_automod, "rate_tracker", AutomodRateTracker())
    return modulo_automod.AutomodCog(bot=MagicMock())


async def test_nel_cog_il_cognome_passa_e_l_insulto_no(monkeypatch, cog):
    ai = AIFinta(NORMALE)
    monkeypatch.setattr(moderazione, "servizio_ai", lambda: ai)
    pulito = _messaggio(COGNOMI[0])
    await cog.on_message(pulito)
    pulito.delete.assert_not_awaited()
    ai.testo = INSULTO
    sporco = _messaggio(FRASI_D_ODIO[0])
    await cog.on_message(sporco)
    sporco.delete.assert_awaited_once()
    cog.bot.dispatch.assert_not_called()  # la scala la conta il richiamo, non l'evento delle parole certe
    righe = await automod_advanced_repo.get_recent_actions(GUILD)
    assert [r["violation"] for r in righe] == [azioni.VIOLATION_PAROLE_SOSPETTE]


async def test_con_la_base_spenta_le_sospette_non_si_controllano(monkeypatch, cog):
    archivio = _archivio(automod_parole_base=False)
    monkeypatch.setattr(modulo_automod, "db", archivio)
    ai = AIFinta(INSULTO)
    monkeypatch.setattr(moderazione, "servizio_ai", lambda: ai)
    m = _messaggio(FRASI_D_ODIO[0])
    await cog.on_message(m)
    m.delete.assert_not_awaited()
    assert ai.richieste == []


# ---- varianti nuove trovate dall'AI -----------------------------------------
async def test_una_parola_nuova_dell_ai_va_in_libreria_solo_se_sta_nel_messaggio(monkeypatch, ambiente):
    segnala = AsyncMock(return_value=[])
    monkeypatch.setattr(moderazione.libreria_odio, "segnala", segnala)
    archivio = _archivio()
    g = Giudizio("insulto", ("zzorbo", "inventata"), "it")
    assert await moderazione.segnala_varianti(GUILD, "voi zzorbo fuori di qui", g, archivio) == 0  # (segnala restituisce [])
    assert segnala.await_args.args[1] == ("zzorbo",)  # "inventata" non e' nel messaggio


async def test_una_parola_gia_nota_non_e_una_variante_nuova(monkeypatch, ambiente):
    segnala = AsyncMock(return_value=[])
    monkeypatch.setattr(moderazione.libreria_odio, "segnala", segnala)
    await moderazione.segnala_varianti(GUILD, "banda di negri", Giudizio("insulto", ("negri",), "it"), _archivio())
    segnala.assert_not_awaited()


# ---- la libreria mondiale ----------------------------------------------------
def test_regole_della_libreria():
    assert pulisci_variante("N1GG3R") == "nigger"
    assert pulisci_variante("ab") is None and pulisci_variante("a b c d") is None and pulisci_variante("") is None
    assert stato_dopo_segnalazione("candidata", SOGLIA_SERVER - 1) == "candidata"
    assert stato_dopo_segnalazione("candidata", SOGLIA_SERVER) == "approvata"
    assert stato_dopo_segnalazione("rifiutata", 99) == "rifiutata"


@pytest.fixture
def repo(clean_db):
    return OdioLibreriaRepository(lambda: clean_db)


async def test_una_candidata_non_diventa_globale_con_un_solo_server(repo):
    for _ in range(5):  # lo stesso server che segnala di continuo conta una volta sola
        esito = await repo.segnala("zzorbo", "it", 1)
    assert esito.stato == "candidata" and esito.server == 1
    assert await repo.globali() == ()
    assert await repo.candidate_del_server(1) == ("zzorbo",)
    assert await repo.candidate_del_server(2) == ()  # vale solo dove e' stata segnalata


async def test_con_tre_server_diversi_diventa_globale(repo):
    await repo.segnala("zzorbo", "it", 1)
    await repo.segnala("zzorbo", "it", 2)
    assert (await repo.segnala("zzorbo", "it", 2)).stato == "candidata"
    assert (await repo.segnala("zzorbo", "it", 3)).stato == "approvata"
    assert await repo.globali() == ("zzorbo",)


async def test_il_proprietario_approva_e_rifiuta(repo):
    await repo.segnala("zzorbo", "it", 1)
    await repo.segnala("brontolo", "it", 1)
    assert await repo.imposta_stato("zzorbo", "approvata") is True
    assert await repo.imposta_stato("brontolo", "rifiutata") is True
    assert await repo.imposta_stato("inesistente", "approvata") is False
    assert await repo.globali() == ("zzorbo",)
    for server in (2, 3, 4):  # una rifiutata non risale con le segnalazioni
        assert (await repo.segnala("brontolo", "it", server)).stato == "rifiutata"
    assert await repo.globali() == ("zzorbo",)


async def test_un_server_non_puo_riempire_la_libreria(repo, monkeypatch):
    from core import odio_libreria_logic as logica
    import core.repositories.odio_libreria_repo as modulo

    monkeypatch.setattr(modulo, "MAX_CANDIDATE_PER_SERVER", 2)
    assert await repo.segnala("alfaxx", "it", 1) is not None
    assert await repo.segnala("betaxx", "it", 1) is not None
    assert await repo.segnala("gammaxx", "it", 1) is None
    assert logica.MAX_CANDIDATE_PER_SERVER >= 2


async def test_voce_di_base_e_elenco(repo):
    await repo.aggiungi_base("qwerty", "en")
    await repo.segnala("zzorbo", "it", 1)
    assert await repo.globali() == ("qwerty",)
    assert [p.variante for p in await repo.elenca("candidata")] == ["zzorbo"]
    assert (await repo.conta_per_stato()) == {"base": 1, "candidata": 1}


async def test_le_globali_entrano_nel_filtro_di_tutti_i_server(repo, monkeypatch):
    libreria = LibreriaOdio(repo)
    monkeypatch.setattr(opz_parole, "libreria_odio", libreria)
    archivio = _archivio()
    await repo.segnala("zzorbo", "it", 1)
    filtro, _ = await opz_parole.filtro_del_server(GUILD, archivio)
    assert trova("voi zzorbo fuori", filtro) is None  # solo candidata: non vale
    for server in (2, 3):
        await repo.segnala("zzorbo", "it", server)
    libreria.svuota()
    filtro, _ = await opz_parole.filtro_del_server(GUILD, archivio)
    assert trova("voi zzorbo fuori", filtro) is not None


async def test_la_candidata_vale_nel_server_che_l_ha_segnalata(repo, monkeypatch):
    libreria = LibreriaOdio(repo)
    monkeypatch.setattr(opz_parole, "libreria_odio", libreria)
    await libreria.segnala(GUILD, ("zzorbo",), "it")
    sospette, _ = await opz_parole.filtro_sospette(GUILD, _archivio())
    assert trova("voi zzorbo fuori", sospette) is not None
    altro, _ = await opz_parole.filtro_sospette(GUILD + 1, _archivio())
    assert trova("voi zzorbo fuori", altro) is None


# ---- lettura della risposta dell'AI ------------------------------------------
def test_leggi_risposta():
    g = leggi_risposta('ecco: {"verdetto": "insulto", "parole": ["a", 3, "b"], "lingua": "it"} grazie')
    assert g.insulto and g.parole == ("a", "b") and g.lingua == "it"
    assert leggi_risposta(NORMALE).parole == ()
    for male in ("", "ciao", "{rotto", '{"verdetto": "forse"}', "[1]"):
        assert leggi_risposta(male) is None


def test_cache_scade_e_ha_un_tetto():
    c = CacheGiudizi(massimo=2, durata=10)
    g = Giudizio("normale")
    c.metti(1, "uno due", g, ora=0)
    assert c.trova(1, "UNO due!", ora=5) is g
    assert c.trova(1, "uno due", ora=11) is None
    for n in ("aaa", "bbb", "ccc"):
        c.metti(1, n, g, ora=0)
    assert len(c) == 2
    assert c.trova(2, "ccc", ora=1) is None  # un altro server non vede la decisione


# ---- regola nativa -------------------------------------------------------------
def test_le_regex_nei_limiti_di_discord():
    r = costruisci_regex()
    assert 0 < len(r.pattern) <= MAX_REGEX
    assert all(len(p) <= MAX_LUNGHEZZA_REGEX for p in r.pattern)
    assert r.insulti_esclusi == 0
    for p in r.pattern:
        assert "(?=" not in p and "(?!" not in p and "(?<" not in p  # niente lookaround: Rust non li ha


def test_le_regex_prendono_insulto_con_minaccia_ma_non_il_cognome():
    modelli = [re.compile(p) for p in costruisci_regex().pattern]
    prende = lambda t: any(m.search(t) for m in modelli)  # noqa: E731
    assert prende("nigger vi ammazzo tutti")
    assert prende("vi bruciamo, niggers")  # minaccia prima dell'insulto
    assert not prende("nigger")  # l'insulto da solo non basta: lo ferma il bot
    assert not prende("Simone Negri lavora al supermercato")
    assert not prende("Simone Negri ammazza il tempo")  # le sospette non sono nella regola nativa


def test_troppi_insulti_restano_fuori_e_lo_dice():
    r = costruisci_regex(tuple(f"parola{chr(97 + i % 26)}{chr(97 + i // 26)}x" for i in range(400)))
    assert len(r.pattern) <= MAX_REGEX and r.insulti_esclusi > 0
    assert r.insulti_inclusi + r.insulti_esclusi == 400


def _regola(nome, tipo=discord.AutoModRuleTriggerType.keyword):
    r = MagicMock()
    r.name = nome
    r.trigger.type = tipo
    r.delete, r.edit = AsyncMock(), AsyncMock()
    return r


def _server(regole):
    g = fake_guild(guild_id=GUILD)
    g.fetch_automod_rules = AsyncMock(return_value=regole)
    g.create_automod_rule = AsyncMock()
    return g


async def test_il_blocco_crea_la_regola_con_il_messaggio_del_server():
    g = _server([])
    avviso = await azioni.sincronizza_blocco(g, odio_opz.OpzioniOdio(blocco=True, messaggio="Basta."))
    assert avviso is None
    kw = g.create_automod_rule.await_args.kwargs
    assert kw["name"] == azioni.RULE_NAME_ODIO
    assert kw["actions"][0].custom_message == "Basta."
    assert kw["trigger"].regex_patterns and kw["trigger"].type is discord.AutoModRuleTriggerType.keyword
    assert kw["enabled"] is True


async def test_il_blocco_aggiorna_la_regola_che_c_e_e_la_toglie_da_spento():
    nostra = _regola(azioni.RULE_NAME_ODIO)
    g = _server([nostra])
    await azioni.sincronizza_blocco(g, odio_opz.OpzioniOdio(blocco=True))
    nostra.edit.assert_awaited_once()
    g.create_automod_rule.assert_not_awaited()
    await azioni.sincronizza_blocco(g, odio_opz.OpzioniOdio(blocco=False))
    nostra.delete.assert_awaited_once()


async def test_il_blocco_rispetta_il_tetto_di_sei_regole_a_parole():
    g = _server([_regola(f"altra{n}") for n in range(6)])
    avviso = await azioni.sincronizza_blocco(g, odio_opz.OpzioniOdio(blocco=True))
    assert "6 regole" in avviso
    g.create_automod_rule.assert_not_awaited()


async def test_il_blocco_senza_permessi_avvisa():
    g = _server([])
    g.fetch_automod_rules = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "no"))
    assert "permesso" in await azioni.sincronizza_blocco(g, odio_opz.OpzioniOdio(blocco=True))


def test_il_messaggio_del_blocco_ha_un_testo_predefinito_e_un_tetto():
    assert odio_opz.messaggio_valido("") == odio_opz.MESSAGGIO_PREDEFINITO
    assert odio_opz.messaggio_valido(None).startswith("Primo richiamo: la tua affermazione risulta razzista")
    assert len(odio_opz.messaggio_valido("x" * 500)) == 150
    assert len(odio_opz.MESSAGGIO_PREDEFINITO) <= 150


# ---- impostazioni e comandi ------------------------------------------------------
async def test_impostazioni_con_i_valori_di_partenza_e_i_limiti(monkeypatch):
    o = await odio_opz.leggi(GUILD, _archivio())
    assert (o.blocco, o.soglia, o.minuti, o.timeout_minuti) == (False, 3, 60, 60)
    o = await odio_opz.leggi(GUILD, _archivio(odio_richiami_soglia=0, odio_timeout_minuti=10**9, odio_blocco_attivo="si"))
    assert (o.blocco, o.soglia, o.timeout_minuti) == (False, 3, 60)
    with pytest.raises(ValueError):
        await odio_opz.imposta_richiami(GUILD, 0, None, None, 1)
    with pytest.raises(ValueError):
        await odio_opz.imposta_richiami(GUILD, None, None, 40321, 1)


async def test_imposta_blocco_salva_testo_e_stato(monkeypatch):
    scritto = _archivio()
    monkeypatch.setattr(odio_opz, "_db", scritto)
    await odio_opz.imposta_blocco(GUILD, True, "Ciao", 9)
    scritto.set_guild_setting.assert_any_await(GUILD, odio_opz.SETTING_BLOCCO, True, changed_by=9)
    scritto.set_guild_setting.assert_any_await(GUILD, odio_opz.SETTING_BLOCCO_MESSAGGIO, "Ciao", changed_by=9)


async def test_solo_il_proprietario_del_bot_gestisce_la_libreria(monkeypatch):
    cog = modulo_parole.ParoleOdioCog(MagicMock())
    monkeypatch.setattr(modulo_parole, "config", SimpleNamespace(OWNER_ID=1))
    estraneo = fake_interaction(guild=fake_guild(guild_id=GUILD), user=fake_member(user_id=2))
    scelta = MagicMock()
    scelta.value = "approva"
    chiamata = AsyncMock()
    monkeypatch.setattr(modulo_parole.odio_libreria_repo, "imposta_stato", chiamata)
    await cog.libreria.callback(cog, estraneo, scelta, "zzorbo", None)
    chiamata.assert_not_awaited()
    assert "Solo il proprietario" in estraneo.response.send_message.await_args.args[0]


async def test_il_proprietario_approva_una_variante(monkeypatch, clean_db):
    from core.repositories.odio_libreria_repo import OdioLibreriaRepository as Repo

    repo = Repo(lambda: clean_db)
    monkeypatch.setattr(modulo_parole, "odio_libreria_repo", repo)
    await repo.segnala("zzorbo", "it", 1)
    assert "Approvata" in await modulo_parole.ParoleOdioCog._libreria("approva", "zzorbo", None)
    assert await repo.globali() == ("zzorbo",)
    assert "non è in libreria" in await modulo_parole.ParoleOdioCog._libreria("rifiuta", "mai vista", None)
    assert "Serve una variante" in await modulo_parole.ParoleOdioCog._libreria("approva", "ab", None)
    assert "1" in await modulo_parole.ParoleOdioCog._libreria("elenca", None, None)

"""
tests/test_automod_eventi.py
============================
Regole AutoMod sugli eventi che non sono messaggi (AMD-009/010/017/018/075): scelta delle regole, condizioni,
freni contro i giri a vuoto, ascoltatori del cog e registro dei casi.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.automod import eventi as cog_mod
from core import automod_eventi as ev
from core import automod_eventi_logic as lg
from core import caso_eventi
from core.automod_azioni import Bersaglio
from core.automod_regole_logic import Condizioni, Regola, azioni_da_json, contatore_da_json
from tests.support.discord_fakes import fake_guild, fake_member, fake_role, fake_text_channel

GUILD = 777000902


def regola(chiave="p:1", evento="vocale", innesco=None, *, attiva=True, tipo="personale", azioni=None, cond=None, contatore=None):
    return Regola(
        chiave=chiave, tipo=tipo, nome=f"regola {chiave}", id=int(chiave.split(":")[-1]) if ":" in chiave else None, evento=evento,
        attiva=attiva, innesco=innesco if innesco is not None else {"tipo": "sempre"}, condizioni=cond or Condizioni(),
        azioni=azioni_da_json(azioni if azioni is not None else [{"t": "log"}]), contatore=contatore,
    )


@pytest.fixture
def amb(monkeypatch):
    guild = fake_guild(GUILD, owner_id=1)
    membro = fake_member(555, "utente")
    membro.guild = guild
    membro.created_at = membro.joined_at = None
    bot = SimpleNamespace(user=SimpleNamespace(id=999))
    esegui = AsyncMock(return_value=("log",))
    log = AsyncMock()
    regole = []
    settings = SimpleNamespace(exempt_channel_ids=(), exempt_role_ids=(), log_channel_id=None)
    monkeypatch.setattr(ev, "esegui_azioni", esegui)
    monkeypatch.setattr(ev.regole_service, "regole_del_server", AsyncMock(side_effect=lambda g: tuple(regole)))
    monkeypatch.setattr(ev.regole_service, "livello_di", AsyncMock(return_value=3))
    monkeypatch.setattr(ev.db, "is_module_active_for_guild", AsyncMock(return_value=True))
    monkeypatch.setattr(ev.automod_advanced_repo, "get_settings", AsyncMock(return_value=settings))
    monkeypatch.setattr(ev.automod_advanced_repo, "log_action", log)
    monkeypatch.setattr(ev.liste_service, "voci_per_regole", AsyncMock(return_value={}))
    monkeypatch.setattr(ev.bot_roles, "e_un_nostro_bot", lambda uid, b: uid == 999)
    monkeypatch.setattr(ev, "conteggi", lg.Conteggi())
    monkeypatch.setattr(ev, "effetti", lg.Effetti())
    monkeypatch.setattr(ev, "limite_regole", lg.LimiteRegole())
    return SimpleNamespace(guild=guild, membro=membro, bot=bot, esegui=esegui, log=log, regole=regole, settings=settings)


@pytest.mark.asyncio
async def test_senza_regole_non_fa_nulla(amb):
    assert await ev.elabora(amb.bot, amb.guild, amb.membro, "ingresso") == ()
    amb.esegui.assert_not_called()


@pytest.mark.asyncio
async def test_regola_dell_evento_esegue_azioni_e_scrive_il_registro(amb):
    amb.regole.append(regola("p:1", "ingresso"))
    assert await ev.elabora(amb.bot, amb.guild, amb.membro, "ingresso") == ("p:1",)
    azioni, bersaglio = amb.esegui.await_args.args
    assert isinstance(bersaglio, Bersaglio) and bersaglio.membro is amb.membro and bersaglio.regola_chiave == "p:1"
    assert azioni == amb.regole[0].azioni
    assert amb.log.await_args.args[:5] == (GUILD, 555, 0, "p:1", ("log",))


@pytest.mark.asyncio
@pytest.mark.parametrize("caso", ["spenta", "altro_evento", "filtro", "innesco_vuoto"])
async def test_regole_che_non_c_entrano_non_scattano(amb, caso):
    amb.regole.append({
        "spenta": regola("p:1", "ingresso", attiva=False),
        "altro_evento": regola("p:1", "uscita"),
        "filtro": regola("anti_caps", "ingresso", tipo="filtro"),
        "innesco_vuoto": regola("p:1", "ingresso", innesco={}),
    }[caso])
    assert await ev.elabora(amb.bot, amb.guild, amb.membro, "ingresso") == ()
    amb.esegui.assert_not_called()


@pytest.mark.asyncio
async def test_modulo_spento_non_fa_nulla(amb, monkeypatch):
    amb.regole.append(regola("p:1", "ingresso"))
    monkeypatch.setattr(ev.db, "is_module_active_for_guild", AsyncMock(return_value=False))
    assert await ev.elabora(amb.bot, amb.guild, amb.membro, "ingresso") == ()


@pytest.mark.asyncio
async def test_il_bot_non_si_giudica_mai(amb):
    amb.regole.append(regola("p:1", "ingresso"))
    mio = fake_member(999, "bot", bot=True)
    mio.guild = amb.guild
    assert await ev.elabora(amb.bot, amb.guild, mio, "ingresso") == ()


@pytest.mark.asyncio
async def test_un_altro_bot_non_scatta_con_autori_di_base(amb):
    amb.regole.append(regola("p:1", "ingresso"))
    altro = fake_member(444, "altro", bot=True)
    altro.guild = amb.guild
    altro.created_at = altro.joined_at = None
    assert await ev.elabora(amb.bot, amb.guild, altro, "ingresso") == ()


@pytest.mark.asyncio
async def test_spostamenti_vocali_scattano_al_terzo(amb):
    amb.regole.append(regola("p:1", "vocale", {"tipo": "spostamenti_vocali", "numero": 3, "secondi": 60}))
    canale = fake_text_channel(10)
    esiti = [await ev.elabora(amb.bot, amb.guild, amb.membro, "vocale", canale=canale) for _ in range(3)]
    assert esiti == [(), (), ("p:1",)]
    assert amb.log.await_args.args[2] == 10  # il canale dell'evento


@pytest.mark.asyncio
async def test_esenzioni_globali_valgono_per_gli_eventi(amb):
    amb.regole.append(regola("p:1", "ingresso"))
    amb.settings.exempt_role_ids = (77,)
    amb.membro.roles = [fake_role(role_id=77)]
    assert await ev.elabora(amb.bot, amb.guild, amb.membro, "ingresso") == ()
    amb.regole[0] = regola("p:1", "ingresso", cond=Condizioni(esenzioni_globali=False))
    assert await ev.elabora(amb.bot, amb.guild, amb.membro, "ingresso") == ("p:1",)


@pytest.mark.asyncio
async def test_condizione_sui_ruoli_si_applica(amb):
    amb.regole.append(regola("p:1", "ingresso", cond=Condizioni(senza_ruoli=True)))
    amb.membro.roles = [fake_role(role_id=5)]
    assert await ev.elabora(amb.bot, amb.guild, amb.membro, "ingresso") == ()


@pytest.mark.asyncio
async def test_effetto_del_bot_non_fa_scattare_la_regola(amb, monkeypatch):
    amb.regole.append(regola("p:1", "ruolo_dato", {"tipo": "sempre"}))
    ev.effetti.segna(GUILD, 555, "ruolo", 42, ev.time.monotonic())
    assert await ev.elabora(amb.bot, amb.guild, amb.membro, "ruolo_dato", lg.DatiEvento(ruolo_id=42)) == ()
    assert await ev.elabora(amb.bot, amb.guild, amb.membro, "ruolo_dato", lg.DatiEvento(ruolo_id=43)) == ("p:1",)


@pytest.mark.asyncio
async def test_il_nickname_cambiato_dal_bot_non_fa_scattare_le_regole_sul_nome(amb):
    amb.regole.append(regola("p:1", "nome", {"tipo": "nome", "parole": ["scam"]}))
    ev.effetti.segna(GUILD, 555, "nome", None, ev.time.monotonic())
    assert await ev.elabora(amb.bot, amb.guild, amb.membro, "nome", lg.DatiEvento(testo="scam")) == ()


@pytest.mark.asyncio
async def test_nome_vietato_scatta(amb):
    amb.regole.append(regola("p:1", "nome", {"tipo": "nome", "parole": ["scam"]}))
    assert await ev.elabora(amb.bot, amb.guild, amb.membro, "nome", lg.DatiEvento(testo="Free SCAM")) == ("p:1",)
    assert await ev.elabora(amb.bot, amb.guild, amb.membro, "nome", lg.DatiEvento(testo="Mario")) == ()


@pytest.mark.asyncio
async def test_al_massimo_tre_regole_per_evento(amb):
    amb.regole.extend(regola(f"p:{n}", "ingresso") for n in range(1, 6))
    assert await ev.elabora(amb.bot, amb.guild, amb.membro, "ingresso") == ("p:1", "p:2", "p:3")
    assert amb.esegui.await_count == 3


@pytest.mark.asyncio
async def test_caso_di_chi_non_e_nel_server_gira_senza_azioni_sulla_persona(amb):
    amb.regole.append(regola("p:1", "caso", {"tipo": "sempre", "casi": ["ban"]}))
    esito = await ev.elabora(amb.bot, amb.guild, None, "caso", lg.DatiEvento(tipo_caso="ban"), user_id=321)
    assert esito == ("p:1",)
    assert amb.esegui.await_args.args[1].membro is None
    assert amb.log.await_args.args[1] == 321


@pytest.mark.asyncio
async def test_senza_persona_ne_id_non_fa_nulla(amb):
    amb.regole.append(regola("p:1", "caso"))
    assert await ev.elabora(amb.bot, amb.guild, None, "caso") == ()


@pytest.mark.asyncio
async def test_un_errore_non_solleva(amb):
    amb.regole.append(regola("p:1", "ingresso"))
    amb.esegui.side_effect = RuntimeError("boom")
    assert await ev.elabora(amb.bot, amb.guild, amb.membro, "ingresso") == ()


@pytest.mark.asyncio
async def test_soglia_del_contatore_esegue_le_azioni_della_soglia(amb, monkeypatch):
    cont = contatore_da_json({"nome": "entrate", "soglie": [{"violazioni": 2, "minuti": 10, "azioni": [{"t": "timeout", "secondi": 60}]}]})
    amb.regole.append(regola("p:1", "ingresso", contatore=cont))
    monkeypatch.setattr(ev.contatori, "soglia_scattata", AsyncMock(return_value=cont.soglie[0]))
    monkeypatch.setattr(ev.contatori, "consuma", AsyncMock(return_value=2))
    await ev.elabora(amb.bot, amb.guild, amb.membro, "ingresso")
    assert amb.esegui.await_count == 2
    assert amb.esegui.await_args_list[1].args[0] == cont.soglie[0].azioni


def test_stato_spento_di_base_e_acceso_solo_dall_interruttore(monkeypatch):
    monkeypatch.delenv(ev.VARIABILE_STATO, raising=False)
    assert ev.stato_attivo() is False and ev.chiede_intent_presenze() is False
    for valore in ("1", "true", "SI", "on"):
        monkeypatch.setenv(ev.VARIABILE_STATO, valore)
        assert ev.chiede_intent_presenze() is True
    for valore in ("", "0", "no", "falso"):
        monkeypatch.setenv(ev.VARIABILE_STATO, valore)
        assert ev.stato_attivo() is False


@pytest.mark.asyncio
async def test_il_motore_segna_gli_effetti_prima_di_agire(monkeypatch):
    # l'evento nato da un'azione del bot arriva appena Discord risponde: la regola deve già saperlo
    from core import automod_azioni as az

    visti = []
    monkeypatch.setattr(az.eventi_logica.effetti, "segna", lambda *a: visti.append(a))
    guild = fake_guild(GUILD, owner_id=1)
    membro = fake_member(555, "u")
    membro.guild = guild
    ruolo = fake_role(role_id=42)
    guild.get_role = MagicMock(return_value=ruolo)
    membro.roles = []
    monkeypatch.setattr(az.bot_roles, "aggiungi_ruolo", AsyncMock())
    await az.esegui_azioni(azioni_da_json([{"t": "ruolo", "ruolo_id": 42, "op": "dai"}]),
                           Bersaglio(guild=guild, motivo="m", regola_chiave="p:1", regola_nome="n", membro=membro))
    assert visti and visti[0][:4] == (GUILD, 555, "ruolo", 42)


# ------------------------------------------------------------------ ascoltatori del cog

@pytest.fixture
def cog(monkeypatch):
    elabora = AsyncMock(return_value=())
    monkeypatch.setattr(cog_mod.eventi, "elabora", elabora)
    bot = SimpleNamespace(guilds=[], get_guild=lambda i: None)
    return SimpleNamespace(cog=cog_mod.EventiAutomodCog(bot), elabora=elabora, bot=bot)


def stato_vocale(canale):
    return SimpleNamespace(channel=canale)


@pytest.mark.asyncio
async def test_vocale_solo_per_gli_spostamenti(cog):
    m = fake_member(1)
    m.guild = fake_guild(GUILD)
    a, b = SimpleNamespace(id=1), SimpleNamespace(id=2)
    await cog.cog.on_voice_state_update(m, stato_vocale(None), stato_vocale(a))  # entra
    await cog.cog.on_voice_state_update(m, stato_vocale(a), stato_vocale(None))  # esce
    await cog.cog.on_voice_state_update(m, stato_vocale(a), stato_vocale(a))  # muto/audio
    cog.elabora.assert_not_called()
    await cog.cog.on_voice_state_update(m, stato_vocale(a), stato_vocale(b))
    assert cog.elabora.await_args.args[3] == "vocale" and cog.elabora.await_args.kwargs["canale"] is b


@pytest.mark.asyncio
async def test_thread_creato_passa_l_autore_e_il_canale_padre(cog):
    m = fake_member(1)
    guild = fake_guild(GUILD)
    guild.get_member = MagicMock(return_value=m)
    thread = SimpleNamespace(guild=guild, owner_id=1, parent=SimpleNamespace(id=5))
    await cog.cog.on_thread_create(thread)
    assert cog.elabora.await_args.args[2:4] == (m, "thread") and cog.elabora.await_args.kwargs["canale"].id == 5
    cog.elabora.reset_mock()
    guild.get_member = MagicMock(return_value=None)
    await cog.cog.on_thread_create(thread)
    cog.elabora.assert_not_called()


@pytest.mark.asyncio
async def test_ingresso_e_uscita(cog):
    m = fake_member(1, "nome")
    m.guild = fake_guild(GUILD)
    m.nick, m.global_name = "Nick", "Globale"
    await cog.cog.on_member_join(m)
    assert [c.args[3] for c in cog.elabora.await_args_list] == ["ingresso", "nome"]
    assert cog.elabora.await_args_list[1].args[4].testo == "Nick Globale nome"
    cog.elabora.reset_mock()
    await cog.cog.on_member_remove(m)
    assert cog.elabora.await_args.args[3] == "uscita"


@pytest.mark.asyncio
async def test_member_update_ruoli_dati_e_tolti_e_nick(cog):
    guild = fake_guild(GUILD)
    prima = fake_member(1)
    dopo = fake_member(1)
    prima.guild = dopo.guild = guild
    prima.nick, dopo.nick = None, "Nuovo"
    prima.global_name = dopo.global_name = None
    prima.roles = [fake_role(role_id=1), fake_role(role_id=2)]
    dopo.roles = [fake_role(role_id=2), fake_role(role_id=3)]
    await cog.cog.on_member_update(prima, dopo)
    chiamate = [(c.args[3], c.args[4]) for c in cog.elabora.await_args_list]
    assert chiamate[0][0] == "nome" and chiamate[0][1].testo.startswith("Nuovo")
    assert (("ruolo_dato", lg.DatiEvento(ruolo_id=3)) in chiamate) and (("ruolo_tolto", lg.DatiEvento(ruolo_id=1)) in chiamate)


@pytest.mark.asyncio
async def test_member_update_senza_cambi_non_fa_nulla(cog):
    m = fake_member(1)
    m.guild = fake_guild(GUILD)
    m.nick = None
    m.global_name = None
    await cog.cog.on_member_update(m, m)
    cog.elabora.assert_not_called()


@pytest.mark.asyncio
async def test_user_update_controlla_ogni_server_in_comune(cog):
    m = fake_member(1, "vecchio")
    g1, g2 = fake_guild(1), fake_guild(2)
    g1.get_member = MagicMock(return_value=m)
    cog.bot.guilds = [g1, g2]
    m.nick, m.global_name = None, None
    prima = SimpleNamespace(name="vecchio", global_name=None)
    await cog.cog.on_user_update(prima, SimpleNamespace(id=1, name="vecchio", global_name=None))
    cog.elabora.assert_not_called()
    await cog.cog.on_user_update(prima, SimpleNamespace(id=1, name="nuovo", global_name=None))
    assert cog.elabora.await_count == 1 and cog.elabora.await_args.args[1] is g1


@pytest.mark.asyncio
async def test_presenze_ignorate_finche_l_interruttore_e_spento(cog, monkeypatch):
    monkeypatch.delenv(ev.VARIABILE_STATO, raising=False)
    m = fake_member(1)
    m.guild = fake_guild(GUILD)
    stato = discord.CustomActivity(name="Nitro gratis qui")
    prima, dopo = SimpleNamespace(activities=()), SimpleNamespace(activities=(stato,), guild=m.guild)
    await cog.cog.on_presence_update(prima, dopo)
    cog.elabora.assert_not_called()
    monkeypatch.setenv(ev.VARIABILE_STATO, "1")
    await cog.cog.on_presence_update(prima, dopo)
    assert cog.elabora.await_args.args[3] == "stato" and cog.elabora.await_args.args[4].testo == "Nitro gratis qui"
    cog.elabora.reset_mock()
    await cog.cog.on_presence_update(dopo, dopo)  # stato uguale: niente
    cog.elabora.assert_not_called()


@pytest.mark.asyncio
async def test_caso_manuale_passa_caso_automod_no(cog):
    guild = fake_guild(GUILD)
    m = fake_member(5)
    guild.get_member = MagicMock(return_value=m)
    cog.bot.get_guild = lambda i: guild
    await cog.cog._caso(GUILD, 1, 5, 9, "BAN", "automod", "x")
    cog.elabora.assert_not_called()  # niente giri a vuoto
    await cog.cog._caso(GUILD, 2, 5, 9, "BAN", "manuale", "spam")
    assert cog.elabora.await_args.args[3] == "caso" and cog.elabora.await_args.args[4].tipo_caso == "ban"
    assert cog.elabora.await_args.kwargs["user_id"] == 5


@pytest.mark.asyncio
async def test_il_cog_si_registra_per_i_casi_e_si_toglie():
    cog = cog_mod.EventiAutomodCog(SimpleNamespace(guilds=[]))
    await cog.cog_load()
    assert cog._caso in caso_eventi._ascoltatori
    await cog.cog_unload()
    assert cog._caso not in caso_eventi._ascoltatori


# ------------------------------------------------------------------ registro dei casi

@pytest.mark.asyncio
async def test_un_ascoltatore_che_sbaglia_non_ferma_gli_altri():
    visti = []

    async def rotto(*a):
        raise RuntimeError("no")

    async def buono(*a):
        visti.append(a)

    caso_eventi.registra(rotto)
    caso_eventi.registra(buono)
    caso_eventi.registra(buono)  # due volte = una
    try:
        await caso_eventi.notifica(1, 2, 3, 4, "warn", "manuale", "m")
    finally:
        caso_eventi.rimuovi(rotto)
        caso_eventi.rimuovi(buono)
    assert visti == [(1, 2, 3, 4, "warn", "manuale", "m")]


@pytest.mark.asyncio
async def test_create_case_avvisa_chi_ascolta(clean_db, monkeypatch):
    from core import log_forum_service
    from core.repositories.moderation_repo import ModerationRepository

    monkeypatch.setattr(log_forum_service, "notifica_caso", AsyncMock())
    visti = AsyncMock()
    caso_eventi.registra(visti)
    try:
        repo = ModerationRepository(pool_provider=lambda: clean_db)
        numero = await repo.create_case(GUILD, 2, 3, "ban", "spam")
    finally:
        caso_eventi.rimuovi(visti)
    visti.assert_awaited_once_with(GUILD, numero, 2, 3, "ban", "manuale", "spam")

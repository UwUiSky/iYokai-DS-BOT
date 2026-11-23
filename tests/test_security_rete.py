"""
tests/test_security_rete.py
===========================
Rete di protezione tra server (VER-025, D111, D112): regole pure, database, avvisi agli altri server, timeout per account
compromessi, rete facoltativa dei ban. Discord finto, database vero.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from core import rete_protezione as rete
from core import rete_protezione_logic as lg
from core.repositories.rete_repo import ReteRepository

ORA = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
VECCHIO = ORA - timedelta(days=30)


# VER-025
def test_categoria_dal_motivo_solo_le_gravi():
    assert lg.categoria_da_motivo("Truffa, phishing o link malevoli") == "truffa"
    assert lg.categoria_da_motivo("Pubblicità o inviti ad altri server non autorizzati") == "spam_server"
    assert lg.categoria_da_motivo("Minacce gravi verso altri membri") == "tossicita_grave"
    assert lg.categoria_da_motivo("Account rubato: messaggi uguali") == "account_compromesso"
    assert lg.categoria_da_motivo("Flood: troppi messaggi") is None and lg.categoria_da_motivo(None) is None


# VER-025
def test_gravita_un_ban_alza_di_un_gradino():
    assert lg.gravita_di("spam_server") == "media" and lg.gravita_di("spam_server", "ban") == "alta"
    assert lg.gravita_di("account_compromesso", "ban") == "critica"


# VER-025
def test_server_piccolo_nuovo_bloccato_o_troppo_attivo_non_segnala():
    f = lg.origine_puo_segnalare
    assert f(500, VECCHIO, ORA, False) is None
    assert f(10, VECCHIO, ORA, False) == "piccolo"
    assert f(500, ORA - timedelta(days=1), ORA, False) == "nuovo" and f(500, None, ORA, False) == "nuovo"
    assert f(500, VECCHIO, ORA, True) == "bloccato"
    assert f(500, VECCHIO, ORA, False, segnalazioni_oggi=lg.TETTO_SEGNALAZIONI_ORIGINE_AL_GIORNO) == "tetto"


# VER-025
def test_ricezione_spenta_o_tetto_raggiunto():
    assert lg.destinazione_puo_ricevere(True, 0) and not lg.destinazione_puo_ricevere(False, 0)
    assert not lg.destinazione_puo_ricevere(True, lg.TETTO_CONSEGNE_AL_GIORNO)


# VER-025
def test_durata_timeout_nei_limiti_di_discord():
    assert lg.ore_timeout_valide(24) == 24 and lg.ore_timeout_valide(0) == 1
    assert lg.ore_timeout_valide(99999) == 672 and lg.ore_timeout_valide("x") == 24 and lg.ore_timeout_valide(True) == 24


# VER-025
def test_mai_proprietari_bot_o_chi_sta_sopra():
    f = lambda **k: lg.bot_puo_colpire(**{"e_proprietario": False, "e_bot": False, "e_il_nostro_bot": False, "bot_sopra": True, "bot_ha_permesso": True, **k})  # noqa: E731
    assert f() is None
    assert f(e_proprietario=True) == "proprietario" and f(e_bot=True) == "bot" and f(e_il_nostro_bot=True) == "bot"
    assert f(bot_sopra=False) == "gerarchia" and f(bot_ha_permesso=False) == "permesso"


# VER-025
def test_il_motivo_della_rete_non_contiene_testi_di_utenti_ed_e_corto():
    assert "compromesso" in lg.motivo_rete("account_compromesso") and len(lg.motivo_rete("x", "n" * 900)) <= 512


# VER-025
def test_proposta_di_ban_niente_catene_e_solo_tra_aderenti():
    f = lambda **k: lg.proposta_ammessa(**{"origine": 1, "destinazione": 2, "origine_aderisce": True, "dest_aderisce": True, "origine_caso": "manuale", **k})  # noqa: E731
    assert f() is None
    assert f(origine_caso="rete") == "catena" and f(destinazione=1) == "stesso_server"
    assert f(dest_aderisce=False) == "non_aderente" and f(origine_aderisce=False) == "non_aderente"


# VER-025
def test_chi_puo_togliere_il_timeout():
    assert lg.puo_togliere_timeout(e_proprietario_bot=True, e_proprietario_server=False)
    assert lg.puo_togliere_timeout(e_proprietario_bot=False, e_proprietario_server=True)
    assert not lg.puo_togliere_timeout(e_proprietario_bot=False, e_proprietario_server=False)


# --- database -----------------------------------------------------------
@pytest.fixture
def repo(db_pool, clean_db, monkeypatch):
    from core.repositories import rete_repo as modulo

    monkeypatch.setattr(modulo.rete_repo, "_pool_provider", lambda: db_pool)  # chi usa il repo globale (i tasti) legge lo stesso database
    return ReteRepository(lambda: db_pool)


@pytest.mark.asyncio
async def test_impostazioni_di_base_e_modifica(repo):
    i = await repo.impostazioni(5)
    assert i.ricezione and not i.ban_aderisce and i.timeout_ore == 24 and not i.mostra_origine  # ricezione accesa di base
    await repo.imposta(5, ricezione=False, timeout_ore=48, canale_id=77)
    await repo.imposta(5, ban_aderisce=True, ban_modo="automatico")
    i = await repo.impostazioni(5)
    assert (i.ricezione, i.timeout_ore, i.canale_id, i.ban_aderisce, i.ban_modo) == (False, 48, 77, True, "automatico")
    assert await repo.aderenti_ban() == {5: "automatico"}
    await repo.imposta(5, canale_id=None)
    assert (await repo.impostazioni(5)).canale_id is None


@pytest.mark.asyncio
async def test_impostazioni_con_nomi_o_tipi_strani_si_rifiutano(repo):
    for brutto in ({"guild_id; DROP TABLE x": 1}, {"ricezione": 1}, {"timeout_ore": "24"}, {"ban_modo": "boh"}):
        with pytest.raises(ValueError):
            await repo.imposta(5, **brutto)


@pytest.mark.asyncio
async def test_blocco_del_server_e_segnalazioni_e_consegne(repo):
    assert not await repo.e_bloccato(9)
    await repo.blocca(9, 1, "segnala a caso")
    assert await repo.e_bloccato(9) and [r["guild_id"] for r in await repo.elenco_bloccati()] == [9]
    assert await repo.sblocca(9) and not await repo.sblocca(9)
    sid = await repo.registra_segnalazione(42, 1, "truffa", "alta")
    assert await repo.gia_segnalato(42, "truffa", 24) and not await repo.gia_segnalato(42, "frode", 24)
    await repo.registra_consegna(sid, 2)
    assert await repo.consegne_oggi(2) == 1 and await repo.segnalazioni_origine_oggi(1) == 1


@pytest.mark.asyncio
async def test_proposta_una_sola_decisione_e_niente_doppioni(repo):
    pid = await repo.crea_proposta(42, 1, 2, "truffa")
    assert pid and await repo.crea_proposta(42, 1, 2, "truffa") is None
    assert await repo.decidi(pid, "proposta", "applicato", 7, 3)
    assert not await repo.decidi(pid, "proposta", "applicato", 8)  # secondo tasto: perde
    assert (await repo.proposta(pid))["case_number"] == 3
    with pytest.raises(ValueError):
        await repo.decidi(pid, "proposta", "boh", 1)


@pytest.mark.asyncio
async def test_timeout_della_rete_si_toglie_una_volta(repo):
    await repo.registra_timeout(2, 42, 1, ORA + timedelta(days=400), 5)  # lontano nel futuro: ancora attivo
    assert await repo.timeout_attivo(2, 42)
    assert await repo.annulla_timeout(2, 42, 99) and not await repo.annulla_timeout(2, 42, 99)
    assert not await repo.timeout_attivo(2, 42)


def test_le_tabelle_della_rete_sono_dichiarate_nel_registro_dati():
    from core import data_registry as d

    for nome in ("rete_impostazioni", "rete_segnalazioni", "rete_consegne", "rete_server_bloccati", "rete_timeout", "rete_ban_proposte"):
        assert nome in d.nomi_dichiarati()
    assert d.tabella("rete_segnalazioni").utente == "cancella" and d.tabella("rete_segnalazioni").scadenza.giorni == 90


async def _proposte(pool, user_id, guild_origine):
    return await pool.fetch("SELECT * FROM rete_ban_proposte WHERE user_id = $1 AND guild_origine = $2 ORDER BY id", user_id, guild_origine)


# --- Discord finto --------------------------------------------------------
class Ruolo:
    def __init__(self, posizione): self.p = posizione
    def __gt__(self, altro): return self.p > altro.p


class Membro:
    def __init__(self, uid, posizione=1, bot=False):
        self.id, self.bot, self.top_role = uid, bot, Ruolo(posizione)
        self.timeout = AsyncMock()


class Server:
    def __init__(self, gid, membri=500, owner=1000, utenti=(), posizione_bot=10, permessi=True, entrato=VECCHIO):
        self.id, self.name, self.member_count, self.owner_id = gid, f"Server{gid}", membri, owner
        self.me = SimpleNamespace(
            top_role=Ruolo(posizione_bot), joined_at=entrato,
            guild_permissions=SimpleNamespace(moderate_members=permessi, ban_members=permessi),
        )
        self._m = {m.id: m for m in utenti}
        self.owner = SimpleNamespace(send=AsyncMock())
        self.ban, self.unban = AsyncMock(), AsyncMock()

    def get_member(self, uid): return self._m.get(uid)
    def get_channel(self, _): return None


@pytest.fixture
def mondo(monkeypatch):
    monkeypatch.setattr(rete, "testo_guild", AsyncMock(side_effect=lambda g, k, **v: f"{k} {v}"))
    monkeypatch.setattr(rete.bot_roles, "e_un_nostro_bot", lambda uid, bot: uid == 1)
    crea = AsyncMock(return_value=7)
    monkeypatch.setattr(rete.moderation_repo, "create_case", crea)
    monkeypatch.setattr(rete.moderation_repo, "revoke_case", AsyncMock(return_value=True))
    return crea


def _bot(*server):
    return SimpleNamespace(user=SimpleNamespace(id=1), guilds=list(server), get_guild=lambda g: next((s for s in server if s.id == g), None),
                           fetch_user=AsyncMock())


# VER-025
@pytest.mark.asyncio
async def test_avviso_agli_altri_server_con_utente_e_bot_senza_contenuto(repo, mondo):
    u = Membro(42)
    origine, b, c, d = Server(1, utenti=[u]), Server(2, utenti=[Membro(42)]), Server(3), Server(4, utenti=[Membro(42)])
    await repo.imposta(4, ricezione=False)  # il server 4 non vuole gli avvisi
    r = await rete.segnala(_bot(origine, b, c, d), origine, 42, "truffa", "ban", repo=repo, ora=ORA)
    assert r.rifiuto is None and r.consegnati == 1
    b.owner.send.assert_awaited_once()
    embed = b.owner.send.await_args.kwargs["embed"]
    assert "42" in embed.description and "origine" not in " ".join(f.name for f in embed.fields)  # origine non permessa di base
    c.owner.send.assert_not_awaited() and d.owner.send.assert_not_awaited()
    assert b.owner.send.await_args.kwargs["allowed_mentions"].users is False


# VER-025
@pytest.mark.asyncio
async def test_il_nome_d_origine_c_e_solo_se_il_server_lo_permette(repo, mondo):
    origine, b = Server(1), Server(2, utenti=[Membro(42)])
    await repo.imposta(1, mostra_origine=True)
    await rete.segnala(_bot(origine, b), origine, 42, "frode", repo=repo, ora=ORA)
    assert b.owner.send.await_args.kwargs["embed"].fields[0].value == "Server1"


# VER-025
@pytest.mark.asyncio
async def test_origine_piccola_nuova_o_bloccata_non_fa_partire_avvisi(repo, mondo):
    b = Server(2, utenti=[Membro(42)])
    for origine, atteso in ((Server(1, membri=5), "piccolo"), (Server(1, entrato=ORA - timedelta(hours=2)), "nuovo")):
        assert (await rete.segnala(_bot(origine, b), origine, 42, "truffa", repo=repo, ora=ORA)).rifiuto == atteso
    origine = Server(1)
    await repo.blocca(1, 99, "scorretto")
    assert (await rete.segnala(_bot(origine, b), origine, 42, "truffa", repo=repo, ora=ORA)).rifiuto == "bloccato"
    b.owner.send.assert_not_awaited()


# VER-025
@pytest.mark.asyncio
async def test_stesso_utente_stessa_categoria_una_volta_al_giorno_e_tetto_per_destinazione(repo, mondo):
    origine, b = Server(1), Server(2, utenti=[Membro(42), Membro(43)])
    bot = _bot(origine, b)
    assert (await rete.segnala(bot, origine, 42, "truffa", repo=repo, ora=ORA)).consegnati == 1
    assert (await rete.segnala(bot, origine, 42, "truffa", repo=repo, ora=ORA)).rifiuto == "gia_segnalato"
    for _ in range(lg.TETTO_CONSEGNE_AL_GIORNO):
        sid = await repo.registra_segnalazione(99, 8, "frode", "alta")
        await repo.registra_consegna(sid, 2)
    assert (await rete.segnala(bot, origine, 43, "frode", repo=repo, ora=ORA)).consegnati == 0  # tetto del server 2 raggiunto


# VER-025
@pytest.mark.asyncio
async def test_non_si_avvisa_per_proprietari_bot_e_per_il_bot_stesso(repo, mondo):
    origine = Server(1)
    b = Server(2, owner=42, utenti=[Membro(42)])
    assert (await rete.segnala(_bot(origine, b), origine, 42, "truffa", repo=repo, ora=ORA)).consegnati == 0
    assert (await rete.segnala(_bot(origine, b), origine, 1, "truffa", repo=repo, ora=ORA)).rifiuto == "categoria"
    c = Server(3, utenti=[Membro(50, bot=True)])
    assert (await rete.segnala(_bot(origine, c), origine, 50, "truffa", repo=repo, ora=ORA)).consegnati == 0


# VER-025
@pytest.mark.asyncio
async def test_account_compromesso_timeout_in_tutti_i_server_con_gerarchia(repo, mondo):
    u1, u2, u3, u4 = Membro(42), Membro(42), Membro(42, posizione=99), Membro(42)
    a, b = Server(1, utenti=[u1]), Server(2, utenti=[u2])
    c = Server(3, utenti=[u3])  # l'utente sta sopra il bot
    d = Server(4, utenti=[u4], owner=42)  # l'utente è il proprietario
    e = Server(5, utenti=[Membro(42)], permessi=False)  # il bot non ha il permesso
    await repo.imposta(2, timeout_ore=48)
    n = await rete.compromesso(_bot(a, b, c, d, e), 42, 1, repo=repo, ora=ORA)
    assert n == 2
    a_fino = u1.timeout.await_args.args[0]
    assert a_fino == ORA + timedelta(hours=24) and u2.timeout.await_args.args[0] == ORA + timedelta(hours=48)  # durata del server
    u3.timeout.assert_not_awaited() and u4.timeout.assert_not_awaited()
    assert mondo.await_count == 2 and mondo.await_args.kwargs["origine"] == "rete" and mondo.await_args.args[3] == "timeout"
    assert a.owner.send.await_count == 1 and b.owner.send.await_count == 1  # avviso agli owner
    assert await rete.compromesso(_bot(a, b), 1, 1, repo=repo, ora=ORA) == 0  # mai il bot stesso


# VER-025
@pytest.mark.asyncio
async def test_timeout_scritto_nel_database_e_tolto_dal_proprietario(repo, mondo):
    u = Membro(42)
    a = Server(1, utenti=[u])
    await rete.compromesso(_bot(a), 42, 9, repo=repo, ora=datetime.now(timezone.utc))
    assert await repo.timeout_attivo(1, 42)
    assert await rete.togli_timeout(_bot(a), a, 42, 77, repo=repo)
    u.timeout.assert_awaited_with(None, reason="Timeout della rete tolto da 77")
    assert not await rete.togli_timeout(_bot(a), a, 42, 77, repo=repo)  # già tolto


# VER-025
@pytest.mark.asyncio
async def test_rete_ban_proposta_solo_tra_aderenti_dove_l_utente_c_e(repo, mondo):
    a, b, c, d = Server(1, utenti=[Membro(42)]), Server(2, utenti=[Membro(42)]), Server(3, utenti=[Membro(42)]), Server(4)
    for g in (1, 2, 4):
        await repo.imposta(g, ban_aderisce=True)
    visti = []

    async def vista(guild, az, x, y):
        visti.append((guild.id, az, x))
        return None

    n = await rete.dopo_ban(_bot(a, b, c, d), a, 42, "truffa", "manuale", repo=repo, crea_vista=vista)
    assert n == 1 and visti and visti[0][:2] == (2, "ap")  # solo il 2: il 3 non aderisce, il 4 non ha l'utente
    b.owner.send.assert_awaited_once() and c.owner.send.assert_not_awaited()
    b.ban.assert_not_awaited()  # proposta: nessun ban finché non preme il tasto
    assert await rete.dopo_ban(_bot(a, b, c, d), a, 42, "truffa", "manuale", repo=repo) == 0  # niente doppioni


# VER-025
@pytest.mark.asyncio
async def test_rete_ban_automatico_con_caso_e_si_puo_annullare(repo, mondo):
    a, b = Server(1, utenti=[Membro(42)]), Server(2, utenti=[Membro(42)])
    await repo.imposta(1, ban_aderisce=True)
    await repo.imposta(2, ban_aderisce=True, ban_modo="automatico")
    assert await rete.dopo_ban(_bot(a, b), a, 42, "frode", "automod", repo=repo) == 1
    b.ban.assert_awaited_once()
    assert mondo.await_args.kwargs["origine"] == "rete" and mondo.await_args.args[3] == "ban"
    prop = await repo.ultima_applicata(42, 2)
    assert prop["stato"] == "applicato" and prop["case_number"] == 7
    assert await rete.annulla_ban(_bot(a, b), b, prop["id"], 55, repo=repo)
    b.unban.assert_awaited_once()
    assert (await repo.proposta(prop["id"]))["stato"] == "annullato"
    assert not await rete.annulla_ban(_bot(a, b), b, prop["id"], 55, repo=repo)


# VER-025
@pytest.mark.asyncio
async def test_un_ban_che_viene_dalla_rete_non_ne_fa_partire_altri(repo, mondo):
    a, b = Server(1, utenti=[Membro(42)]), Server(2, utenti=[Membro(42)])
    for g in (1, 2):
        await repo.imposta(g, ban_aderisce=True, ban_modo="automatico")
    assert await rete.dopo_ban(_bot(a, b), a, 42, "truffa", "rete", repo=repo) == 0
    b.ban.assert_not_awaited()


# VER-025
@pytest.mark.asyncio
async def test_due_tasti_insieme_un_solo_ban_e_chi_non_puo_colpire_fallisce(db_pool, repo, mondo):
    a, b = Server(1, utenti=[Membro(42)]), Server(2, utenti=[Membro(42)])
    for g in (1, 2):
        await repo.imposta(g, ban_aderisce=True)
    await rete.dopo_ban(_bot(a, b), a, 42, "truffa", "manuale", repo=repo)
    pid = (await _proposte(db_pool, 42, 1))[0]["id"]
    bot = _bot(a, b)
    assert await rete.applica_ban(bot, b, pid, 7, repo=repo) == "ok"
    assert await rete.applica_ban(bot, b, pid, 8, repo=repo) == "gia_deciso"
    assert b.ban.await_count == 1
    # utente sopra il bot: la proposta passa a «fallito», nessun ban
    c = Server(3, utenti=[Membro(42, posizione=99)])
    await repo.imposta(3, ban_aderisce=True)
    await rete.dopo_ban(_bot(a, c), a, 42, "truffa", "manuale", repo=repo)
    pid3 = (await _proposte(db_pool, 42, 1))[-1]["id"]
    assert await rete.applica_ban(_bot(a, c), c, pid3, 7, repo=repo) == "gerarchia" and c.ban.await_count == 0
    # una proposta di un altro server non si applica qui
    assert await rete.applica_ban(bot, a, pid, 7, repo=repo) == "gia_deciso"


# VER-025
@pytest.mark.asyncio
async def test_ascoltatore_dei_casi_solo_azioni_gravi_e_mai_casi_della_rete(repo, mondo, monkeypatch):
    a, b = Server(1, utenti=[Membro(42)]), Server(2, utenti=[Membro(42)])
    bot = _bot(a, b)
    chiamate = []
    monkeypatch.setattr(rete, "segnala", AsyncMock(side_effect=lambda *x, **k: chiamate.append(x[2:])))
    monkeypatch.setattr(rete, "dopo_ban", AsyncMock())
    monkeypatch.setattr(rete, "compromesso", AsyncMock())
    ascolta = rete.ascoltatore_casi(bot)
    await ascolta(1, 1, 42, 5, "warn", "manuale", "Truffa o phishing")  # un avviso non basta
    await ascolta(1, 2, 42, 5, "ban", "rete", "Truffa o phishing")  # caso della rete: mai di nuovo
    await ascolta(1, 3, 42, 5, "ban", "manuale", "Insulti")  # motivo non grave
    assert chiamate == []
    await ascolta(1, 4, 42, 5, "ban", "manuale", "Truffa, phishing o link malevoli")
    assert chiamate == [(42, "truffa", "ban")] and rete.dopo_ban.await_count == 1 and rete.compromesso.await_count == 0
    await ascolta(1, 5, 42, 5, "timeout", "automod", "Account rubato")
    assert rete.compromesso.await_count == 1 and rete.dopo_ban.await_count == 1


# --- comandi, tasti e punti di aggancio -----------------------------------
def _interazione(utente_id, guild, client=None):
    from tests.support.discord_fakes import fake_interaction, fake_member

    i = fake_interaction(guild=guild, user=fake_member(utente_id))
    i.client = client
    return i


def _cog(bot=None):
    from cogs.security.rete_protezione import ReteProtezioneCog

    return ReteProtezioneCog(bot or _bot())


def _testo(mp, monkeypatch):
    from cogs.security import rete_protezione as cog

    monkeypatch.setattr(cog, "testo_per", AsyncMock(side_effect=lambda i, k, **v: f"{k} {v}"))
    monkeypatch.setattr(cog.rete, "testo_guild", AsyncMock(side_effect=lambda g, k, **v: f"{k} {v}"))


# VER-025
@pytest.mark.asyncio
async def test_comando_impostazioni_salva_e_mostra(repo, monkeypatch):
    from cogs.security import rete_protezione as cog

    _testo(None, monkeypatch)
    monkeypatch.setattr(cog, "rete_repo", repo)
    g = Server(5)
    canale = SimpleNamespace(id=900, permissions_for=lambda me: SimpleNamespace(send_messages=True, embed_links=True))
    i = _interazione(7, g)
    await _cog().impostazioni.callback(_cog(), i, ricezione=False, canale=canale, togli_canale=None, mostra_origine=True, timeout_ore=48)
    s = await repo.impostazioni(5)
    assert (s.ricezione, s.canale_id, s.mostra_origine, s.timeout_ore) == (False, 900, True, 48)
    assert i.response.send_message.await_args.kwargs["allowed_mentions"].users is False
    i2 = _interazione(7, g)
    await _cog().impostazioni.callback(_cog(), i2, None, None, True, None, None)  # solo togliere il canale
    assert (await repo.impostazioni(5)).canale_id is None


# VER-025
@pytest.mark.asyncio
async def test_comando_ban_aderisci_e_modo(repo, monkeypatch):
    from cogs.security import rete_protezione as cog

    _testo(None, monkeypatch)
    monkeypatch.setattr(cog, "rete_repo", repo)
    g = Server(5)
    await _cog().ban_rete.callback(_cog(), _interazione(7, g), True, SimpleNamespace(value="automatico"), None)
    assert (await repo.impostazioni(5)).ban_aderisce and (await repo.impostazioni(5)).ban_modo == "automatico"
    await _cog().ban_rete.callback(_cog(), _interazione(7, g), False, None, None)
    assert not (await repo.impostazioni(5)).ban_aderisce


# VER-025
@pytest.mark.asyncio
async def test_togliere_il_timeout_solo_proprietario_del_server_o_del_bot(repo, mondo, monkeypatch):
    from cogs.security import rete_protezione as cog
    from core import rete_protezione_vista as vista

    _testo(None, monkeypatch)
    u = Membro(42)
    g = Server(1, owner=1000, utenti=[u])
    bot = _bot(g)
    await rete.compromesso(bot, 42, 9, repo=repo, ora=datetime.now(timezone.utc))
    utente = SimpleNamespace(id=42)
    estraneo = _interazione(2000, g)
    await _cog(bot).timeout_togli.callback(_cog(bot), estraneo, utente)
    assert "rete_non_permesso" in estraneo.response.send_message.await_args.args[0]
    assert await repo.timeout_attivo(1, 42)  # un estraneo non ha tolto niente
    assert vista.puo_togliere_timeout(g, 123456789) and vista.puo_togliere_timeout(g, 1000) and not vista.puo_togliere_timeout(g, 2000)


# VER-025
def test_chi_puo_decidere_un_ban_ricontrollato_adesso(monkeypatch):
    from core import rete_protezione_vista as vista

    g = Server(1, owner=1000)
    g._m = {7: SimpleNamespace(guild_permissions=SimpleNamespace(ban_members=True)), 8: SimpleNamespace(guild_permissions=SimpleNamespace(ban_members=False))}
    assert vista.puo_decidere_ban(g, 7) and vista.puo_decidere_ban(g, 1000) and vista.puo_decidere_ban(g, 123456789)
    assert not vista.puo_decidere_ban(g, 8) and not vista.puo_decidere_ban(g, 9) and not vista.puo_decidere_ban(None, 7)


# VER-025
@pytest.mark.asyncio
async def test_il_tasto_di_un_estraneo_non_banna(db_pool, repo, mondo, monkeypatch):
    from core import rete_protezione_vista as vista

    monkeypatch.setattr(vista, "rete_repo", repo)
    monkeypatch.setattr(vista, "testo_per", AsyncMock(side_effect=lambda i, k, **v: k))
    a, b = Server(1, utenti=[Membro(42)]), Server(2, utenti=[Membro(42)], owner=1000)
    for g in (1, 2):
        await repo.imposta(g, ban_aderisce=True)
    await rete.dopo_ban(_bot(a, b), a, 42, "truffa", "manuale", repo=repo)
    pid = (await _proposte(db_pool, 42, 1))[0]["id"]
    bot = _bot(a, b)
    tasto = vista.BottoneRete("ap", pid, 0)
    estraneo = _interazione(2000, b, client=bot)
    await tasto.callback(estraneo)
    assert estraneo.response.send_message.await_args.args[0] == "rete_non_permesso" and b.ban.await_count == 0
    giusto = _interazione(1000, b, client=bot)
    await tasto.callback(giusto)
    assert b.ban.await_count == 1 and giusto.followup.send.await_args.args[0] == "rete_ban_applicato"
    ancora = _interazione(1000, b, client=bot)
    await tasto.callback(ancora)
    assert b.ban.await_count == 1  # secondo click: già deciso


# VER-025
@pytest.mark.asyncio
async def test_il_tasto_non_decide_su_proposte_di_un_altro_server(db_pool, repo, mondo, monkeypatch):
    from core import rete_protezione_vista as vista

    monkeypatch.setattr(vista, "rete_repo", repo)
    monkeypatch.setattr(vista, "testo_per", AsyncMock(side_effect=lambda i, k, **v: k))
    a, b = Server(1, utenti=[Membro(42)], owner=3000), Server(2, utenti=[Membro(42)], owner=1000)
    for g in (1, 2):
        await repo.imposta(g, ban_aderisce=True)
    await rete.dopo_ban(_bot(a, b), a, 42, "truffa", "manuale", repo=repo)
    pid = (await _proposte(db_pool, 42, 1))[0]["id"]
    # il proprietario del server 1 (origine) prova a decidere la proposta destinata al server 2
    intruso = _interazione(3000, a, client=_bot(a, b))
    await vista.BottoneRete("ap", pid, 0).callback(intruso)
    assert intruso.response.send_message.await_args.args[0] == "rete_non_permesso" and b.ban.await_count == 0


# VER-025
def test_il_modello_del_tasto_riconosce_solo_i_suoi_id():
    import re

    from core.rete_protezione_vista import MODELLO

    assert re.fullmatch(MODELLO, "rete:to:123:456") and re.fullmatch(MODELLO, "rete:ap:9:0")
    assert not re.fullmatch(MODELLO, "rete:xx:1:2") and not re.fullmatch(MODELLO, "rete:to:1; DROP:2")


# VER-025
@pytest.mark.asyncio
async def test_il_blocco_dei_server_e_solo_del_proprietario_del_bot(repo, monkeypatch):
    from cogs.security import rete_protezione as cog

    _testo(None, monkeypatch)
    monkeypatch.setattr(cog, "rete_repo", repo)
    azione = lambda v: SimpleNamespace(value=v)  # noqa: E731
    estraneo = _interazione(7, Server(1))
    await _cog().rete_owner.callback(_cog(), estraneo, azione("blocca"), "12345", None)
    assert not await repo.e_bloccato(12345) and "rete_owner_solo_proprietario" in estraneo.response.send_message.await_args.args[0]
    owner = _interazione(123456789, Server(1))
    await _cog().rete_owner.callback(_cog(), owner, azione("blocca"), "12345", "segnala a caso")
    assert await repo.e_bloccato(12345)
    await _cog().rete_owner.callback(_cog(), _interazione(123456789, Server(1)), azione("sblocca"), "12345", None)
    assert not await repo.e_bloccato(12345)
    brutto = _interazione(123456789, Server(1))
    await _cog().rete_owner.callback(_cog(), brutto, azione("blocca"), "12x45", None)
    assert "rete_owner_id_non_valido" in brutto.response.send_message.await_args.args[0]


# VER-025
@pytest.mark.asyncio
async def test_account_rubato_e_anti_nuke_avviano_la_rete(monkeypatch):
    import pathlib

    from core import account_rubato

    chiamate = []
    monkeypatch.setattr(rete, "avvia_compromesso", lambda *a, **k: chiamate.append((a[1:], k)))
    monkeypatch.setattr(account_rubato, "_gestisci", AsyncMock(return_value=True))
    sintesi = SimpleNamespace(user_id=42, guild_ids=(10, 11))
    assert await account_rubato.gestisci(_bot(), sintesi, None)
    assert chiamate == [((42, 10), {"escludi": (10, 11)})]  # i server dove l'AutoMod ha già agito non si ripetono
    account_rubato._gestisci.return_value = False
    await account_rubato.gestisci(_bot(), sintesi, None)
    assert len(chiamate) == 1
    sorgente = (pathlib.Path(__file__).resolve().parent.parent / "cogs/security/anti_nuke.py").read_text(encoding="utf-8")
    assert "rete_protezione.avvia_compromesso(" in sorgente

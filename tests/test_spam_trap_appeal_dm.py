"""
tests/test_spam_trap_appeal_dm.py
=====================================
SEC-12: i DM ricevuti dal bot non devono più fare una query per ogni
server (moderation_repo.get_active_cases_for_user_across_guilds
sostituisce il giro su self.bot.guilds) e non più di un DM viene
elaborato ogni 30 secondi per utente.

BUG-22: il limite conta solo i DM ELABORATI. Un DM scartato non
allunga l'attesa, altrimenti chi scrive più spesso di ogni 30 secondi
resterebbe ignorato per sempre.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from cogs.security.spam_trap import BAN_ACTION_TYPE, SpamTrapCog
from core.spam_trap_logic import DM_APPEAL_PROCESSING_COOLDOWN_SECONDS
from core.spam_trap_rate_tracker import LimiteDmAppello, limite_dm_appello

ID_UTENTE = 1000001
ISTANTE_ZERO = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def limite_dm_azzerato():
    """
    Il limite sui DM è un singleton di processo: va azzerato prima e
    dopo ogni test, così i test possono usare tutti lo stesso utente
    senza influenzarsi (prima ognuno usava un id diverso per aggirarlo).
    """
    limite_dm_appello.azzera()
    yield
    limite_dm_appello.azzera()


class _OrologioFinto(datetime):
    """`datetime` con un `now()` comandato dal test."""

    istante = ISTANTE_ZERO

    @classmethod
    def now(cls, tz=None):
        return cls.istante


@pytest.fixture
def orologio(monkeypatch):
    import cogs.security.spam_trap as spam_trap_module

    monkeypatch.setattr(_OrologioFinto, "istante", ISTANTE_ZERO)
    monkeypatch.setattr(spam_trap_module, "datetime", _OrologioFinto)
    return _OrologioFinto


class _FakeGuild:
    def __init__(self, guild_id: int, name: str = "Server") -> None:
        self.id = guild_id
        self.name = name


class _FakeBot:
    def __init__(self, guilds: list[_FakeGuild]) -> None:
        self._guilds = {g.id: g for g in guilds}

    def get_guild(self, guild_id: int):
        return self._guilds.get(guild_id)


class _FakeChannel:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, content: str = None, **kwargs) -> None:
        self.sent.append(content)


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.mention = f"<@{user_id}>"

    def __str__(self) -> str:
        return f"utente#{self.id}"


class _FakeMessage:
    def __init__(self, author: _FakeUser, content: str = "") -> None:
        self.author = author
        self.content = content
        self.channel = _FakeChannel()


class _CasoFinto:
    def __init__(self, guild_id: int, case_number: int) -> None:
        self.guild_id = guild_id
        self.case_number = case_number


@pytest.fixture
def cog_con_repo_finto(monkeypatch):
    import cogs.security.spam_trap as spam_trap_module

    moderation_repo_finto = AsyncMock()
    moderation_repo_finto.get_active_cases_for_user_across_guilds.return_value = []
    monkeypatch.setattr(spam_trap_module, "moderation_repo", moderation_repo_finto)

    spam_trap_repo_finto = AsyncMock()
    monkeypatch.setattr(spam_trap_module, "spam_trap_repo", spam_trap_repo_finto)

    guild = _FakeGuild(100)
    bot = _FakeBot([guild])
    cog = SpamTrapCog(bot=bot)
    return cog, moderation_repo_finto, spam_trap_repo_finto, guild


class TestUnaSolaQuery:
    @pytest.mark.asyncio
    async def test_nessun_caso_attivo_usa_una_sola_query(self, cog_con_repo_finto):
        cog, moderation_repo_finto, _, _ = cog_con_repo_finto
        messaggio = _FakeMessage(_FakeUser(ID_UTENTE))

        await cog._handle_possible_appeal(messaggio)

        moderation_repo_finto.get_active_cases_for_user_across_guilds.assert_awaited_once_with(
            ID_UTENTE, BAN_ACTION_TYPE
        )
        # Il vecchio metodo (una query per server) non deve più essere
        # chiamato.
        moderation_repo_finto.get_latest_active_case.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_nessun_caso_attivo_non_manda_nessun_messaggio(self, cog_con_repo_finto):
        cog, _, _, _ = cog_con_repo_finto
        messaggio = _FakeMessage(_FakeUser(ID_UTENTE))

        await cog._handle_possible_appeal(messaggio)

        assert messaggio.channel.sent == []


class TestFlussoConCasoAttivo:
    @pytest.mark.asyncio
    async def test_caso_attivo_ma_appello_recente_rifiutato(self, cog_con_repo_finto):
        cog, moderation_repo_finto, spam_trap_repo_finto, guild = cog_con_repo_finto
        moderation_repo_finto.get_active_cases_for_user_across_guilds.return_value = [
            _CasoFinto(guild_id=guild.id, case_number=1)
        ]
        spam_trap_repo_finto.get_last_appeal.return_value = datetime.now(timezone.utc)

        messaggio = _FakeMessage(_FakeUser(ID_UTENTE))
        await cog._handle_possible_appeal(messaggio)

        assert any("24 hours" in (testo or "") for testo in messaggio.channel.sent)

    @pytest.mark.asyncio
    async def test_caso_in_un_server_che_il_bot_ha_lasciato_viene_ignorato(
        self, cog_con_repo_finto
    ):
        # self.bot.get_guild(...) restituisce None per un server che
        # il bot non frequenta più — quel caso non deve contare come
        # candidato.
        cog, moderation_repo_finto, _, _ = cog_con_repo_finto
        moderation_repo_finto.get_active_cases_for_user_across_guilds.return_value = [
            _CasoFinto(guild_id=999999, case_number=1)
        ]

        messaggio = _FakeMessage(_FakeUser(ID_UTENTE))
        await cog._handle_possible_appeal(messaggio)

        assert messaggio.channel.sent == []


class TestRateLimitDM:
    @pytest.mark.asyncio
    async def test_secondo_dm_entro_30_secondi_viene_ignorato(self, cog_con_repo_finto):
        cog, moderation_repo_finto, _, _ = cog_con_repo_finto
        utente = _FakeUser(ID_UTENTE)

        await cog._handle_possible_appeal(_FakeMessage(utente))
        await cog._handle_possible_appeal(_FakeMessage(utente))

        assert moderation_repo_finto.get_active_cases_for_user_across_guilds.await_count == 1

    @pytest.mark.asyncio
    async def test_dm_scartati_non_allungano_l_attesa(self, cog_con_repo_finto, orologio):
        # BUG-22: DM a 0, 10, 35 e 65 secondi. Il secondo viene
        # scartato (10 s dopo il primo elaborato); il terzo e il quarto
        # sono a 35 e 30 secondi dall'ultimo ELABORATO, quindi passano.
        # Col vecchio conteggio (anche gli scartati) passava solo il primo.
        cog, moderation_repo_finto, _, _ = cog_con_repo_finto
        query = moderation_repo_finto.get_active_cases_for_user_across_guilds
        utente = _FakeUser(ID_UTENTE)

        elaborati = []
        for secondi in (0, 10, 35, 65):
            orologio.istante = ISTANTE_ZERO + timedelta(seconds=secondi)
            prima = query.await_count
            await cog._handle_possible_appeal(_FakeMessage(utente))
            elaborati.append(query.await_count > prima)

        assert elaborati == [True, False, True, True]

    @pytest.mark.asyncio
    async def test_chi_scrive_ogni_10_secondi_viene_comunque_ascoltato(
        self, cog_con_repo_finto, orologio
    ):
        cog, moderation_repo_finto, _, _ = cog_con_repo_finto
        utente = _FakeUser(ID_UTENTE)

        for secondi in range(0, 130, 10):
            orologio.istante = ISTANTE_ZERO + timedelta(seconds=secondi)
            await cog._handle_possible_appeal(_FakeMessage(utente))

        # 0, 30, 60, 90, 120: uno ogni 30 secondi, non uno solo.
        assert moderation_repo_finto.get_active_cases_for_user_across_guilds.await_count == 5

    @pytest.mark.asyncio
    async def test_utenti_diversi_non_si_bloccano_a_vicenda(self, cog_con_repo_finto):
        cog, moderation_repo_finto, _, _ = cog_con_repo_finto

        await cog._handle_possible_appeal(_FakeMessage(_FakeUser(1000006)))
        await cog._handle_possible_appeal(_FakeMessage(_FakeUser(1000007)))

        assert moderation_repo_finto.get_active_cases_for_user_across_guilds.await_count == 2

    @pytest.mark.asyncio
    async def test_la_risposta_a_quale_server_non_viene_scartata(self, monkeypatch, orologio):
        # Con ban attivi in due server il bot chiede "quale server?".
        # La risposta arriva di solito entro pochi secondi: non deve
        # essere fermata dal limite dei 30 secondi.
        import cogs.security.spam_trap as spam_trap_module

        moderation_repo_finto = AsyncMock()
        moderation_repo_finto.get_active_cases_for_user_across_guilds.return_value = [
            _CasoFinto(100, 1),
            _CasoFinto(200, 1),
        ]
        monkeypatch.setattr(spam_trap_module, "moderation_repo", moderation_repo_finto)
        monkeypatch.setattr(spam_trap_module, "spam_trap_repo", AsyncMock())
        cog = SpamTrapCog(bot=_FakeBot([_FakeGuild(100, "Alpha"), _FakeGuild(200, "Beta")]))
        utente = _FakeUser(ID_UTENTE)
        query = moderation_repo_finto.get_active_cases_for_user_across_guilds

        primo = _FakeMessage(utente, "voglio fare appello")
        await cog._handle_possible_appeal(primo)
        assert "multiple servers" in primo.channel.sent[0]

        # Niente altro deve partire dopo la domanda: fermiamo qui il
        # flusso dell'appello vero, che non è l'oggetto di questo test.
        monkeypatch.setattr(spam_trap_module, "latest_case_per_guild", lambda casi: [])
        orologio.istante = ISTANTE_ZERO + timedelta(seconds=5)
        await cog._handle_possible_appeal(_FakeMessage(utente, "Alpha"))

        assert query.await_count == 2


class TestLimiteDmAppello:
    def test_registra_solo_i_dm_elaborati(self):
        limite = LimiteDmAppello()
        attesa = DM_APPEAL_PROCESSING_COOLDOWN_SECONDS

        esiti = [
            limite.puo_elaborare(1, ISTANTE_ZERO + timedelta(seconds=s), attesa)
            for s in (0, 10, 35, 65)
        ]

        assert esiti == [True, False, True, True]

    def test_non_cresce_oltre_la_dimensione_massima(self):
        limite = LimiteDmAppello(max_size=3)

        for user_id in range(10):
            limite.puo_elaborare(user_id, ISTANTE_ZERO, 30)

        assert len(limite) == 3

    def test_azzera_dimentica_tutti(self):
        limite = LimiteDmAppello()
        limite.puo_elaborare(1, ISTANTE_ZERO, 30)

        limite.azzera()

        assert limite.puo_elaborare(1, ISTANTE_ZERO, 30) is True

    def test_dimentica_riapre_subito_per_quell_utente(self):
        limite = LimiteDmAppello()
        attesa = DM_APPEAL_PROCESSING_COOLDOWN_SECONDS

        assert limite.puo_elaborare(1, ISTANTE_ZERO, attesa) is True
        limite.dimentica(1)

        assert limite.puo_elaborare(1, ISTANTE_ZERO + timedelta(seconds=1), attesa) is True

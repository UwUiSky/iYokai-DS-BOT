"""
tests/test_invite_tracker.py
===============================
Test di core/invite_tracker.py con oggetti Guild/Invite finti
minimali (espongono solo gli attributi realmente usati: .id per
Guild, .code/.uses/.inviter per Invite) — non serve una connessione
Discord vera per verificare la logica di cache e refresh.
"""

import asyncio

import pytest

from core.invite_tracker import InviteTracker


class _FakeInviter:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeInvite:
    def __init__(self, code: str, uses: int, inviter_id: int | None) -> None:
        self.code = code
        self.uses = uses
        self.inviter = _FakeInviter(inviter_id) if inviter_id is not None else None


class _FakeGuild:
    def __init__(self, guild_id: int, invites: list[_FakeInvite]) -> None:
        self.id = guild_id
        self._invites = invites

    async def invites(self) -> list[_FakeInvite]:
        return self._invites


@pytest.mark.asyncio
async def test_refresh_guild_popola_la_cache():
    tracker = InviteTracker()
    guild = _FakeGuild(100, [_FakeInvite("abc123", uses=5, inviter_id=42)])

    await tracker.refresh_guild(guild)

    assert tracker._cache.get(100) == {"abc123": 5}
    assert tracker._inviters.get(100) == {"abc123": 42}


@pytest.mark.asyncio
async def test_refresh_guild_con_invito_senza_inviter():
    # Un invito può non avere un inviter noto (es. widget invite).
    tracker = InviteTracker()
    guild = _FakeGuild(100, [_FakeInvite("xyz", uses=1, inviter_id=None)])

    await tracker.refresh_guild(guild)

    assert tracker._inviters.get(100)["xyz"] is None


@pytest.mark.asyncio
async def test_find_used_invite_identifica_il_codice_usato():
    tracker = InviteTracker()
    guild_v1 = _FakeGuild(100, [_FakeInvite("abc123", uses=5, inviter_id=42)])
    await tracker.refresh_guild(guild_v1)

    # Simula: l'invito "abc123" è stato usato, uses sale a 6.
    guild_v2 = _FakeGuild(100, [_FakeInvite("abc123", uses=6, inviter_id=42)])
    risultato = await tracker.find_used_invite(guild_v2)

    assert risultato == ("abc123", 42)


@pytest.mark.asyncio
async def test_find_used_invite_nessun_cambiamento_restituisce_none():
    tracker = InviteTracker()
    guild = _FakeGuild(100, [_FakeInvite("abc123", uses=5, inviter_id=42)])
    await tracker.refresh_guild(guild)

    # Rilettura identica: nessun invito usato (es. join da vanity URL).
    risultato = await tracker.find_used_invite(guild)

    assert risultato is None


@pytest.mark.asyncio
async def test_find_used_invite_aggiorna_la_cache_per_il_prossimo_join():
    tracker = InviteTracker()
    guild_v1 = _FakeGuild(100, [_FakeInvite("abc123", uses=5, inviter_id=42)])
    await tracker.refresh_guild(guild_v1)

    guild_v2 = _FakeGuild(100, [_FakeInvite("abc123", uses=6, inviter_id=42)])
    await tracker.find_used_invite(guild_v2)

    # Un secondo join con lo stesso stato (uses invariato rispetto
    # all'ultimo find) non deve rilevare nessun uso, perché la cache
    # è stata aggiornata dopo il primo find.
    risultato = await tracker.find_used_invite(guild_v2)
    assert risultato is None


@pytest.mark.asyncio
async def test_server_diversi_non_si_influenzano():
    tracker = InviteTracker()
    await tracker.refresh_guild(_FakeGuild(100, [_FakeInvite("a", 1, 1)]))
    await tracker.refresh_guild(_FakeGuild(200, [_FakeInvite("b", 1, 2)]))

    assert tracker._cache.get(100) == {"a": 1}
    assert tracker._cache.get(200) == {"b": 1}


class TestResolveJoinInvite:
    """
    SPEC.md §8.8 (PROGRESS.md Fase 70): resolve_join_invite() esiste
    apposta perché find_used_invite() MUTA la propria cache ad ogni
    chiamata — chiamarlo due volte per lo stesso join (da due moduli
    diversi, es. Spam Trap e il Logging Avanzato) farebbe sì che la
    seconda chiamata veda il diff già "consumato" dalla prima.
    """

    @pytest.mark.asyncio
    async def test_una_singola_chiamata_risolve_normalmente(self):
        tracker = InviteTracker()
        await tracker.refresh_guild(_FakeGuild(100, [_FakeInvite("abc", 5, 42)]))
        guild_dopo_join = _FakeGuild(100, [_FakeInvite("abc", 6, 42)])

        risultato = await tracker.resolve_join_invite(guild_dopo_join, member_id=999)

        assert risultato == ("abc", 42)

    @pytest.mark.asyncio
    async def test_due_chiamate_sequenziali_per_lo_stesso_join_danno_la_stessa_risposta(self):
        # Il bug che questo metodo evita: find_used_invite() diretto
        # darebbe (None) alla seconda chiamata, perché la prima ha
        # già aggiornato l'istantanea.
        tracker = InviteTracker()
        await tracker.refresh_guild(_FakeGuild(100, [_FakeInvite("abc", 5, 42)]))
        guild_dopo_join = _FakeGuild(100, [_FakeInvite("abc", 6, 42)])

        prima_chiamata = await tracker.resolve_join_invite(guild_dopo_join, member_id=999)
        seconda_chiamata = await tracker.resolve_join_invite(guild_dopo_join, member_id=999)

        assert prima_chiamata == ("abc", 42)
        assert seconda_chiamata == ("abc", 42)

    @pytest.mark.asyncio
    async def test_chiamate_concorrenti_per_lo_stesso_join_non_si_pestano_i_piedi(self):
        tracker = InviteTracker()
        await tracker.refresh_guild(_FakeGuild(100, [_FakeInvite("abc", 5, 42)]))
        guild_dopo_join = _FakeGuild(100, [_FakeInvite("abc", 6, 42)])

        risultati = await asyncio.gather(
            tracker.resolve_join_invite(guild_dopo_join, member_id=999),
            tracker.resolve_join_invite(guild_dopo_join, member_id=999),
            tracker.resolve_join_invite(guild_dopo_join, member_id=999),
        )

        assert risultati == [("abc", 42), ("abc", 42), ("abc", 42)]

    @pytest.mark.asyncio
    async def test_membri_diversi_sullo_stesso_server_sono_indipendenti(self):
        tracker = InviteTracker()
        await tracker.refresh_guild(_FakeGuild(100, [_FakeInvite("abc", 5, 42)]))
        guild_dopo_join = _FakeGuild(100, [_FakeInvite("abc", 6, 42)])

        risultato_membro_1 = await tracker.resolve_join_invite(guild_dopo_join, member_id=1)
        # Un secondo membro con lo stesso stato di invito (nessun
        # nuovo uso reale) non deve "riciclare" la risposta del primo.
        risultato_membro_2 = await tracker.resolve_join_invite(guild_dopo_join, member_id=2)

        assert risultato_membro_1 == ("abc", 42)
        assert risultato_membro_2 is None

    @pytest.mark.asyncio
    async def test_nessun_invito_determinabile_restituisce_none_e_resta_cache(self):
        tracker = InviteTracker()
        guild = _FakeGuild(100, [_FakeInvite("abc", 5, 42)])
        await tracker.refresh_guild(guild)

        risultato = await tracker.resolve_join_invite(guild, member_id=999)
        assert risultato is None
        # Anche un None risolto resta in cache (non ri-diffato al
        # prossimo giro per la stessa coppia).
        assert (100, 999) in tracker._join_results

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


# ====================================================================
# M 3.17 (LC-6): ingressi insieme — attribuzione giusta o "sconosciuto"
# ====================================================================
class _ServerVivo:
    """
    Server finto con inviti che cambiano mentre il bot li legge:
    `invites()` impiega un attimo (come una chiamata vera) e risponde
    con i contatori di quel momento.
    """

    def __init__(self, guild_id: int, usi: dict[str, int]) -> None:
        self.id = guild_id
        self.usi = dict(usi)
        self.letture = 0

    def entra_con(self, codice: str | None) -> None:
        """Un membro entra; None = ingresso senza invito tracciabile (vanity URL)."""
        if codice is not None:
            self.usi[codice] = self.usi.get(codice, 0) + 1

    async def invites(self) -> list[_FakeInvite]:
        self.letture += 1
        await asyncio.sleep(0.01)
        return [_FakeInvite(codice, usi, inviter_id=42) for codice, usi in self.usi.items()]


class TestIngressiInsieme:
    @pytest.mark.asyncio
    async def test_ingresso_senza_invito_non_ruba_l_invito_di_chi_entra_insieme(self):
        # A entra dal vanity URL (nessun contatore sale), B con l'invito
        # "yyy", nello stesso istante. Prima A risultava entrato con "yyy".
        tracker = InviteTracker()
        server = _ServerVivo(100, {"xxx": 0, "yyy": 0})
        await tracker.refresh_guild(server)
        server.entra_con(None)
        server.entra_con("yyy")

        di_a, di_b = await asyncio.gather(
            tracker.resolve_join_invite(server, member_id=1),
            tracker.resolve_join_invite(server, member_id=2),
        )

        assert di_a is None, "A non ha usato nessun invito: deve restare sconosciuto"
        assert di_b in (None, ("yyy", 42))

    @pytest.mark.asyncio
    async def test_due_ingressi_insieme_con_inviti_diversi(self):
        tracker = InviteTracker()
        server = _ServerVivo(100, {"xxx": 0, "yyy": 0})
        await tracker.refresh_guild(server)
        server.entra_con("xxx")
        server.entra_con("yyy")

        di_a, di_b = await asyncio.gather(
            tracker.resolve_join_invite(server, member_id=1),
            tracker.resolve_join_invite(server, member_id=2),
        )

        assert di_a in (None, ("xxx", 42))
        assert di_b in (None, ("yyy", 42))

    @pytest.mark.asyncio
    async def test_raid_con_lo_stesso_invito_viene_attribuito_a_tutti(self):
        tracker = InviteTracker()
        server = _ServerVivo(100, {"raid": 3, "altro": 0})
        await tracker.refresh_guild(server)
        for _ in range(4):
            server.entra_con("raid")

        risultati = await asyncio.gather(
            *(tracker.resolve_join_invite(server, member_id=numero) for numero in range(1, 5))
        )

        assert risultati == [("raid", 42)] * 4

    @pytest.mark.asyncio
    async def test_raid_con_ingressi_uno_dopo_l_altro_ma_gia_contati(self):
        # Discord ha già contato tutti e tre gli usi quando il bot
        # guarda per il primo: gli altri due non vedono più differenze.
        tracker = InviteTracker()
        server = _ServerVivo(100, {"raid": 0})
        await tracker.refresh_guild(server)
        for _ in range(3):
            server.entra_con("raid")

        risultati = [
            await tracker.resolve_join_invite(server, member_id=numero) for numero in (1, 2, 3)
        ]

        assert risultati == [("raid", 42)] * 3

    @pytest.mark.asyncio
    async def test_usi_gia_attribuiti_non_restano_validi_a_lungo(self):
        from core.invite_tracker import DURATA_USI_IN_SOSPESO

        adesso = [1000.0]
        tracker = InviteTracker(orologio=lambda: adesso[0])
        server = _ServerVivo(100, {"raid": 0})
        await tracker.refresh_guild(server)
        for _ in range(3):
            server.entra_con("raid")
        assert await tracker.resolve_join_invite(server, member_id=1) == ("raid", 42)

        # Più tardi entra qualcuno dal vanity URL: non è un uso di "raid".
        adesso[0] += DURATA_USI_IN_SOSPESO + 1
        assert await tracker.resolve_join_invite(server, member_id=2) is None

    @pytest.mark.asyncio
    async def test_stesso_ingresso_chiesto_da_due_moduli_non_conta_come_due_persone(self):
        tracker = InviteTracker()
        server = _ServerVivo(100, {"xxx": 0})
        await tracker.refresh_guild(server)
        server.entra_con("xxx")

        risultati = await asyncio.gather(
            tracker.resolve_join_invite(server, member_id=1),
            tracker.resolve_join_invite(server, member_id=1),
        )

        assert risultati == [("xxx", 42), ("xxx", 42)]
        assert server.letture == 2  # refresh iniziale + una sola lettura per l'ingresso

    @pytest.mark.asyncio
    async def test_niente_resta_in_memoria_dopo_gli_ingressi(self):
        tracker = InviteTracker()
        server = _ServerVivo(100, {"xxx": 0})
        await tracker.refresh_guild(server)
        server.entra_con("xxx")

        await asyncio.gather(
            tracker.resolve_join_invite(server, member_id=1),
            tracker.resolve_join_invite(server, member_id=2),
        )

        assert tracker._guild_locks == {}
        assert tracker._in_corso == {}

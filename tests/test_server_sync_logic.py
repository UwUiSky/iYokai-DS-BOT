"""
tests/test_server_sync_logic.py
===============================
NF-39 (#110): ban e ruoli tenuti uguali tra due server dello stesso owner.
Logica pura, repository sul database vero e listener con server finti
(niente eco: un ban copiato non torna indietro).
Funzioni coperte: SPEC §11.16, NF-39
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import cogs.utility.backup as backup_module
from cogs.utility.backup import BackupCog
from core import server_sync_logic as sync
from core.database import Database
from core.repositories.backup_sincronia_repo import BackupSincroniaRepository
from core.repositories.backup_struttura_repo import BackupStrutturaRepository
from tests.support.discord_fakes import fake_role

A, B, C = 930001, 930002, 930003


def test_logica_pura():
    assert sync.coppia(5, 3) == (3, 5)
    assert sync.stesso_proprietario(1, 1, 1) and not sync.stesso_proprietario(1, 1, 2)
    assert sync.differenza_ruoli({"a", "b"}, {"b", "c"}) == ({"c"}, {"a"})
    bot = fake_role(9, "bot", position=10)
    ruoli = [fake_role(1, "Vip", position=2), fake_role(2, "Vip2", position=3, managed=True),
             fake_role(3, "Capo", position=20)]
    assert [r.name for r in sync.ruoli_applicabili({"Vip", "Vip2", "Capo"}, ruoli, bot)] == ["Vip"]
    assert len(sync.motivo("S", "x" * 600)) == 512


@pytest.fixture
async def repos(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    rs = BackupSincroniaRepository(pool_provider=lambda: database.pool)
    rr = BackupStrutturaRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(backup_module, "backup_sincronia_repo", rs)
    monkeypatch.setattr(backup_module, "backup_struttura_repo", rr)
    yield rs
    await database.pool.execute(
        "DELETE FROM backup_sincronie WHERE guild_a = ANY($1::bigint[]) OR guild_b = ANY($1::bigint[])",
        [A, B, C, *range(940000, 940010)],
    )
    await database.pool.execute("DELETE FROM backup_registro WHERE guild_id = ANY($1::bigint[])", [A, B, C])
    await database.close()


async def test_repository_coppia_unica_e_tetto(repos):
    assert await repos.attiva(B, A, True, False, 1)
    assert await repos.attiva(A, B, True, True, 1)  # stessa coppia: aggiornata
    assert len(await repos.sincronie_di(A)) == 1
    s = (await repos.sincronie_di(B))[0]
    assert (s.altro, s.ban, s.ruoli) == (A, True, True)
    for i in range(4):
        assert await repos.attiva(A, 940000 + i, True, True, 1)
    assert not await repos.attiva(A, 940009, True, True, 1)  # A ne ha già 5
    assert await repos.disattiva(B, A)
    assert not await repos.disattiva(B, A)


class _Server:
    def __init__(self, gid, owner=1):
        self.id, self.name, self.owner_id = gid, f"S{gid}", owner
        self.bannati: list = []
        self.sbannati: list = []
        self.roles = [fake_role(gid * 10 + 1, "Vip", position=2)]
        self.me = SimpleNamespace(top_role=fake_role(gid * 10 + 9, "bot", position=50))
        self.membri = {}

    async def ban(self, user, **kw):
        self.bannati.append(user.id)

    async def unban(self, user, **kw):
        self.sbannati.append(user.id)

    def get_member(self, uid):
        return self.membri.get(uid)


class _Bot:
    def __init__(self, *server):
        self.server = {s.id: s for s in server}

    def get_guild(self, gid):
        return self.server.get(gid)


def _interazione(guild, user_id=1):
    risposte = []

    async def send_message(testo=None, **kw):
        risposte.append(testo)

    return SimpleNamespace(
        guild=guild, user=SimpleNamespace(id=user_id),
        response=SimpleNamespace(send_message=send_message), risposte=risposte,
    )


async def test_solo_l_owner_di_entrambi_attiva(repos):
    a, b = _Server(A), _Server(B, owner=2)
    cog = BackupCog(_Bot(a, b))
    i = _interazione(a)
    await cog.sincronia.callback(cog, i, SimpleNamespace(value="attiva"), str(B), True, True)
    assert "entrambi" in i.risposte[0]
    assert await repos.sincronie_di(A) == []


async def test_ban_copiato_una_volta_senza_eco(repos):
    a, b = _Server(A), _Server(B)
    cog = BackupCog(_Bot(a, b))
    i = _interazione(a)
    await cog.sincronia.callback(cog, i, SimpleNamespace(value="attiva"), str(B), True, False)
    assert "Sincronia" in i.risposte[0]
    utente = SimpleNamespace(id=77)

    await cog.on_member_ban(a, utente)
    assert b.bannati == [77]
    await cog.on_member_ban(b, utente)  # l'evento del ban copiato
    assert a.bannati == []
    await cog.on_member_unban(b, utente)  # sban fatto a mano in B: arriva in A
    assert a.sbannati == [77]


async def test_ruoli_per_nome_e_niente_chiamate_se_gia_uguale(repos):
    a, b = _Server(A), _Server(B)
    cog = BackupCog(_Bot(a, b))
    i = _interazione(a)
    await cog.sincronia.callback(cog, i, SimpleNamespace(value="attiva"), str(B), False, True)
    chiamate = []

    class _Membro:
        roles: list = []

        async def add_roles(self, *r, **kw):
            chiamate.append(("dai", [x.name for x in r]))
            self.roles = [*self.roles, *r]

        async def remove_roles(self, *r, **kw):
            chiamate.append(("togli", [x.name for x in r]))

    b.membri[77] = _Membro()
    vip_a = a.roles[0]
    prima = SimpleNamespace(id=77, roles=[], guild=a)
    dopo = SimpleNamespace(id=77, roles=[vip_a], guild=a)
    await cog.on_member_update(prima, dopo)
    assert chiamate == [("dai", ["Vip"])]
    await cog.on_member_update(prima, dopo)  # già uguale: nessuna chiamata
    assert len(chiamate) == 1
    await cog.on_member_ban(a, SimpleNamespace(id=5))  # ban non sincronizzati qui
    assert b.bannati == []

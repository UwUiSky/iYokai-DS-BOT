"""
tests/test_ai_bozze.py
======================
Bozze di codice per le richieste approvate (§25.100): coda, tetto, AI ferma, pull request in bozza. Database vero.
"""

import pytest

from cogs.ai import bozze
from core import ai_bozza_logic as logica
from core.database import db
from core.github_bozze import ConfigGitHub, GitHubBozze, imposta_github_bozze, leggi_config
from core.repositories.ai_bozze_repo import ai_bozze_repo
from core.repositories.ai_repo import ai_repo
from tests.support.ai_finto import TrasportoFinto, fornitore, servizio_finto
from core.ai_servizio import imposta_servizio_ai


@pytest.fixture
def repo(clean_db, monkeypatch):
    for r in (ai_bozze_repo, ai_repo):
        monkeypatch.setattr(r, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(db, "_pool", clean_db, raising=False)
    yield ai_bozze_repo
    imposta_servizio_ai(None)
    imposta_github_bozze(None)


def _usa(fornitori, risposte):
    servizio, trasporto = servizio_finto(ai_repo, fornitori=fornitori, trasporto=TrasportoFinto(risposte=risposte))
    imposta_servizio_ai(servizio)
    return trasporto


async def _richiesta(pool, nome="saluta", stato="approved"):
    return await pool.fetchval(
        "INSERT INTO custom_command_requests (requester_guild_id, requester_guild_name, user_id, username_snapshot, "
        "command_name, description, example, status) VALUES (1, 'g', 2, 'u', $1, 'Saluta chi entra', 'es', $2) RETURNING id",
        nome, stato,
    )


def test_nomi_di_ramo_e_file_sicuri():
    r = logica.Richiesta(7, "Saluta ../Tutti!", "d", "e")
    assert logica.nome_ramo(r) == "bozze-ai/richiesta-7-saluta-tutti"
    assert logica.percorso_file(r).startswith("bozze_ai/") and ".." not in logica.percorso_file(r)
    assert logica.sotto_il_tetto(4) and not logica.sotto_il_tetto(5)


def test_github_spento_senza_token_o_repo():
    assert leggi_config({}) is None
    assert leggi_config({"GITHUB_BOZZE_TOKEN": "x", "GITHUB_BOZZE_REPO": "male"}) is None
    assert leggi_config({"GITHUB_BOZZE_TOKEN": "x", "GITHUB_BOZZE_REPO": "a/b"}).base == "main"


async def test_pull_request_in_bozza_con_trasporto_finto():
    chiamate = []

    async def trasporto(metodo, percorso, corpo):
        chiamate.append((metodo, percorso, corpo))
        return {"object": {"sha": "abc"}, "html_url": "https://github.com/a/b/pull/1"}

    gh = GitHubBozze(ConfigGitHub("t", "a/b"), trasporto)
    url = await gh.apri_bozza("ramo", "bozze_ai/x.md", "testo", "titolo", "corpo")
    assert url == "https://github.com/a/b/pull/1"
    assert chiamate[-1][2]["draft"] is True and [c[0] for c in chiamate] == ["GET", "POST", "PUT", "POST"]
    assert await GitHubBozze(None).apri_bozza("r", "p", "c", "t", "c") is None


async def test_giro_prepara_la_bozza_una_volta(repo, clean_db):
    rid = await _richiesta(clean_db, "salutatore")
    _usa([fornitore("alfa", tipi=("codice",), fascia="alta")], {"alfa": "## Analisi\nok"})
    imposta_github_bozze(GitHubBozze(None))
    cog = bozze.AiBozzeCog(bot=None)
    inviati = []

    async def avvisa(r, stato, url, bozza):
        inviati.append((r.id, stato))

    cog._avvisa_owner = avvisa
    assert await cog.giro() >= 1
    assert (rid, "pronta") in inviati
    assert await clean_db.fetchval("SELECT stato FROM ai_bozze WHERE request_id = $1", rid) == "pronta"
    n = len(inviati)
    await cog.giro()
    assert len(inviati) == n  # una sola bozza per richiesta


async def test_giro_con_ai_ferma_non_salva_nulla(repo, clean_db):
    rid = await _richiesta(clean_db, "senzaai")
    _usa([], None)
    cog = bozze.AiBozzeCog(bot=None)
    await cog.giro()
    assert await clean_db.fetchval("SELECT stato FROM ai_bozze WHERE request_id = $1", rid) is None


async def test_richieste_non_approvate_restano_fuori(repo, clean_db):
    rid = await _richiesta(clean_db, "inattesa", stato="pending")
    assert rid not in [r.id for r in await repo.da_preparare(50)]


async def test_nel_repository_niente_dati_personali_ne_segreti(repo, clean_db):
    """Il testo della persona e la bozza dell'AI finiscono su GitHub: menzioni, ID, e-mail e chiavi si tolgono."""
    rid = await clean_db.fetchval(
        "INSERT INTO custom_command_requests (requester_guild_id, requester_guild_name, user_id, username_snapshot, "
        "command_name, description, example, status) VALUES (1, 'g', 2, 'u', 'saluta', "
        "'Scrivete a mario.rossi@example.com, sono <@123456789012345678>, chiave ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123', 'es', 'approved') RETURNING id"
    )
    _usa([fornitore("alfa", tipi=("codice",), fascia="alta")], {"alfa": "## Codice\nTOKEN = 'ghp_ZYXWVUTSRQPONMLKJIHGFEDCBA9876'"})
    chiamate = []

    async def trasporto(metodo, percorso, corpo):
        chiamate.append(corpo)
        return {"object": {"sha": "abc"}, "html_url": "https://github.com/a/b/pull/1"}

    imposta_github_bozze(GitHubBozze(ConfigGitHub("t", "a/b"), trasporto))
    cog = bozze.AiBozzeCog(bot=None)

    async def avvisa(*_):
        return None

    cog._avvisa_owner = avvisa
    await cog.giro()
    inviato = repr(chiamate)
    import base64
    inviato += "".join(base64.b64decode(c["content"]).decode() for c in chiamate if c and "content" in c)
    assert chiamate, "la pull request doveva partire"
    for vietato in ("mario.rossi@example.com", "123456789012345678", "ghp_ABCDEFGHIJ", "ghp_ZYXWVUTSRQ"):
        assert vietato not in inviato, vietato
    assert rid

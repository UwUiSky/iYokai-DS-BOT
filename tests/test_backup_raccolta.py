"""
tests/test_backup_raccolta.py
=============================
Raccolta pubblica dei modelli di server (BKP-022/023, D127): struttura senza dati personali, revisione dell'owner,
elenco solo degli approvati, voto unico per persona, ripristino dei soli elementi mancanti, ruoli pericolosi solo con
la conferma del proprietario.
Funzioni coperte: BKP-022, BKP-023
"""

from __future__ import annotations

import json

import pytest

from core import backup_raccolta_logic as rac
from core import backup_struttura_logic as st
from core.repositories.backup_raccolta_repo import BackupRaccoltaRepository
from tests.support.discord_fakes import fake_role
from tests.test_backup_struttura import _Canale, _Cat, _Guild

PERICOLOSO = 8  # administrator


def _grezzo():
    return {
        "versione": 1, "nome": "Mio server", "everyone": 1024 | PERICOLOSO, "id": 5, "owner_id": 7,
        "ruoli": [
            {"nome": "Staff @everyone", "colore": 5, "hoist": True, "mentionable": False, "permessi": PERICOLOSO | 1024,
             "posizione": 2, "id": 99, "membri": [1, 2]},
            {"nome": "Membro", "colore": 0, "permessi": 1024, "posizione": 1},
        ],
        "categorie": [{"nome": "Info", "posizione": 0, "overwrite": [{"membro": 42, "allow": 1024, "deny": 0}]}],
        "canali": [
            {"nome": "regole", "tipo": "testo", "categoria": "Info", "posizione": 1, "topic": "scrivi a <@123> su https://x.it",
             "overwrite": [{"ruolo": "Membro", "allow": 1024 | PERICOLOSO, "deny": 0}, {"membro": 9, "allow": 1, "deny": 0}]},
        ],
        "ban": [{"user_id": 1, "motivo": "x"}], "membri": [{"user_id": 1}], "messaggi": {"regole": [{"contenuto": "ciao"}]},
        "emoji": [{"nome": "e", "url": "https://cdn.discordapp.com/x.png"}],
    }


def test_la_struttura_proposta_non_ha_dati_personali():
    pulita, errori = rac.prepara_struttura(_grezzo())
    assert errori == [] and pulita is not None
    assert set(pulita) == {"versione", "everyone", "ruoli", "categorie", "canali"}
    testo = str(pulita)
    for vietato in ("owner_id", "'id'", "membri", "ban", "messaggi", "emoji", "membro", "<@", "http", "42", "'Mio server'"):
        assert vietato not in testo, vietato
    assert pulita["everyone"] & st.PERMESSI_PERICOLOSI == 0
    assert pulita["ruoli"][0]["nome"] == "Staff"  # @everyone tolto dal nome
    assert pulita["canali"][0]["overwrite"] == [{"ruolo": "Membro", "allow": 1024, "deny": 0}]
    assert pulita["canali"][0]["topic"] == "scrivi a su"
    assert st.valida_struttura(pulita) == []


def test_tetti_e_nomi_doppi_o_vuoti():
    dati = _grezzo()
    dati["ruoli"] = [{"nome": f"r{i}", "permessi": 0} for i in range(rac.MAX_RUOLI_RACCOLTA + 1)]
    assert rac.prepara_struttura(dati)[0] is None
    dati = _grezzo()
    dati["ruoli"].append({"nome": "membro", "permessi": 0})
    assert any("doppio" in e for e in rac.prepara_struttura(dati)[1])
    dati = _grezzo()
    dati["canali"][0]["nome"] = "​  "
    assert rac.prepara_struttura(dati)[0] is None
    assert rac.prepara_struttura({"versione": 1, "tipo": "chat"})[0] is None
    assert rac.prepara_struttura({"versione": 1})[0] is None  # vuoto


def test_ruoli_pericolosi_sono_indicati():
    pulita, _ = rac.prepara_struttura(_grezzo())
    assert rac.ruoli_pericolosi(pulita) == ["Staff"]
    assert rac.permessi_pericolosi_di(pulita["ruoli"][0]) == ["administrator"]


def test_mancanti_conta_solo_cio_che_non_c_e():
    cat = _Cat(10, "Info")
    g = _Guild(ruoli=[fake_role(5, "Membro", position=1)], categorie=[cat], canali=[_Canale(11, "regole", category=cat)])
    pulita, _ = rac.prepara_struttura(_grezzo())
    m = rac.mancanti(g, pulita)
    assert (m.ruoli, m.categorie, m.canali) == (["Staff"], [], [])
    assert m.totale() == 1


async def test_ripristino_aggiunge_solo_cio_che_manca_e_non_tocca_il_resto():
    esistente = fake_role(5, "Membro", position=1, permissions=__import__("discord").Permissions(0))
    cat = _Cat(10, "Info")
    g = _Guild(ruoli=[esistente], categorie=[cat], canali=[_Canale(11, "regole", category=cat)])
    pulita, _ = rac.prepara_struttura(_grezzo())
    pulita["canali"].append({"nome": "nuovo", "tipo": "testo", "categoria": "Info", "posizione": 2, "overwrite": []})
    r = await st.Caricatore(g, pulita, {"ruoli", "canali"}, solo_mancanti=True, pericolosi_ok=True).esegui()
    assert ("ruolo", "Staff") in g.chiamate and ("ruolo", "Membro") not in g.chiamate
    assert ("testo", "nuovo", "Info") in g.chiamate and ("categoria", "Info") not in g.chiamate
    assert not any(c[0] == "server" for c in g.chiamate)  # nessuna modifica a @everyone né altro
    assert esistente.permissions.value == 0  # il ruolo che c'era non cambia
    assert r.creati == 2 and r.riusati == 3


async def test_ruolo_pericoloso_senza_conferma_nasce_senza_permessi():
    pulita, _ = rac.prepara_struttura(_grezzo())
    g = _Guild()
    await st.Caricatore(g, pulita, {"ruoli"}, pericolosi_ok=False).esegui()
    creato = next(r for r in g.roles if r.name == "Staff")
    assert creato.permissions.value & st.PERMESSI_PERICOLOSI == 0
    assert creato.permissions.value & 1024  # i permessi normali restano
    g2 = _Guild()
    await st.Caricatore(g2, pulita, {"ruoli"}, pericolosi_ok=True).esegui()  # conferma del proprietario
    assert next(r for r in g2.roles if r.name == "Staff").permissions.value & PERICOLOSO


# ---------------------------------------------------------------- database
@pytest.fixture
def repo(clean_db):
    return BackupRaccoltaRepository(pool_provider=lambda: clean_db)


async def _proposta(repo, guild=1, nome="Mio modello"):
    pulita, _ = rac.prepara_struttura(_grezzo())
    return await repo.proponi(guild, 7, nome, "desc", "it", pulita)


async def test_modello_non_approvato_e_invisibile(repo):
    mid = await _proposta(repo)
    assert await repo.elenco_pubblico() == []
    assert await repo.leggi_pubblico(mid) is None
    assert await repo.vota(mid, 5) == "assente"  # non si vota ciò che non si vede
    assert [m.id for m in await repo.da_rivedere()] == [mid]
    assert await repo.decidi(mid, False, 1)
    assert await repo.elenco_pubblico() == [] and await repo.leggi_pubblico(mid) is None
    assert await repo.decidi(mid, True, 1)
    assert [m.id for m in await repo.elenco_pubblico()] == [mid]
    assert await repo.decidi(mid, False, 1)  # l'owner può anche toglierlo
    assert await repo.elenco_pubblico() == []


async def test_voto_doppio_conta_una_volta(repo):
    mid = await _proposta(repo)
    await repo.decidi(mid, True, 1)
    assert [await repo.vota(mid, 5), await repo.vota(mid, 5), await repo.vota(mid, 6)] == ["nuovo", "gia", "nuovo"]
    (m,) = await repo.elenco_pubblico()
    assert m.voti == 2 and (m.ruoli, m.categorie, m.canali) == (2, 1, 1)


async def test_ordine_per_voti_ricerca_lingua_e_modifica(repo):
    a, b = await _proposta(repo, nome="Alfa gioco"), await _proposta(repo, 2, "Beta studio")
    for i in (a, b):
        await repo.decidi(i, True, 1)
    await repo.vota(b, 5)
    assert [m.id for m in await repo.elenco_pubblico()] == [b, a]
    assert [m.id for m in await repo.elenco_pubblico(ricerca="gioco")] == [a]
    assert await repo.elenco_pubblico(lingua="en-US") == []
    pulita, _ = rac.prepara_struttura(_grezzo())
    assert await repo.modifica(a, "Alfa nuovo", "altro", pulita)
    assert (await repo.leggi_pubblico(a))[0].nome == "Alfa nuovo"


async def test_tetto_proposte_in_revisione_per_server(repo):
    ids = [await _proposta(repo, 9, f"Modello {i}") for i in range(rac.MAX_IN_REVISIONE_PER_SERVER + 1)]
    assert ids[:-1] and all(ids[:-1]) and ids[-1] is None
    assert len(await repo.del_server(9)) == rac.MAX_IN_REVISIONE_PER_SERVER


# ---------------------------------------------------------------- pannello
from tests.test_web_panel_server import ADMIN, _client, _csrf, _entra, ambiente  # noqa: E402,F401


@pytest.fixture
def web(ambiente, clean_db, monkeypatch):  # noqa: F811
    from core import panel_bridge

    ambiente.owner = [ADMIN]
    monkeypatch.setattr(panel_bridge, "e_proprietario", lambda u: u is not None and u in ambiente.owner)
    return ambiente


async def test_pannello_elenco_pubblico_solo_approvati_e_senza_login(web, clean_db):
    repo = BackupRaccoltaRepository(pool_provider=lambda: clean_db)
    visto, nascosto = await _proposta(repo, nome="Visibile"), await _proposta(repo, 2, "Nascosto")
    await repo.decidi(visto, True, 1)
    client = await _client(web.app)
    try:
        testo = await (await client.get("/modelli")).text()
        assert "Visibile" in testo and "Nascosto" not in testo
        assert "administrator" not in testo and "Staff" not in testo  # mai la struttura
        assert (await client.get("/proprietario/modelli", allow_redirects=False)).status == 302
    finally:
        await client.close()


async def test_pannello_revisione_solo_owner_e_modifica_validata(web, clean_db, monkeypatch):
    repo = BackupRaccoltaRepository(pool_provider=lambda: clean_db)
    mid = await _proposta(repo, nome="Da rivedere")
    client = await _client(web.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, f"/proprietario/modelli/{mid}")
        r = await client.post(f"/proprietario/modelli/{mid}/decidi", data={"csrf": csrf, "scelta": "approva"}, allow_redirects=False)
        assert r.status == 302 and (await repo.leggi_pubblico(mid)) is not None
        r = await client.post(f"/proprietario/modelli/{mid}/modifica", data={
            "csrf": csrf, "nome": "Nome nuovo", "descrizione": "d", "struttura": '{"versione": 1, "ruoli": []}'})
        assert r.status == 400 and (await repo.leggi_pubblico(mid))[0].nome == "Da rivedere"  # struttura vuota: rifiutata
        buona = json.dumps(_grezzo())
        r = await client.post(f"/proprietario/modelli/{mid}/modifica", data={
            "csrf": csrf, "nome": "Nome nuovo", "descrizione": "d", "struttura": buona}, allow_redirects=False)
        assert r.status == 302 and (await repo.leggi_pubblico(mid))[0].nome == "Nome nuovo"
        r = await client.post(f"/proprietario/modelli/{mid}/decidi", data={"csrf": csrf, "scelta": "rifiuta"}, allow_redirects=False)
        assert await repo.leggi_pubblico(mid) is None
        web.owner.clear()  # non più l'owner
        assert (await client.get(f"/proprietario/modelli/{mid}")).status == 403
        r = await client.post(f"/proprietario/modelli/{mid}/decidi", data={"csrf": csrf, "scelta": "approva"})
        assert r.status == 403 and await repo.leggi_pubblico(mid) is None
    finally:
        await client.close()

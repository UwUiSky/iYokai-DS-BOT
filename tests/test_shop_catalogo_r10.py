"""
tests/test_shop_catalogo_r10.py
===============================
ECO-065 (ordine), ECO-066 (categorie), ECO-067 (oggetti «a elenco»),
ECO-068 (testo di risposta) e ECO-063 (ruolo che scade) dello shop.
Archivio su PostgreSQL vero.
Funzioni coperte: SPEC §15.4 (catalogo #125)
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest

import cogs.leveling.leveling as modulo
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.shop_repo import EsitoAcquisto, ShopRepository
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role
from tests.support.moduli import attiva_livelli

GUILD = 100


@pytest.fixture
def repo(clean_db):
    return ShopRepository(pool_provider=lambda: clean_db)


@pytest.fixture
def monete(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


# ---------------------------------------------------------------- ordine e categorie
@pytest.mark.asyncio
async def test_senza_ordine_ne_categorie_resta_l_ordine_per_prezzo(repo):
    await repo.add_item(GUILD, name="Caro", price=50)
    await repo.add_item(GUILD, name="Economico", price=5)
    nomi = [o.name for o in await repo.list_items(GUILD)]
    assert nomi == ["Economico", "Caro"]


@pytest.mark.asyncio
async def test_la_posizione_viene_prima_del_prezzo(repo):
    await repo.add_item(GUILD, name="Economico", price=5, sort_order=2)
    await repo.add_item(GUILD, name="Caro", price=50, sort_order=1)
    assert [o.name for o in await repo.list_items(GUILD)] == ["Caro", "Economico"]


@pytest.mark.asyncio
async def test_le_categorie_raggruppano_e_si_puo_filtrare(repo):
    await repo.add_item(GUILD, name="Spada", price=10, category="Armi")
    await repo.add_item(GUILD, name="Adesivo", price=1)
    await repo.add_item(GUILD, name="Elmo", price=30, category="Armature")
    await repo.add_item(GUILD, name="Arco", price=20, category="Armi")
    ordine = [(o.category, o.name) for o in await repo.list_items(GUILD)]
    assert ordine == [(None, "Adesivo"), ("Armature", "Elmo"), ("Armi", "Spada"), ("Armi", "Arco")]
    armi = await repo.list_items(GUILD, categoria="armi")  # senza badare alle maiuscole
    assert [o.name for o in armi] == ["Spada", "Arco"]


@pytest.mark.asyncio
async def test_update_item_cambia_e_toglie_ordine_categoria_risposta(repo):
    item_id = await repo.add_item(GUILD, name="X", price=10)
    o = await repo.update_item(item_id, GUILD, sort_order=3, category=" Vari ", reply_text="Grazie!")
    assert (o.sort_order, o.category, o.reply_text) == (3, "Vari", "Grazie!")
    o = await repo.update_item(item_id, GUILD, category=None, reply_text=None)
    assert (o.category, o.reply_text) == (None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "campi",
    [
        {"sort_order": -1}, {"sort_order": 10_000}, {"category": "x" * 31},
        {"reply_text": "x" * 501}, {"role_duration_hours": 0}, {"role_duration_hours": 24 * 366},
    ],
)
async def test_valori_fuori_dai_limiti_sono_rifiutati(repo, campi):
    item_id = await repo.add_item(GUILD, name="X", price=10)
    with pytest.raises(ValueError):
        await repo.update_item(item_id, GUILD, **campi)
    with pytest.raises(ValueError):
        await repo.add_item(GUILD, name="Y", price=10, **campi)


# ---------------------------------------------------------------- oggetti a elenco
@pytest.mark.asyncio
async def test_ogni_acquisto_consegna_una_riga_diversa(repo, monete):
    item_id = await repo.add_item(GUILD, name="Chiave", price=10)
    assert await repo.add_lines(item_id, GUILD, ["AAA", " ", "BBB", "CCC"]) == 3
    await monete.add_coins(GUILD, 1, 100)
    oggetto = await repo.get_item(item_id, GUILD)
    assert (oggetto.list_item, oggetto.lines_left) == (True, 3)

    prime = await repo.buy_item(GUILD, 1, oggetto)
    seconda = await repo.buy_item(GUILD, 1, oggetto)
    assert (prime.riga, seconda.riga) == ("AAA", "BBB")
    assert (await repo.get_item(item_id, GUILD)).lines_left == 1


@pytest.mark.asyncio
async def test_senza_righe_libere_e_esaurito_e_non_addebita(repo, monete):
    item_id = await repo.add_item(GUILD, name="Chiave", price=10)
    await repo.add_lines(item_id, GUILD, ["AAA"])
    await monete.add_coins(GUILD, 1, 100)
    oggetto = await repo.get_item(item_id, GUILD)
    assert (await repo.buy_item(GUILD, 1, oggetto)).esito == EsitoAcquisto.RIUSCITO
    assert (await repo.buy_item(GUILD, 1, oggetto)).esito == EsitoAcquisto.ESAURITO
    assert (await monete.get_totals(GUILD, 1)).coins_total == 90


@pytest.mark.asyncio
async def test_senza_saldo_la_riga_resta_libera(repo, monete):
    item_id = await repo.add_item(GUILD, name="Chiave", price=10)
    await repo.add_lines(item_id, GUILD, ["AAA"])
    oggetto = await repo.get_item(item_id, GUILD)
    assert (await repo.buy_item(GUILD, 1, oggetto)).esito == EsitoAcquisto.SALDO_INSUFFICIENTE
    assert (await repo.get_item(item_id, GUILD)).lines_left == 1


@pytest.mark.asyncio
async def test_il_rimborso_rimette_la_riga_in_vendita(repo, monete):
    item_id = await repo.add_item(GUILD, name="Chiave", price=10)
    await repo.add_lines(item_id, GUILD, ["AAA"])
    await monete.add_coins(GUILD, 1, 100)
    acquisto = await repo.buy_item(GUILD, 1, await repo.get_item(item_id, GUILD))
    assert await repo.refund_purchase(acquisto.purchase_id, GUILD, 1, 10) is True
    assert (await repo.get_item(item_id, GUILD)).lines_left == 1


@pytest.mark.asyncio
async def test_due_acquisti_insieme_non_prendono_la_stessa_riga(repo, monete, clean_db):
    item_id = await repo.add_item(GUILD, name="Chiave", price=10)
    await repo.add_lines(item_id, GUILD, ["AAA", "BBB"])
    await monete.add_coins(GUILD, 1, 100)
    await monete.add_coins(GUILD, 2, 100)
    oggetto = await repo.get_item(item_id, GUILD)
    await apri_connessioni(clean_db)
    esiti = await asyncio.gather(repo.buy_item(GUILD, 1, oggetto), repo.buy_item(GUILD, 2, oggetto))
    assert sorted(e.riga for e in esiti) == ["AAA", "BBB"]


@pytest.mark.asyncio
async def test_limiti_delle_righe(repo):
    item_id = await repo.add_item(GUILD, name="Chiave", price=10)
    with pytest.raises(ValueError):
        await repo.add_lines(item_id, GUILD, ["x" * 201])
    with pytest.raises(ValueError):
        await repo.add_lines(item_id, GUILD, [f"r{i}" for i in range(1001)])
    assert await repo.add_lines(item_id + 99, GUILD, ["a"]) is None
    assert await repo.add_lines(item_id, GUILD + 1, ["a"]) is None


@pytest.mark.asyncio
async def test_togliere_l_oggetto_toglie_le_righe(repo, clean_db):
    item_id = await repo.add_item(GUILD, name="Chiave", price=10)
    await repo.add_lines(item_id, GUILD, ["AAA"])
    assert await repo.remove_item(item_id, GUILD) is True
    assert await clean_db.fetchval("SELECT count(*) FROM shop_item_lines") == 0


# ---------------------------------------------------------------- ruolo a tempo
@pytest.mark.asyncio
async def test_il_ruolo_comprato_ha_una_scadenza_e_poi_si_puo_ricomprare(repo, monete, clean_db):
    item_id = await repo.add_item(GUILD, name="Vip", price=10, role_id=555, role_duration_hours=2)
    await monete.add_coins(GUILD, 1, 100)
    oggetto = await repo.get_item(item_id, GUILD)
    acquisto = await repo.buy_item(GUILD, 1, oggetto)
    assert acquisto.ruolo_scade_il is not None
    assert (await repo.buy_item(GUILD, 1, oggetto)).esito == EsitoAcquisto.GIA_ACQUISTATO
    assert await repo.list_expired_roles() == []

    await clean_db.execute("UPDATE shop_purchases SET role_expires_at = now() - interval '1 minute'")
    scaduti = await repo.list_expired_roles()
    assert [(s["user_id"], s["role_id"]) for s in scaduti] == [(1, 555)]

    await repo.close_role_purchase(scaduti[0]["id"])
    assert await repo.list_expired_roles() == []
    assert (await repo.buy_item(GUILD, 1, oggetto)).esito == EsitoAcquisto.RIUSCITO


@pytest.mark.asyncio
async def test_senza_durata_il_ruolo_non_scade(repo, monete):
    item_id = await repo.add_item(GUILD, name="Vip", price=10, role_id=555)
    await monete.add_coins(GUILD, 1, 100)
    acquisto = await repo.buy_item(GUILD, 1, await repo.get_item(item_id, GUILD))
    assert acquisto.ruolo_scade_il is None


@pytest.mark.asyncio
async def test_i_tentativi_falliti_si_contano(repo, monete):
    item_id = await repo.add_item(GUILD, name="Vip", price=10, role_id=555, role_duration_hours=1)
    await monete.add_coins(GUILD, 1, 100)
    acquisto = await repo.buy_item(GUILD, 1, await repo.get_item(item_id, GUILD))
    assert await repo.note_expiry_failure(acquisto.purchase_id) == 1
    assert await repo.note_expiry_failure(acquisto.purchase_id) == 2


# ---------------------------------------------------------------- comandi
@pytest.fixture
async def scena(monkeypatch, clean_db):
    from core.command_groups import costruisci_gruppi, registra_comandi_del_cog

    await apri_connessioni(clean_db)
    await attiva_livelli(monkeypatch, clean_db, GUILD)
    negozio = ShopRepository(pool_provider=lambda: clean_db)
    monete = LevelingRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "shop_repo", negozio)
    monkeypatch.setattr(modulo, "leveling_repo", monete)
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    comandi = {
        c.qualified_name: c
        for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None)
    }
    return SimpleNamespace(cog=cog, comandi=comandi, negozio=negozio, monete=monete)


def _interazione(user_id=1, ruolo=None):
    bot = fake_member(1000, "Yokai Bot", bot=True)
    bot.top_role = fake_role(1001, "Yokai Bot", position=50)
    server = fake_guild(GUILD, me=bot)
    if ruolo is not None:
        server.get_role.side_effect = lambda rid: ruolo if rid == ruolo.id else None
    return fake_interaction(guild=server, user=fake_member(user_id))


def _testi(interazione):
    chiamate = interazione.response.send_message.call_args_list + interazione.followup.send.call_args_list
    return " | ".join(str(c.args[0] if c.args else c.kwargs) for c in chiamate)


def _allegato(testo: str, size: int | None = None):
    dati = testo.encode()
    a = create_autospec(discord.Attachment, instance=True)
    a.size = len(dati) if size is None else size
    a.read = AsyncMock(return_value=dati)
    return a


@pytest.mark.asyncio
async def test_shop_add_con_tutti_i_nuovi_campi_e_un_file_di_righe(scena):
    interazione = _interazione()
    await scena.comandi["economia shop-add"].callback(
        scena.cog, interazione, name="Chiave", price=5, role=None, description=None,
        scorte=None, ruolo_richiesto=None, posizione=3, categoria="Giochi",
        risposta="Grazie {utente}!", durata_ruolo_ore=None,
        righe=_allegato("AAA\n\nBBB\n"),
    )
    o = (await scena.negozio.list_items(GUILD))[0]
    assert (o.sort_order, o.category, o.reply_text, o.list_item, o.lines_left) == (
        3, "Giochi", "Grazie {utente}!", True, 2,
    )
    assert "Righe da consegnare: 2" in _testi(interazione)


@pytest.mark.asyncio
async def test_shop_add_rifiuta_file_troppo_grande_e_durata_senza_ruolo(scena):
    grande = _interazione()
    await scena.comandi["economia shop-add"].callback(
        scena.cog, grande, name="Chiave", price=5, righe=_allegato("A", size=70_000),
    )
    assert "troppo grande" in _testi(grande)

    senza_ruolo = _interazione()
    await scena.comandi["economia shop-add"].callback(
        scena.cog, senza_ruolo, name="Vip", price=5, durata_ruolo_ore=2,
    )
    assert "dà un ruolo" in _testi(senza_ruolo)
    assert await scena.negozio.list_items(GUILD) == []


@pytest.mark.asyncio
async def test_shop_edit_cambia_e_toglie_categoria_e_risposta(scena):
    item_id = await scena.negozio.add_item(GUILD, name="X", price=10, category="A", reply_text="ciao")
    interazione = _interazione()
    await scena.comandi["economia shop-edit"].callback(
        scena.cog, interazione, item_id=item_id, posizione=4, categoria="B", senza_risposta=True,
    )
    o = await scena.negozio.get_item(item_id, GUILD)
    assert (o.sort_order, o.category, o.reply_text) == (4, "B", None)

    interazione = _interazione()
    await scena.comandi["economia shop-edit"].callback(
        scena.cog, interazione, item_id=item_id, senza_categoria=True,
        righe=_allegato("uno\ndue"),
    )
    o = await scena.negozio.get_item(item_id, GUILD)
    assert (o.category, o.list_item, o.lines_left) == (None, True, 2)


@pytest.mark.asyncio
async def test_shop_edit_durata_su_oggetto_senza_ruolo_non_scrive(scena):
    item_id = await scena.negozio.add_item(GUILD, name="X", price=10)
    interazione = _interazione()
    await scena.comandi["economia shop-edit"].callback(
        scena.cog, interazione, item_id=item_id, durata_ruolo_ore=5, posizione=9,
    )
    assert "dà un ruolo" in _testi(interazione)
    assert (await scena.negozio.get_item(item_id, GUILD)).sort_order == 0


@pytest.mark.asyncio
async def test_la_lista_raggruppa_per_categoria_e_filtra(scena):
    await scena.negozio.add_item(GUILD, name="Spada", price=10, category="Armi")
    await scena.negozio.add_item(GUILD, name="Adesivo", price=1)
    interazione = _interazione()
    await scena.comandi["level shop list"].callback(scena.cog, interazione)
    testo = interazione.response.send_message.await_args.kwargs["embed"].description
    assert testo.index("Senza categoria") < testo.index("Adesivo") < testo.index("Armi") < testo.index("Spada")

    interazione = _interazione()
    await scena.comandi["level shop list"].callback(scena.cog, interazione, categoria="armi")
    testo = interazione.response.send_message.await_args.kwargs["embed"].description
    assert "Spada" in testo and "Adesivo" not in testo

    interazione = _interazione()
    await scena.comandi["level shop list"].callback(scena.cog, interazione, categoria="boh")
    assert "Nessun oggetto" in _testi(interazione)


@pytest.mark.asyncio
async def test_il_codice_lo_vede_solo_chi_compra_e_il_testo_di_risposta_si_compone(scena):
    item_id = await scena.negozio.add_item(
        GUILD, name="Chiave", price=10, reply_text="Ciao {utente}, hai preso {oggetto}."
    )
    await scena.negozio.add_lines(item_id, GUILD, ["XYZ-123"])
    await scena.monete.add_coins(GUILD, 1, 100)
    interazione = _interazione()
    await scena.comandi["level shop buy"].callback(scena.cog, interazione, item_id=item_id)
    chiamata = interazione.response.send_message.await_args
    assert chiamata.kwargs["ephemeral"] is True
    assert "XYZ-123" in chiamata.args[0]
    assert "Ciao utente, hai preso Chiave." in chiamata.args[0]

    altro = _interazione(user_id=2)
    await scena.monete.add_coins(GUILD, 2, 100)
    await scena.comandi["level shop buy"].callback(scena.cog, altro, item_id=item_id)
    assert "esaurito" in _testi(altro).lower()


@pytest.mark.asyncio
async def test_la_lista_mostra_righe_rimaste_e_durata(scena):
    item_id = await scena.negozio.add_item(GUILD, name="Chiave", price=10)
    await scena.negozio.add_lines(item_id, GUILD, ["a", "b"])
    await scena.negozio.add_item(GUILD, name="Vip", price=20, role_id=55, role_duration_hours=48)
    interazione = _interazione()
    await scena.comandi["level shop list"].callback(scena.cog, interazione)
    testo = interazione.response.send_message.await_args.kwargs["embed"].description
    assert "rimasti 2" in testo and "dura 48 h" in testo


@pytest.mark.asyncio
async def test_acquisto_di_un_ruolo_a_tempo_dice_la_scadenza_e_il_giro_lo_toglie(scena, clean_db):
    ruolo = fake_role(55, "Vip", position=1)
    item_id = await scena.negozio.add_item(GUILD, name="Vip", price=10, role_id=55, role_duration_hours=2)
    await scena.monete.add_coins(GUILD, 1, 100)
    interazione = _interazione(ruolo=ruolo)
    await scena.comandi["level shop buy"].callback(scena.cog, interazione, item_id=item_id)
    assert "Il ruolo dura fino a" in _testi(interazione)

    membro = fake_member(1, roles=[ruolo])
    server = fake_guild(GUILD)
    server.get_role.side_effect = lambda rid: ruolo if rid == 55 else None
    server.get_member.side_effect = lambda uid: membro if uid == 1 else None
    scena.cog.bot = SimpleNamespace(get_guild=lambda gid: server if gid == GUILD else None, guilds=[server])

    await scena.cog.togli_ruoli_shop_scaduti()
    membro.remove_roles.assert_not_awaited()  # non ancora scaduto

    await clean_db.execute("UPDATE shop_purchases SET role_expires_at = now() - interval '1 minute'")
    await scena.cog.togli_ruoli_shop_scaduti()
    membro.remove_roles.assert_awaited_once()
    assert await scena.negozio.list_expired_roles() == []
    assert await clean_db.fetchval("SELECT role_id FROM shop_purchases") is None


@pytest.mark.asyncio
async def test_se_discord_rifiuta_si_riprova_poi_si_lascia_perdere(scena, clean_db):
    ruolo = fake_role(55, "Vip", position=1)
    item_id = await scena.negozio.add_item(GUILD, name="Vip", price=10, role_id=55, role_duration_hours=1)
    await scena.monete.add_coins(GUILD, 1, 100)
    await scena.negozio.buy_item(GUILD, 1, await scena.negozio.get_item(item_id, GUILD))
    await clean_db.execute("UPDATE shop_purchases SET role_expires_at = now() - interval '1 minute'")

    membro = fake_member(1, roles=[ruolo])
    risposta = SimpleNamespace(status=500, reason="boh")
    membro.remove_roles.side_effect = discord.HTTPException(risposta, "errore")
    server = fake_guild(GUILD)
    server.get_role.side_effect = lambda rid: ruolo
    server.get_member.side_effect = lambda uid: membro
    scena.cog.bot = SimpleNamespace(get_guild=lambda gid: server, guilds=[server])

    for _ in range(4):
        await scena.cog.togli_ruoli_shop_scaduti()
        assert len(await scena.negozio.list_expired_roles()) == 1  # ancora da togliere
    await scena.cog.togli_ruoli_shop_scaduti()  # quinto tentativo: si arrende
    assert await scena.negozio.list_expired_roles() == []


@pytest.mark.asyncio
async def test_membro_uscito_o_ruolo_gia_tolto_chiude_senza_errori(scena, clean_db):
    item_id = await scena.negozio.add_item(GUILD, name="Vip", price=10, role_id=55, role_duration_hours=1)
    await scena.monete.add_coins(GUILD, 1, 100)
    await scena.negozio.buy_item(GUILD, 1, await scena.negozio.get_item(item_id, GUILD))
    await clean_db.execute("UPDATE shop_purchases SET role_expires_at = now() - interval '1 minute'")
    server = fake_guild(GUILD)  # nessun membro, nessun ruolo
    scena.cog.bot = SimpleNamespace(get_guild=lambda gid: server, guilds=[server])
    await scena.cog.togli_ruoli_shop_scaduti()
    assert await scena.negozio.list_expired_roles() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "testo",
    ["\n  \n\n", "\n".join(f"c{i}" for i in range(1001)), "x" * 201],
    ids=["vuoto", "troppe", "lunga"],
)
async def test_shop_add_con_righe_non_valide_non_mette_in_vendita_niente(scena, testo):
    """Prima l'oggetto restava in vendita senza righe: chi lo comprava pagava e non riceveva nulla."""
    interazione = _interazione()
    await scena.comandi["economia shop-add"].callback(
        scena.cog, interazione, name="Chiave", price=5, righe=_allegato(testo),
    )
    assert "Aggiunto" not in _testi(interazione)
    assert await scena.negozio.list_items(GUILD) == []


@pytest.mark.asyncio
async def test_il_codice_arriva_anche_in_privato(scena):
    """ECO-067: la riga si consegna in DM; il messaggio effimero sparisce."""
    item_id = await scena.negozio.add_item(GUILD, name="Chiave", price=10)
    await scena.negozio.add_lines(item_id, GUILD, ["XYZ-123"])
    await scena.monete.add_coins(GUILD, 1, 100)
    interazione = _interazione()
    await scena.comandi["level shop buy"].callback(scena.cog, interazione, item_id=item_id)
    interazione.user.send.assert_awaited_once()
    assert "XYZ-123" in str(interazione.user.send.await_args)

    # DM chiusi: l'acquisto resta valido e il codice si vede comunque nella risposta.
    await scena.negozio.add_lines(item_id, GUILD, ["ABC-9"])
    chiuso = _interazione()
    chiuso.user.send.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason="no"), "dm")
    await scena.comandi["level shop buy"].callback(scena.cog, chiuso, item_id=item_id)
    assert "ABC-9" in _testi(chiuso)


@pytest.mark.asyncio
async def test_gli_acquisti_di_server_senza_il_bot_non_bloccano_il_giro(scena, clean_db):
    """Il giro legge 100 scadenze alla volta: quelle di un server lasciato restavano in testa per sempre."""
    for utente in range(1, 102):
        await clean_db.execute(
            "INSERT INTO shop_purchases (guild_id, user_id, item_id, role_id, role_expires_at) "
            "VALUES (999, $1, 1, 55, now() - interval '1 hour')",
            utente,
        )
    item_id = await scena.negozio.add_item(GUILD, name="Vip", price=10, role_id=55, role_duration_hours=1)
    await scena.monete.add_coins(GUILD, 1, 100)
    await scena.negozio.buy_item(GUILD, 1, await scena.negozio.get_item(item_id, GUILD))
    await clean_db.execute(
        "UPDATE shop_purchases SET role_expires_at = now() - interval '1 minute' WHERE guild_id = $1", GUILD
    )
    ruolo = fake_role(55, "Vip", position=1)
    membro = fake_member(1, roles=[ruolo])
    server = fake_guild(GUILD)
    server.get_role.side_effect = lambda rid: ruolo
    server.get_member.side_effect = lambda uid: membro
    scena.cog.bot = SimpleNamespace(
        get_guild=lambda gid: server if gid == GUILD else None, guilds=[server]
    )
    await scena.cog.togli_ruoli_shop_scaduti()
    membro.remove_roles.assert_awaited_once()

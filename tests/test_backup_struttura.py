"""
tests/test_backup_struttura.py
==============================
La struttura come dati: lettura, controllo del file, esportazione, caricamento
per nome con tetti, stato e annullo; permessi a tre livelli; copie datate,
caricamenti e registro sul database vero.
Funzioni coperte: M 12.17, BKP-009, BKP-010, BKP-014, BKP-015, BKP-018,
BKP-019, BKP-032…037
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import discord
import pytest

from core import backup_struttura_logic as st
from core.backup_permessi_logic import (
    AZIONE_CARICA,
    AZIONE_CREA,
    LIVELLO_ADMIN_TUTTO,
    LIVELLO_SOLO_OWNER,
    puo,
)
from core.database import Database
from core.repositories.backup_struttura_repo import BackupStrutturaRepository
from tests.support.discord_fakes import fake_role


# ---------------------------------------------------------------- finti
class _Risposta:
    status = 403
    reason = "Forbidden"


class _Cat:
    def __init__(self, cid, name, position=0, overwrites=None):
        self.id, self.name, self.position = cid, name, position
        self.type = discord.ChannelType.category
        self.overwrites = overwrites or {}
        self.channels = []
        self.category = None


class _Canale:
    def __init__(self, cid, name, tipo=discord.ChannelType.text, category=None, overwrites=None):
        self.id, self.name, self.type, self.category = cid, name, tipo, category
        self.position = cid
        self.topic, self.nsfw, self.slowmode_delay = "argomento", False, 0
        self.bitrate, self.user_limit = 96000, 0
        self.overwrites = overwrites or {}


class _Guild:
    """Server finto: crea e registra ogni chiamata, una alla volta."""

    def __init__(self, ruoli=(), categorie=(), canali=(), bitrate_limit=96000.0):
        self.id = 1
        self.name = "Server"
        self.default_role = fake_role(0, "@everyone", position=0)
        self.me = SimpleNamespace(
            guild_permissions=discord.Permissions.all(), top_role=fake_role(99, "bot", position=50)
        )
        self.roles = [self.default_role, *ruoli]
        self.categories = list(categorie)
        self.channels = [*categorie, *canali]
        self.bitrate_limit = bitrate_limit
        self.emojis, self.stickers = [], []
        self.emoji_limit = self.sticker_limit = 50
        self.chiamate: list[tuple] = []
        self._id = 1000
        self.membri = {}

    def get_member(self, uid):
        return self.membri.get(uid)

    def _nuovo_id(self):
        self._id += 1
        return self._id

    async def create_role(self, **kw):
        self.chiamate.append(("ruolo", kw["name"]))
        r = fake_role(self._nuovo_id(), kw["name"], position=1, permissions=kw["permissions"])
        self.roles.append(r)
        return r

    async def edit_role_positions(self, ordine, **kw):
        self.chiamate.append(("posizioni", len(ordine)))

    async def create_category(self, **kw):
        self.chiamate.append(("categoria", kw["name"]))
        c = _Cat(self._nuovo_id(), kw["name"])
        self.categories.append(c)
        return c

    async def create_text_channel(self, **kw):
        self.chiamate.append(("testo", kw["name"], kw.get("category").name if kw.get("category") else None))
        return _Canale(self._nuovo_id(), kw["name"])

    async def create_voice_channel(self, **kw):
        self.chiamate.append(("vocale", kw["name"], kw["bitrate"]))
        return _Canale(self._nuovo_id(), kw["name"], discord.ChannelType.voice)

    async def edit(self, **kw):
        self.chiamate.append(("server", tuple(sorted(kw))))

    async def ban(self, utente, **kw):
        self.chiamate.append(("ban", utente.id, kw["reason"]))


async def _nessuna_pausa(_s):
    return None


# ---------------------------------------------------------------- lettura
def test_lettura_salta_canali_offuscati_ruoli_gestiti_e_mappa_i_permessi_per_nome():
    staff = fake_role(5, "Staff", position=3)
    staff.colour, staff.hoist, staff.mentionable = discord.Colour(0xFF0000), True, False
    gestito = fake_role(6, "BotMusica", position=2, managed=True)
    cat = _Cat(10, "Info", overwrites={staff: discord.PermissionOverwrite(view_channel=True)})
    g = _Guild(ruoli=[staff, gestito], categorie=[cat],
               canali=[_Canale(11, "regole", category=cat), _Canale(12, st.NOME_CANALE_OFFUSCATO)])
    g.verification_level = discord.VerificationLevel.low
    g.default_notifications = discord.NotificationLevel.only_mentions
    g.explicit_content_filter = discord.ContentFilter.all_members
    g.afk_timeout, g.afk_channel, g.system_channel = 300, None, None

    dati = st.leggi_struttura(g)

    assert [r["nome"] for r in dati["ruoli"]] == ["Staff"]
    assert [c["nome"] for c in dati["canali"]] == ["regole"]
    assert dati["canali"][0]["categoria"] == "Info"
    assert dati["categorie"][0]["overwrite"][0]["ruolo"] == "Staff"
    assert st.valida_struttura(dati) == []
    assert st.leggi_json(st.in_json(dati))[0] == dati


# ---------------------------------------------------------------- controllo
def test_file_non_valido_non_tocca_niente():
    assert st.leggi_json(b"non json")[0] is None
    assert "versione" in st.valida_struttura({"versione": 9})[0]
    troppi = {"versione": 1, "ruoli": [{"nome": "r", "permessi": 0}] * 251}
    assert "al massimo 250" in st.valida_struttura(troppi)[0]
    tipo = {"versione": 1, "canali": [{"nome": "x", "tipo": "segreto"}]}
    assert "tipo" in st.valida_struttura(tipo)[0]
    grande = b" " * (st.MAX_FILE_BYTE + 1)
    assert st.leggi_json(grande) == (None, ["il file supera 10 MiB"])


def test_esportazione_csv_e_modello_senza_dati_personali():
    contenuto, est = st.esporta("ban", "csv", [{"user_id": 7, "nome": "x", "motivo": "spam"}])
    assert est == "csv" and contenuto.decode().splitlines() == ["user_id,nome,motivo", "7,x,spam"]
    assert st.esporta("struttura", "csv", {"a": 1})[1] == "json"
    dati = {"versione": 1, "ban": [1], "membri": [2],
            "canali": [{"nome": "c", "overwrite": [{"membro": 5, "allow": 0, "deny": 0}, {"ruolo": "r", "allow": 0, "deny": 0}]}]}
    pulito = st.senza_dati_personali(dati)
    assert "ban" not in pulito and "membri" not in pulito
    assert pulito["canali"][0]["overwrite"] == [{"ruolo": "r", "allow": 0, "deny": 0}]


def test_solo_immagini_di_discord():
    assert st.url_immagine_ammesso("https://cdn.discordapp.com/emojis/1.png")
    assert not st.url_immagine_ammesso("http://cdn.discordapp.com/emojis/1.png")
    assert not st.url_immagine_ammesso("https://169.254.169.254/latest")


# ---------------------------------------------------------------- caricamento
async def test_caricamento_riusa_per_nome_e_adatta_il_bitrate():
    esistente = fake_role(5, "Staff", position=1)
    cat = _Cat(10, "Info")
    g = _Guild(ruoli=[esistente], categorie=[cat], canali=[_Canale(11, "regole", category=cat)], bitrate_limit=64000.0)
    dati = {
        "versione": 1,
        "ruoli": [{"nome": "Staff", "permessi": 0, "posizione": 1}, {"nome": "Nuovo", "permessi": 8, "posizione": 2}],
        "categorie": [{"nome": "Info", "posizione": 0}, {"nome": "Voce", "posizione": 1}],
        "canali": [
            {"nome": "regole", "tipo": "testo", "categoria": "Info"},
            {"nome": "chat", "tipo": "testo", "categoria": "Info"},
            {"nome": "stanza", "tipo": "vocale", "categoria": "Voce", "bitrate": 384000},
        ],
    }
    r = await st.Caricatore(g, dati, {"ruoli", "canali"}).esegui()

    assert ("ruolo", "Nuovo") in g.chiamate and ("ruolo", "Staff") not in g.chiamate
    assert ("categoria", "Voce") in g.chiamate and ("categoria", "Info") not in g.chiamate
    assert ("testo", "chat", "Info") in g.chiamate
    assert ("vocale", "stanza", 64000) in g.chiamate  # LIM-28
    assert r.creati == 4 and r.riusati == 3 and not r.annullato


async def test_tetto_di_50_canali_per_categoria():
    cat = _Cat(10, "Piena")
    cat.channels = [object()] * 49
    g = _Guild(categorie=[cat])
    dati = {"versione": 1, "canali": [{"nome": f"c{i}", "tipo": "testo", "categoria": "Piena"} for i in range(3)]}
    r = await st.Caricatore(g, dati, {"canali"}).esegui()
    assert r.creati == 1 and r.saltati == 2


async def test_annullo_ferma_tra_un_passo_e_l_altro_e_lo_stato_avanza():
    g = _Guild()
    passi = []

    async def avanza(passo, fatti, totale):
        passi.append((passo, fatti, totale))
        return fatti >= 2  # annullo chiesto dopo il secondo passo

    dati = {"versione": 1, "ruoli": [{"nome": f"r{i}", "permessi": 0, "posizione": i} for i in range(5)]}
    r = await st.Caricatore(g, dati, {"ruoli"}, avanza=avanza).esegui()
    assert r.annullato
    assert passi == [("ruoli", 1, 5), ("ruoli", 2, 5)]
    assert [c for c in g.chiamate if c[0] == "ruolo"] == [("ruolo", "r0")]


async def test_ban_ricaricati_con_motivo_tagliato_a_512():
    g = _Guild()
    dati = {"versione": 1, "ban": [{"user_id": 7, "motivo": "x" * 600}, {"user_id": 8, "motivo": ""}]}
    r = await st.Caricatore(g, dati, {"ban"}, pausa=_nessuna_pausa).esegui()
    assert r.creati == 2
    assert g.chiamate[0] == ("ban", 7, "x" * 512)
    assert g.chiamate[1][2] == st.MOTIVO


async def test_membri_ruoli_sopra_il_bot_non_si_danno():
    basso, alto = fake_role(5, "Basso", position=2), fake_role(6, "Alto", position=60)
    g = _Guild(ruoli=[basso, alto])
    dati_ricevuti = []

    class _Membro:
        nick = None
        roles = []
        top_role = fake_role(1, "x", position=1)

        async def add_roles(self, *ruoli, **kw):
            dati_ricevuti.append([r.name for r in ruoli])

        async def edit(self, **kw):
            dati_ricevuti.append(kw["nick"])

    g.membri[7] = _Membro()
    dati = {"versione": 1, "membri": [{"user_id": 7, "nick": "Neo", "ruoli": ["Basso", "Alto"]}, {"user_id": 8, "ruoli": []}]}
    r = await st.Caricatore(g, dati, {"membri"}, pausa=_nessuna_pausa).esegui()
    assert dati_ricevuti == [["Basso"], "Neo"]
    assert r.riusati == 1 and r.saltati == 1


def test_parti_presenti_e_passi():
    dati = {"versione": 1, "ruoli": [{}], "canali": [{}, {}], "categorie": [{}], "ban": []}
    assert st.parti_presenti(dati) == ["ruoli", "canali"]
    assert st.conta_passi(dati, {"ruoli", "canali"}) == 4


# ---------------------------------------------------------------- permessi
def test_tre_livelli_di_permesso():
    assert puo(None, AZIONE_CREA, e_owner=False, e_admin=True)
    assert not puo(None, AZIONE_CARICA, e_owner=False, e_admin=True)  # predefinito: solo l'owner carica
    assert puo(LIVELLO_ADMIN_TUTTO, AZIONE_CARICA, e_owner=False, e_admin=True)
    assert not puo(LIVELLO_SOLO_OWNER, AZIONE_CREA, e_owner=False, e_admin=True)
    assert puo(LIVELLO_SOLO_OWNER, AZIONE_CARICA, e_owner=True, e_admin=False)
    assert not puo(LIVELLO_ADMIN_TUTTO, AZIONE_CREA, e_owner=False, e_admin=False)


# ---------------------------------------------------------------- database
@pytest.fixture
async def repo():
    database = Database()
    await database.connect()
    await database.run_migrations()
    yield BackupStrutturaRepository(pool_provider=lambda: database.pool)
    for tabella in ("backup_strutture", "backup_caricamenti", "backup_registro"):
        await database.pool.execute(f"DELETE FROM {tabella} WHERE guild_id IN (910001, 910002)")
    await database.close()


async def test_al_massimo_10_copie_datate_e_modello_con_codice(repo):
    ids = [await repo.salva_struttura(910001, f"c{i}", 5, {"versione": 1, "i": i}) for i in range(10)]
    assert all(ids)
    assert await repo.salva_struttura(910001, "troppe", 5, {"versione": 1}) is None
    copie = await repo.lista_strutture(910001)
    assert len(copie) == 10 and copie[0].nome == "c9"  # la più recente in alto
    assert (await repo.leggi_struttura(910001, ids[3]))["i"] == 3
    assert await repo.leggi_struttura(910002, ids[3]) is None  # mai la copia di un altro server

    codice = await repo.pubblica_modello(910001, ids[0])
    assert codice and await repo.pubblica_modello(910001, ids[0]) == codice
    assert (await repo.leggi_modello(codice))[0] == "c0"
    assert await repo.ritira_modello(910001, ids[0])
    assert await repo.leggi_modello(codice) is None
    assert await repo.elimina_struttura(910001, ids[1])
    assert not await repo.elimina_struttura(910002, ids[2])


async def test_un_caricamento_alla_volta_con_stato_e_annullo(repo):
    primo = await repo.avvia_caricamento(910001, 5, "copia #1", 10)
    assert primo is not None
    assert await repo.avvia_caricamento(910001, 5, "copia #2", 10) is None
    assert not await repo.aggiorna_caricamento(primo, "ruoli", 3, 10)
    assert await repo.chiedi_annullo(910001)
    assert await repo.aggiorna_caricamento(primo, "ruoli", 4, 10)
    await repo.chiudi_caricamento(primo, "annullato")
    stato = await repo.ultimo_caricamento(910001)
    assert (stato.stato, stato.fatti, stato.passo) == ("annullato", 4, "ruoli")
    assert not await repo.chiedi_annullo(910001)
    assert await repo.avvia_caricamento(910001, 5, "copia #2", 1) is not None


async def test_caricamento_morto_non_blocca_il_prossimo(repo):
    primo = await repo.avvia_caricamento(910002, 5, "copia", 1)
    await repo._pool.execute(
        "UPDATE backup_caricamenti SET aggiornato_il = now() - interval '2 hours' WHERE id = $1", primo
    )
    assert await repo.avvia_caricamento(910002, 5, "copia", 1) is not None


async def test_registro(repo):
    await repo.registra(910001, 5, "salva", "x" * 300)
    righe = await repo.leggi_registro(910001)
    assert righe[0]["azione"] == "salva" and len(righe[0]["dettaglio"]) == 200
    json.dumps([str(r) for r in righe])


async def test_messaggi_ricaricati_solo_nei_canali_vuoti_con_lo_stesso_nome(monkeypatch):
    from core import backup_messages_logic as bm

    inviati = []

    class _Hook:
        async def send(self, **kw):
            inviati.append(kw["content"])
            return SimpleNamespace(id=1)

    class _Testo:
        def __init__(self, nome, pieno):
            self.name, self.pieno = nome, pieno

    async def vuota(canale):
        return not canale.pieno

    async def hook(_canale):
        return _Hook()

    monkeypatch.setattr(bm, "_destinazione_vuota", vuota)
    monkeypatch.setattr(bm, "webhook_chat", hook)
    g = _Guild()
    g.text_channels = [_Testo("generale", False), _Testo("pieno", True)]
    dati = {"versione": 1, "messaggi": {
        "generale": [{"autore": "A", "contenuto": "ciao"}],
        "pieno": [{"autore": "A", "contenuto": "no"}],
        "sparito": [{"autore": "A", "contenuto": "no"}],
    }}
    assert st.valida_struttura(dati) == [] and "messaggi" in st.parti_presenti(dati)
    assert "messaggi" not in st.senza_dati_personali(dati)
    r = await st.Caricatore(g, dati, {"messaggi"}).esegui()
    assert inviati == ["ciao"]
    assert (r.creati, r.saltati) == (1, 2)
    assert st.valida_struttura({"versione": 1, "messaggi": {"c": [{}] * 101}})


# ---------------------------------------------------------------- file da fuori
def test_file_con_tipi_sbagliati_si_rifiuta_prima_di_toccare_il_server():
    """Ogni campo letto dal Caricatore ha il tipo giusto: niente errori a metà caricamento."""
    casi = [
        {"emoji": [{"nome": 1, "url": "https://cdn.discordapp.com/e.png"}]},
        {"sticker": [{"nome": "s"}]},
        {"membri": [{"ruoli": "Admin"}]},
        {"membri": [{"user_id": 7, "ruoli": [1]}]},
        {"ban": [{"user_id": 7, "motivo": 5}]},
        {"ruoli": [{"nome": "r", "posizione": "alta"}]},
        {"canali": [{"nome": "c", "tipo": "vocale", "bitrate": "alto"}]},
        {"impostazioni": {"verification_level": "x"}},
        {"messaggi": {"chat": [{"contenuto": "ciao", "allegati": [{"url": 5}]}]}},
        {"messaggi": {"chat": [{"contenuto": "ciao", "autore": ["x"]}]}},
    ]
    for caso in casi:
        assert st.valida_struttura({"versione": 1, **caso}), caso


async def test_permessi_pericolosi_non_si_aggiungono_a_everyone_ne_ai_ruoli_esistenti():
    """Un modello o un file non fa admin tutto il server: @everyone e i ruoli già dati restano senza admin."""
    membri = fake_role(5, "Membri", position=1, permissions=discord.Permissions(send_messages=True))
    g = _Guild(ruoli=[membri])
    pericolosi = discord.Permissions(administrator=True, send_messages=True).value
    dati = {
        "versione": 1, "everyone": pericolosi,
        "ruoli": [{"nome": "Membri", "permessi": pericolosi}, {"nome": "Nuovo", "permessi": pericolosi}],
        "canali": [{"nome": "c", "tipo": "testo", "overwrite": [
            {"everyone": True, "allow": discord.Permissions(manage_webhooks=True, view_channel=True).value, "deny": 0}
        ]}],
    }
    kw_canale = {}

    async def crea_testo(**kw):
        kw_canale.update(kw)
        return _Canale(500, kw["name"])

    g.create_text_channel = crea_testo
    await st.Caricatore(g, dati, {"ruoli", "canali"}).esegui()

    everyone = g.default_role.edit.await_args.kwargs["permissions"]
    assert not everyone.administrator and everyone.send_messages
    assert all(not c.kwargs["permissions"].administrator for c in membri.edit.await_args_list)
    assert [r for r in g.roles if r.name == "Nuovo"][0].permissions.administrator  # nuovo e senza membri: resta
    ow = kw_canale["overwrites"][g.default_role]
    assert ow.manage_webhooks is None and ow.view_channel is True

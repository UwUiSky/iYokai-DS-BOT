"""
tests/test_ticket_opzioni_logic.py
==================================
Regole pure delle opzioni dei pannelli dei ticket (#120): orari, pausa, accesso,
lista nera, sospensione, nome del canale, testi, permessi dell'utente.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core import ticket_opzioni_logic as L

UTC = timezone.utc
# Lunedì 12/10/2026 alle 10:00 a Roma (08:00 UTC, ora legale).
LUNEDI_10 = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)


def test_orari_lettura_e_controllo():
    orari = L.leggi_orari("lun-ven 09:00-18:00; sab 10:00-12:30, 15:00-16:00")
    assert orari[0] == [(540, 1080)] and orari[4] == [(540, 1080)]
    assert orari[5] == [(600, 750), (900, 960)]
    assert 6 not in orari
    testo = "lun-ven 09:00-18:00"
    assert L.in_orario(testo, "Europe/Rome", LUNEDI_10)
    assert not L.in_orario(testo, "Europe/Rome", LUNEDI_10 + timedelta(hours=9))  # 19:00
    assert not L.in_orario(testo, "Europe/Rome", LUNEDI_10 + timedelta(days=6))  # domenica
    assert L.in_orario(None, "Europe/Rome", LUNEDI_10)


@pytest.mark.parametrize(
    "testo",
    ["", "lun", "xyz 09:00-10:00", "ven-lun 09:00-10:00", "lun 10:00-09:00", "lun 9-10", "lun 25:00-26:00"],
)
def test_orari_non_validi(testo):
    with pytest.raises(ValueError):
        L.leggi_orari(testo)


def test_fuso_sconosciuto():
    with pytest.raises(ValueError):
        L.fuso_valido("Marte/Base")


def test_pausa_e_azzeramento():
    ultima = LUNEDI_10 - timedelta(minutes=10)
    assert L.secondi_di_pausa(ultima, None, 3600, LUNEDI_10) == 3000
    assert L.secondi_di_pausa(ultima, LUNEDI_10 - timedelta(minutes=1), 3600, LUNEDI_10) == 0
    assert L.secondi_di_pausa(ultima, ultima - timedelta(days=1), 3600, LUNEDI_10) == 3000
    assert L.secondi_di_pausa(None, None, 3600, LUNEDI_10) == 0
    assert L.secondi_di_pausa(ultima, None, 0, LUNEDI_10) == 0


def test_regole_di_accesso_dall_alto():
    regole = [(1, False), (2, True), (99, False)]  # 99 = @everyone in fondo: lista bianca
    assert not L.accesso_consentito(regole, {1, 2, 99})
    assert L.accesso_consentito(regole, {2, 99})
    assert not L.accesso_consentito(regole, {99})
    assert L.accesso_consentito([], {99})


def _r(*ruoli, staff=False):
    return L.Richiedente(5, frozenset(ruoli), staff)


def test_decisione_ordine_dei_controlli():
    s = L.Situazione(in_lista_nera=True)
    assert not L.decidi_apertura(_r(), s, LUNEDI_10).permesso
    assert L.decidi_apertura(_r(staff=True), s, LUNEDI_10).permesso

    s = L.Situazione(sospesa_motivo="manutenzione", sospesa_fino=LUNEDI_10 + timedelta(hours=1))
    esito = L.decidi_apertura(_r(), s, LUNEDI_10)
    assert not esito.permesso and "manutenzione" in esito.messaggio and "<t:" in esito.messaggio
    s.opzioni = L.Opzioni(ruoli_esenti=(7,))
    assert L.decidi_apertura(_r(7), s, LUNEDI_10).permesso

    s = L.Situazione(opzioni=L.Opzioni(max_aperti=3), aperti_nel_pannello=3)
    assert not L.decidi_apertura(_r(), s, LUNEDI_10).permesso
    s.aperti_nel_pannello = 2
    assert L.decidi_apertura(_r(), s, LUNEDI_10).permesso

    s = L.Situazione(opzioni=L.Opzioni(pausa_secondi=600), ultima_apertura=LUNEDI_10 - timedelta(minutes=5))
    esito = L.decidi_apertura(_r(), s, LUNEDI_10)
    assert not esito.permesso and "5 minuti" in esito.messaggio

    s = L.Situazione(regole_accesso=[(3, False)])
    assert not L.decidi_apertura(_r(3), s, LUNEDI_10).permesso
    assert L.decidi_apertura(_r(3, staff=True), s, LUNEDI_10).permesso


def test_fuori_orario_blocca_o_apre_con_avviso():
    sera = LUNEDI_10 + timedelta(hours=10)
    o = L.Opzioni(orari="lun-ven 09:00-18:00", fuori_orario_testo="Siamo chiusi, torna domani.")
    esito = L.decidi_apertura(_r(), L.Situazione(opzioni=o), sera)
    assert not esito.permesso and esito.messaggio == "Siamo chiusi, torna domani."
    o = L.Opzioni(orari="lun-ven 09:00-18:00", fuori_orario_apri=True)
    esito = L.decidi_apertura(_r(), L.Situazione(opzioni=o), sera)
    assert esito.permesso and esito.fuori_orario
    o = L.Opzioni(orari="lun-ven 09:00-18:00", ruoli_esenti=(4,))
    assert L.decidi_apertura(_r(4), L.Situazione(opzioni=o), sera).permesso


def test_nome_del_canale():
    assert L.nome_canale(None, 7, "Mario") == "ticket-0007"
    assert L.nome_canale("supporto-{numero}-{utente}", 7, "Mario Rossi") == "supporto-0007-mario-rossi"
    assert L.nome_canale("{nickname}-{num}", 12, "mario", "Il Capo!") == "il-capo-12"
    assert len(L.nome_canale("{utente}" * 10, 1, "x" * 32)) <= 100
    assert L.nome_canale("!!!", 3, "a") == "ticket-0003"
    with pytest.raises(ValueError):
        L.controlla_modello_nome("ticket-{sconosciuto}")
    assert L.controlla_modello_nome(" t-{numero} ") == "t-{numero}"


def test_testi_controllati_al_salvataggio():
    assert L.controlla_testo("nessuno") is None
    assert L.controlla_testo("Ciao {utente}") == "Ciao {utente}"
    with pytest.raises(ValueError):
        L.controlla_testo("{server}" * 30)  # 30 × 100 caratteri
    assert L.riempi("{staff} ha preso il #{numero}", staff="@a", numero=3) == "@a ha preso il #0003"


def test_permessi_e_liste():
    assert L.leggi_permessi_negati("allegati, link") == ("allegati", "link")
    with pytest.raises(ValueError):
        L.leggi_permessi_negati("volare")
    p = L.permessi_utente(("allegati", "vocali"))
    assert p["attach_files"] is False and p["send_voice_messages"] is False and p["send_messages"] is True
    assert L.leggi_ids("<@&123456789012345678> 223456789012345678 <@&123456789012345678>") == (
        123456789012345678, 223456789012345678,
    )
    assert L.leggi_ids("nessuno") == ()
    with pytest.raises(ValueError):
        L.leggi_ids(" ".join(str(10**17 + i) for i in range(11)))


def test_categoria_con_posto():
    assert L.prima_con_posto([(1, 50), (2, 49)]) == 2
    assert L.prima_con_posto([(1, 50)]) is None


def test_link_del_messaggio():
    g, c, m = 123456789012345678, 223456789012345678, 323456789012345678
    assert L.leggi_link_messaggio(f"https://discord.com/channels/{g}/{c}/{m}") == (g, c, m)
    assert L.leggi_link_messaggio(f"https://ptb.discordapp.com/channels/{g}/{c}/{m}") == (g, c, m)
    assert L.leggi_link_messaggio("https://example.com/channels/1/2/3") is None
    assert L.leggi_link_messaggio(None) is None


def test_il_riassunto_sta_in_un_embed():
    lunghe = tuple(range(10**17, 10**17 + L.MAX_RUOLI_LISTA))
    o = L.Opzioni(ruoli_esenti=lunghe, ruoli_osservatori=lunghe, ruoli_durante=lunghe, ruoli_staff=lunghe,
                       ping_ruoli=lunghe, categorie_riserva=lunghe, orari="lun-ven 09:00-18:00")
    campi = L.riassunto(o)
    assert len(campi) <= 25 and all(len(v) <= 1024 and len(n) <= 256 for n, v in campi)
    assert sum(len(n) + len(v) for n, v in campi) < 6000

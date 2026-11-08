"""
tests/test_automod_account_rubato_logic.py
==========================================
Riconoscimento dell'account rubato (D67): immagini malevole, stesso messaggio in tre canali, finestra, tetti.
"""

from core import account_rubato_logic as lg

FIRMA = lg.firma_messaggio("Hai vinto un Nitro gratis, ritiralo qui http://x.example")


def invio(reg, canale, msg, ora, *, guild=1, user=9, firma=FIRMA, malevola=False):
    return reg.registra(user, guild, canale, msg, firma, ora, malevola=malevola)


def test_firma_ignora_maiuscole_e_spazi():
    assert lg.firma_messaggio("Ciao  A TUTTI  quanti siete") == lg.firma_messaggio("ciao a tutti quanti siete")


def test_firma_none_per_testo_breve_senza_allegati():
    assert lg.firma_messaggio("ok") is None
    assert lg.firma_messaggio("") is None
    assert lg.firma_messaggio("ok", [("a.png", 10)]) is not None


def test_firma_cambia_con_gli_allegati_e_con_gli_inoltri():
    base = lg.firma_messaggio("guarda qua sotto adesso")
    assert lg.firma_messaggio("guarda qua sotto adesso", [("a.png", 10)]) != base
    assert lg.firma_messaggio("", inoltrati=["messaggio inoltrato lungo abbastanza"]) is not None


def test_due_canali_uguali_non_bastano():
    reg = lg.RegistroInvii()
    assert invio(reg, 1, 1, 0) is None
    assert invio(reg, 2, 2, 1) is None


def test_tre_canali_uguali_segnalano():
    reg = lg.RegistroInvii()
    invio(reg, 1, 1, 0)
    invio(reg, 2, 2, 1)
    s = invio(reg, 3, 3, 2)
    assert (s.invii, s.canali, s.server, s.prima_volta, s.motivi) == (3, 3, 1, True, (lg.MOTIVO_UGUALI,))
    assert s.timeout_secondi == lg.TIMEOUT_UGUALI_S


def test_tre_canali_in_server_diversi_contano_i_server():
    reg = lg.RegistroInvii()
    invio(reg, 1, 1, 0, guild=10)
    invio(reg, 2, 2, 1, guild=20)
    s = invio(reg, 3, 3, 2, guild=30)
    assert s.server == 3 and s.guild_ids == (10, 20, 30)


def test_fuori_dalla_finestra_non_conta():
    reg = lg.RegistroInvii()
    invio(reg, 1, 1, 0)
    invio(reg, 2, 2, lg.FINESTRA_S + 5)
    assert invio(reg, 3, 3, lg.FINESTRA_S + 6) is None


def test_stesso_canale_tre_volte_non_segnala():
    reg = lg.RegistroInvii()
    for n in range(5):
        assert invio(reg, 1, n, n) is None


def test_messaggi_diversi_non_segnalano():
    reg = lg.RegistroInvii()
    for n in range(4):
        assert invio(reg, n, n, n, firma=lg.firma_messaggio(f"messaggio numero {n} diverso dagli altri")) is None


def test_persone_diverse_non_si_sommano():
    reg = lg.RegistroInvii()
    invio(reg, 1, 1, 0, user=1)
    invio(reg, 2, 2, 1, user=2)
    assert invio(reg, 3, 3, 2, user=3) is None


def test_immagine_malevola_segnala_subito_con_timeout_lungo():
    reg = lg.RegistroInvii()
    s = invio(reg, 1, 1, 0, malevola=True)
    assert s.malevole and s.invii == 1 and s.prima_volta
    assert s.timeout_secondi == lg.TIMEOUT_MALEVOLE_S


def test_dopo_la_prima_segnalazione_si_aggiorna_senza_essere_prima_volta():
    reg = lg.RegistroInvii()
    assert invio(reg, 1, 1, 0, malevola=True).prima_volta
    s = invio(reg, 2, 2, 5, malevola=True)
    assert (s.prima_volta, s.invii, s.canali) == (False, 2, 2)


def test_dopo_la_segnalazione_basta_un_altro_invio_uguale():
    reg = lg.RegistroInvii()
    invio(reg, 1, 1, 0)
    invio(reg, 2, 2, 1)
    invio(reg, 3, 3, 2)
    s = invio(reg, 4, 4, 3)
    assert s is not None and not s.prima_volta and s.invii == 4


def test_stesso_messaggio_visto_da_due_filtri_conta_una_volta():
    reg = lg.RegistroInvii()
    assert invio(reg, 1, 77, 0) is None
    s = invio(reg, 1, 77, 0, malevola=True)
    assert s.invii == 1 and s.malevole


def test_dopo_la_finestra_si_riparte_da_prima_volta():
    reg = lg.RegistroInvii()
    invio(reg, 1, 1, 0, malevola=True)
    assert invio(reg, 1, 2, lg.FINESTRA_S * 3, malevola=True).prima_volta


def test_memoria_con_tetto():
    reg = lg.RegistroInvii()
    for n in range(lg.MAX_INVII_PER_PERSONA + 40):
        invio(reg, n, n, 0, firma=lg.firma_messaggio(f"messaggio unico numero {n} lungo"))
    assert len(reg._persone.get(9).invii) == lg.MAX_INVII_PER_PERSONA


def test_la_sintesi_porta_i_messaggi_da_cancellare():
    reg = lg.RegistroInvii()
    invio(reg, 1, 11, 0, guild=10)
    invio(reg, 2, 22, 1, guild=20)
    s = invio(reg, 3, 33, 2, guild=30)
    assert set(s.messaggi) == {(10, 1, 11), (20, 2, 22), (30, 3, 33)}


def test_ogni_messaggio_si_passa_da_cancellare_una_sola_volta():
    """Ogni nuovo invio dopo la segnalazione porta solo sé stesso: niente cancellazioni ripetute (429 di Discord)."""
    reg = lg.RegistroInvii()
    invio(reg, 1, 11, 0)
    invio(reg, 2, 22, 1)
    assert len(invio(reg, 3, 33, 2).messaggi) == 3
    s = invio(reg, 4, 44, 3)
    assert s.messaggi == ((1, 4, 44),) and s.invii == 4

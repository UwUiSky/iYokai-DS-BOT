"""
tests/test_voci_solo_documenti_varie.py
=======================================
Voci del catalogo che c'erano ma senza la loro prova con il codice (giro r1doc).
Funzioni coperte: FUN-139, FUN-063
"""

from core.command_policy import MOTIVO_COMANDO_OFF, Politica, valuta


# FUN-139
def test_le_azioni_tra_utenti_si_spengono_con_la_politica_dei_comandi():
    spenta = Politica(comandi_off=frozenset({"gif azione"}))
    chiamata = dict(canali=[1], ruoli=[], user_id=5, esente=False)
    assert valuta(spenta, percorso="gif azione", **chiamata) == MOTIVO_COMANDO_OFF
    assert valuta(spenta, percorso="gif reazione", **chiamata) is None  # le reazioni restano
    # l'amministratore del bot non può chiudersi fuori: «admin-bot» resta sempre aperto
    assert valuta(Politica(comandi_off=frozenset({"admin-bot politica comando"})), percorso="admin-bot politica comando", **chiamata) is None

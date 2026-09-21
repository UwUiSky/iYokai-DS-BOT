"""
tests/test_command_search_logic.py
======================================
Test di core/command_search_logic.py — logica pura, con esempi presi
dai comandi reali del bot (non inventati), per verificare che
funzioni sui casi veri che /search dovrà gestire.
"""

from core.command_search_logic import score_command, search_commands

COMANDI_DI_ESEMPIO = [
    ("ban", "Banna permanentemente un membro."),
    ("kick", "Espelle un membro dal server."),
    ("poll", "Crea un sondaggio (fino a 5 opzioni)."),
    ("reminder set", "Imposta un promemoria."),
    ("serverstats", "Mostra le statistiche del server, con grafico di crescita."),
    ("mute-role", "Silenzia un membro con un ruolo dedicato (alternativa al timeout)."),
]


class TestScoreCommand:
    def test_query_vuota_ha_punteggio_zero(self):
        assert score_command("", "ban", "Banna un membro.") == 0.0

    def test_parola_esatta_nella_descrizione_alza_il_punteggio(self):
        punteggio = score_command("banna", "ban", "Banna permanentemente un membro.")
        assert punteggio > 0

    def test_query_completamente_estranea_ha_punteggio_basso(self):
        punteggio = score_command("meteo previsioni domani", "ban", "Banna un membro.")
        assert punteggio < 0.3

    def test_query_come_sottostringa_alza_ulteriormente_il_punteggio(self):
        con_sottostringa = score_command("crea un sondaggio", "poll", "Crea un sondaggio.")
        senza_sottostringa = score_command("crea qualcosa", "poll", "Crea un sondaggio.")
        assert con_sottostringa > senza_sottostringa

    def test_forma_verbale_diversa_della_stessa_radice_trova_corrispondenza(self):
        # "bannare" (infinito) vs "banna" (comando) - forme diverse
        # della stessa radice, l'italiano coniugato non trova un
        # match ESATTO per parola intera senza un aiuto qui.
        punteggio = score_command("bannare", "ban", "Banna un membro.")
        assert punteggio > 0

    def test_stopword_non_vengono_conteggiate_come_mancanti(self):
        # "voglio" e "qualcuno" sono rumore, non parole chiave -
        # una query che le contiene non deve avere un punteggio più
        # basso di una che dice solo la parola chiave vera.
        con_stopword = score_command("voglio bannare qualcuno", "ban", "Banna un membro.")
        solo_chiave = score_command("bannare", "ban", "Banna un membro.")
        assert con_stopword == solo_chiave


class TestSearchCommands:
    def test_trova_ban_da_query_in_linguaggio_naturale(self):
        risultati = search_commands("voglio bannare qualcuno", COMANDI_DI_ESEMPIO)
        assert len(risultati) > 0
        assert risultati[0][0] == "ban"

    def test_trova_poll_da_query_sondaggio(self):
        risultati = search_commands("crea un sondaggio per il server", COMANDI_DI_ESEMPIO)
        assert risultati[0][0] == "poll"

    def test_trova_mute_da_query_silenzia(self):
        risultati = search_commands("silenzia un membro", COMANDI_DI_ESEMPIO)
        assert risultati[0][0] == "mute-role"

    def test_query_senza_corrispondenza_restituisce_lista_vuota(self):
        risultati = search_commands("ricetta della carbonara perfetta", COMANDI_DI_ESEMPIO)
        assert risultati == []

    def test_rispetta_il_limite_di_risultati(self):
        risultati = search_commands("membro", COMANDI_DI_ESEMPIO, threshold=0.0, limit=2)
        assert len(risultati) <= 2

    def test_risultati_ordinati_per_punteggio_decrescente(self):
        risultati = search_commands("membro server", COMANDI_DI_ESEMPIO, threshold=0.0, limit=10)
        punteggi = [r[2] for r in risultati]
        assert punteggi == sorted(punteggi, reverse=True)

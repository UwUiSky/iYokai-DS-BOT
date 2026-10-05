"""
core/panel_bridge.py
====================
Riceve dal pannello l'avviso "configurazione cambiata" e aggiorna la
memoria del bot.
Funzioni coperte: SPEC §24 (NF-20)

STATO: scheletro. Il codice non è ancora scritto (issue #91).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #91, fase F10
# Funzione: NF-20, Pannello web (iYokai Panel).
#
# Cosa deve fare la funzione: Un sito dove l'admin entra con Discord,
#   sceglie il server e configura ogni modulo. Scrive le stesse
#   impostazioni dei comandi. Ha anche le pagine dell'owner (premium,
#   blacklist) e le pagine legali.
# Questo file: Riceve dal pannello l'avviso "configurazione cambiata" e
#   aggiorna la memoria del bot.
# Comandi previsti: Nessun comando. Vive in un repository separato e
#   privato (scelta dell'owner).
# File collegati: core/config_schema.py.
# Test da scrivere per primi: tests/test_panel_bridge.py,
#   tests/test_config_schema.py.
# Limiti da rispettare: Stessi controlli dei comandi: il pannello chiama
#   le stesse funzioni di validazione, mai il database a mano.
# Da chi prendere spunto: MEE6, Dyno, Carl-bot, ProBot, Wick.
# Dipende da: NF-01, NF-05, NF-06. Dominio con HTTPS. Privacy policy
#   (NF-04).
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------

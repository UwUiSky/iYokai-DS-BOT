"""
core/command_groups.py
======================
I 13 gruppi di primo livello, definiti una volta sola e usati da tutti i
cog.
Funzioni coperte: SPEC §20 (NF-05)

STATO: scheletro. Il codice non è ancora scritto (issue #76).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #76, fase F7
# Funzione: NF-05, Nuova struttura dei comandi.
#
# Cosa deve fare la funzione: Da 97 comandi di primo livello a 13
#   gruppi: /owner /admin /mod /modban /security /log /ticket /voice
#   /music /level /clan /fun /utility. Chi non può usare un comando non
#   lo vede. /owner esiste solo nel server dell'owner.
# Questo file: I 13 gruppi di primo livello, definiti una volta sola e
#   usati da tutti i cog.
# Comandi previsti: Tutti. Vedi la tabella "Albero dei comandi" più
#   sotto.
# Test da scrivere per primi: tests/test_command_groups.py.
# Limiti da rispettare: 100 comandi; 25 figli per gruppo; un solo
#   livello di sotto-gruppi; default_permissions solo sul primo livello
#   (LIM-57).
# Da chi prendere spunto: Standard di Discord (permessi predefiniti e
#   delega in Integrazioni).
# Dipende da: D2, D4. REVIEW.md §6.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------

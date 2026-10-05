"""
core/welcome_image.py
=====================
Disegna l'immagine di benvenuto.
Funzioni coperte: SPEC §22 (NF-11)

STATO: scheletro. Il codice non è ancora scritto (issue #82).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #82, fase F9
# Funzione: NF-11, Immagine di benvenuto.
#
# Cosa deve fare la funzione: Il benvenuto può avere un'immagine con
#   avatar, nome e numero del membro. Si parte con 3–4 modelli pronti e
#   uno sfondo caricabile.
# Questo file: Disegna l'immagine di benvenuto.
# Comandi previsti: /admin benvenuto immagine.
# File esistenti da toccare: cogs/utility/greetings.py,
#   core/repositories/greetings_repo.py.
# Test da scrivere per primi: tests/test_welcome_image.py.
# Migrazione: core/migrations/NNNN_greetings_immagine.sql. (prossimo
#   numero libero in core/migrations/).
# Limiti da rispettare: Regole di core/safe_image.py (16 megapixel, 2048
#   px); file sotto 10 MiB; lavoro Pillow fuori dal ciclo principale.
# Da chi prendere spunto: ProBot (sfondo sotto 3 MB, avatar tondo o
#   quadrato, testo con posizione e colore).
# Dipende da: Nessuna. L'editor completo arriva con il pannello web
#   (NF-20).
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------

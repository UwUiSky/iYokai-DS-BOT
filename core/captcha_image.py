"""
core/captcha_image.py
=====================
Genera l'immagine e il testo atteso.
Funzioni coperte: SPEC §22 (NF-18)

STATO: scheletro. Il codice non è ancora scritto (issue #89).
"""

# ----------------------------------------------------------------------
# NOTA PER CHI SCRIVE QUESTO FILE — issue #89, fase F9
# Funzione: NF-18, Captcha a immagine.
#
# Cosa deve fare la funzione: La verifica mostra un'immagine con lettere
#   storte da ricopiare, al posto della somma scritta.
# Questo file: Genera l'immagine e il testo atteso.
# Comandi previsti: /security verify setup (opzione captcha: immagine).
# File esistenti da toccare: cogs/security/verify.py,
#   core/verify_logic.py.
# Test da scrivere per primi: tests/test_captcha_image.py.
# Limiti da rispettare: Campo del modulo 45 caratteri di etichetta;
#   immagine piccola; tempo massimo e numero di tentativi.
# Da chi prendere spunto: Wick, Captcha.bot.
# Dipende da: Nessuna.
#
# Prima di iniziare: lista di controllo di
#   revisione/01-analisi/LIMITI.md (Parte 4); ogni impostazione passa da
#   un solo punto del codice, usato anche dal pannello web (decisione
#   D16); prima il test che fallisce, poi il codice.
# Dettaglio: revisione/02-piano/NUOVE_FUNZIONI.md e il catalogo in
#   revisione/01-analisi/catalogo/.
# ----------------------------------------------------------------------

#!/usr/bin/env bash
# installa_servizio.sh
# ====================
# Installa il servizio di sistema `iyokai-bot` (deploy/systemd/iyokai-bot.service) su Debian o Ubuntu,
# x86_64 o arm64. Va lanciato come amministratore dalla cartella del bot (di base /opt/iyokai).
# Uso: sudo scripts/installa_servizio.sh [--prova]
#   --prova: mostra cosa farebbe, senza cambiare niente.
# Nessun segreto qui: il bot legge le sue chiavi dal .env.

set -euo pipefail

PROVA=0
[[ "${1:-}" == "--prova" ]] && PROVA=1

CARTELLA=$(cd "$(dirname "$0")/.." && pwd)
UTENTE=iyokai
UNITA_ORIGINE="$CARTELLA/deploy/systemd/iyokai-bot.service"
UNITA_DESTINAZIONE=/etc/systemd/system/iyokai-bot.service

info() { printf '[servizio] %s\n' "$1"; }
errore() { printf '[servizio] ERRORE: %s\n' "$1" >&2; exit 1; }
esegui() { if (( PROVA )); then info "(prova) $*"; else "$@"; fi; }

# Sistema e architettura supportati
[[ -r /etc/os-release ]] || errore "non riconosco il sistema (manca /etc/os-release)."
# shellcheck disable=SC1091
. /etc/os-release
case "${ID:-}${ID_LIKE:-}" in
    *debian*|*ubuntu*) ;;
    *) errore "serve Debian o Ubuntu (trovato: ${PRETTY_NAME:-sconosciuto}). Su altri sistemi copia l'unità a mano." ;;
esac
case "$(uname -m)" in
    x86_64|aarch64|arm64) ;;
    *) errore "architettura non supportata: $(uname -m) (servono x86_64 o arm64)." ;;
esac
command -v systemctl >/dev/null || errore "systemd non c'è su questa macchina."
(( PROVA )) || [[ $EUID -eq 0 ]] || errore "lancia lo script come amministratore (sudo)."

# Cosa serve nella cartella del bot
[[ -f "$UNITA_ORIGINE" ]] || errore "manca $UNITA_ORIGINE."
[[ -f "$CARTELLA/.env" ]] || errore "manca il file .env in $CARTELLA: copia .env.example e compilalo."
[[ -x "$CARTELLA/.venv/bin/python" ]] || errore "manca l'ambiente Python (.venv): lancia prima ./avvia.sh una volta."

# Utente di sistema, senza shell e senza password
if id "$UTENTE" >/dev/null 2>&1; then
    info "L'utente $UTENTE c'è già."
else
    esegui useradd --system --home-dir "$CARTELLA" --shell /usr/sbin/nologin "$UTENTE"
fi

# Cartelle in cui il bot scrive; il resto resta in sola lettura per il servizio.
esegui mkdir -p "$CARTELLA/logs" "$CARTELLA/data"
esegui chown -R "$UTENTE:$UTENTE" "$CARTELLA/logs" "$CARTELLA/data"
esegui chmod 600 "$CARTELLA/.env"
esegui chown "$UTENTE:$UTENTE" "$CARTELLA/.env"

# Unità: i percorsi dell'esempio (/opt/iyokai) diventano quelli veri.
if (( PROVA )); then
    info "(prova) copio $UNITA_ORIGINE in $UNITA_DESTINAZIONE con i percorsi di $CARTELLA"
else
    sed "s#/opt/iyokai#$CARTELLA#g" "$UNITA_ORIGINE" > "$UNITA_DESTINAZIONE"
    chmod 644 "$UNITA_DESTINAZIONE"
fi
esegui systemctl daemon-reload
esegui systemctl enable --now iyokai-bot.service
info "Fatto. Controlla con: systemctl status iyokai-bot  e  curl -s http://127.0.0.1:8424/salute"

# avvia.ps1
# =========
# Avvio completo di iYokai su Windows, nell'ordine giusto:
#   1. controlla il file .env;
#   2. prepara l'ambiente Python e installa i requisiti (solo se sono cambiati);
#   3. accende il Lavalink locale (Docker Desktop) e aspetta che risponda;
#   4. avvia il bot.
# Uso (PowerShell, dalla cartella del bot):  .\avvia.ps1   oppure  .\avvia.ps1 -SenzaLavalink
# Se Windows blocca lo script: powershell -ExecutionPolicy Bypass -File .\avvia.ps1
# Nessun segreto qui: password e chiavi si leggono dal .env.

param([switch]$SenzaLavalink)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$AttesaLavalink = 300   # secondi; al primo avvio Lavalink scarica i plugin

function Info($testo) { Write-Host "[avvio] $testo" }
function Errore($testo) { Write-Host "[avvio] ERRORE: $testo" -ForegroundColor Red; exit 1 }

# Legge una variabile dal .env senza eseguirne il contenuto.
function Leggi-Env($nome) {
    $riga = Get-Content .env | Where-Object { $_ -match "^$nome=" } | Select-Object -Last 1
    if (-not $riga) { return "" }
    $valore = $riga.Substring($nome.Length + 1).Trim()
    return $valore.Trim('"').Trim("'")
}

# 1. Il file .env
if (-not (Test-Path .env)) { Errore "manca il file .env. Copia .env.example in .env e compilalo." }

# 2. Ambiente Python e requisiti
$Py = ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Info "Creo l'ambiente Python in .venv"
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { Errore "non riesco a creare .venv: serve Python 3.11 (comando py)." }
}
$Impronta = (Get-FileHash requirements.lock -Algorithm SHA256).Hash
$Salvata = if (Test-Path .venv\.requisiti) { Get-Content .venv\.requisiti -Raw } else { "" }
if ($Salvata -ne $Impronta) {
    Info "Installo i requisiti (requirements.lock)"
    & $Py -m pip install --upgrade pip | Out-Null
    & $Py -m pip install -r requirements.lock
    if ($LASTEXITCODE -ne 0) { Errore "installazione dei requisiti non riuscita." }
    Set-Content -Path .venv\.requisiti -Value $Impronta -NoNewline
}

# 3. Lavalink locale
$Host_ = Leggi-Env "LAVALINK_HOST"
$Porta = Leggi-Env "LAVALINK_PORT"; if (-not $Porta) { $Porta = "2333" }
$Password = Leggi-Env "LAVALINK_PASSWORD"

function Lavalink-Risponde {
    try {
        $r = Invoke-WebRequest -Uri "http://${Host_}:$Porta/version" -Headers @{ Authorization = $Password } -TimeoutSec 3 -UseBasicParsing
        return $r.StatusCode -eq 200
    } catch { return $false }
}

if ($SenzaLavalink) {
    Info "Lavalink saltato (-SenzaLavalink)"
} elseif ($Host_ -ne "127.0.0.1" -and $Host_ -ne "localhost") {
    Info "Nessun Lavalink locale nel .env (LAVALINK_HOST=$Host_): uso i nodi indicati lì"
} else {
    if (-not $Password -or $Password -eq "CAMBIAMI") { Errore "imposta LAVALINK_PASSWORD nel .env." }
    if (Lavalink-Risponde) {
        Info "Lavalink è già acceso"
    } else {
        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            Errore "Lavalink locale non risponde e Docker non c'è. Installa Docker Desktop o avvia Lavalink a mano."
        }
        Info "Accendo Lavalink (Docker)"
        $env:LAVALINK_PASSWORD = $Password
        foreach ($nome in "MAIN_RADIO_LOCAL_FOLDER","MUSICA_CARTELLA_OWNER","SPOTIFY_CLIENT_ID","SPOTIFY_CLIENT_SECRET","APPLE_MUSIC_TOKEN","TIDAL_TOKEN","YANDEX_MUSIC_TOKEN") {
            $valore = Leggi-Env $nome
            if ($valore) { Set-Item -Path "env:$nome" -Value $valore }
        }
        Push-Location deploy\lavalink
        docker compose up -d
        $esito = $LASTEXITCODE
        Pop-Location
        if ($esito -ne 0) { Errore "docker compose non è partito. Docker Desktop è acceso?" }
        Info "Aspetto che Lavalink risponda (al massimo ${AttesaLavalink}s)"
        $inizio = Get-Date
        while (-not (Lavalink-Risponde)) {
            if (((Get-Date) - $inizio).TotalSeconds -ge $AttesaLavalink) {
                Errore "Lavalink non risponde dopo ${AttesaLavalink}s. Guarda: cd deploy\lavalink; docker compose logs lavalink"
            }
            Start-Sleep -Seconds 3
        }
        Info ("Lavalink pronto in {0:N0}s" -f ((Get-Date) - $inizio).TotalSeconds)
    }
}

# 4. Il bot
Info "Avvio il bot"
& $Py main.py
exit $LASTEXITCODE

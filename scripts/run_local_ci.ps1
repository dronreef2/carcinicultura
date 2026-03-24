param(
    [switch]$RunSmoke,
    [switch]$SimulateAck,
    [string]$PythonCmd = "python",
    [string]$BackendUrl = "http://localhost:8000",
    [string]$MqttHost = "localhost",
    [int]$MqttPort = 1883,
    [string]$MqttUser = "camarao",
    [string]$MqttPassword = "mqtt_senha_segura",
    [string]$PondId = "pond-01",
    [string]$FarmId = "farm-01",
    [string]$Command = "pulse",
    [int]$DurationS = 5,
    [int]$TimeoutS = 20
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Test-TcpPort {
    param(
        [string]$Host,
        [int]$Port,
        [int]$TimeoutMs = 2000
    )

    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($Host, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if (-not $ok) {
            $client.Close()
            return $false
        }
        $client.EndConnect($iar) | Out-Null
        $client.Close()
        return $true
    }
    catch {
        return $false
    }
}

Write-Host "[CI-LOCAL] Iniciando validação local..." -ForegroundColor Cyan

Write-Host "[CI-LOCAL] 1/3 Compile backend e testes" -ForegroundColor Yellow
& $PythonCmd -m compileall backend\app backend\tests backend\scripts
if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha no compileall."
}

Write-Host "[CI-LOCAL] 2/3 Testes unitários" -ForegroundColor Yellow
& $PythonCmd -m pytest backend\tests -q
if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha nos testes unitários."
}

if (-not $RunSmoke) {
    Write-Host "[CI-LOCAL] 3/3 Smoke E2E ignorado (use -RunSmoke para habilitar)." -ForegroundColor DarkYellow
    Write-Host "[CI-LOCAL] Concluído com sucesso (unitário)." -ForegroundColor Green
    exit 0
}

Write-Host "[CI-LOCAL] Verificando pré-requisitos do smoke..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "$BackendUrl/api/health" -Method Get -TimeoutSec 5
    if (-not $health) {
        throw "Resposta vazia do backend"
    }
}
catch {
    Write-Error "Backend indisponível em $BackendUrl. Suba os serviços antes: Set-Location backend; docker compose up -d"
}

if (-not (Test-TcpPort -Host $MqttHost -Port $MqttPort)) {
    Write-Error "MQTT indisponível em ${MqttHost}:${MqttPort}. Suba os serviços antes: Set-Location backend; docker compose up -d"
}

Write-Host "[CI-LOCAL] 3/3 Smoke E2E comando->ACK->status" -ForegroundColor Yellow
$smokeArgs = @(
    "backend\\scripts\\smoke_command_ack.py",
    "--backend-url", $BackendUrl,
    "--mqtt-host", $MqttHost,
    "--mqtt-port", $MqttPort,
    "--mqtt-user", $MqttUser,
    "--mqtt-password", $MqttPassword,
    "--pond-id", $PondId,
    "--farm-id", $FarmId,
    "--command", $Command,
    "--duration-s", $DurationS,
    "--timeout", $TimeoutS
)

if ($SimulateAck) {
    Write-Host "[CI-LOCAL] Smoke em modo simulado (sem firmware físico)." -ForegroundColor DarkYellow
    $smokeArgs += "--simulate-ack"
}

& $PythonCmd @smokeArgs

if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha no smoke E2E."
}

Write-Host "[CI-LOCAL] Concluído com sucesso (unitário + smoke)." -ForegroundColor Green

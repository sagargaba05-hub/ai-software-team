$ErrorActionPreference = "Stop"
$frameworkRoot = Split-Path -Parent $PSScriptRoot
$env:DATA_DIR = Join-Path $frameworkRoot "omniroute-data"
$env:OMNIROUTE_CLI_SKIP_REPO_ENV = "1"
$env:OMNIROUTE_SERVER_HOST = "127.0.0.1"
$env:OMNIROUTE_API_KEY = "local-omniroute"
$env:RATE_LIMIT_MAX_WAIT_MS = "300000"
$env:OMNIROUTE_DIRECT_HEADERS_TIMEOUT_MS = "300000"

$command = Get-Command "omniroute.cmd" -ErrorAction Stop
& $command.Source serve --daemon --no-open --port 20128

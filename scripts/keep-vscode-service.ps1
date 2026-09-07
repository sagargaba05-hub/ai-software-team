param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$ServiceName,

    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 65535)]
    [int]$Port,

    [ValidateRange(0, 65535)]
    [int]$DependsOnPort = 0,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Executable,

    [string[]]$ServiceArguments = @()
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
    throw "$ServiceName executable does not exist: $Executable"
}

function Test-ServiceListener {
    [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

Write-Host "$ServiceName keeper active for VS Code (port $Port)."

while ($true) {
    if (Test-ServiceListener) {
        Start-Sleep -Seconds 2
        continue
    }

    if ($DependsOnPort -gt 0 -and -not [bool](
        Get-NetTCPConnection -State Listen -LocalPort $DependsOnPort -ErrorAction SilentlyContinue
    )) {
        Write-Host "$ServiceName is waiting for port $DependsOnPort."
        Start-Sleep -Seconds 2
        continue
    }

    Write-Host "Starting $ServiceName..."
    & $Executable @ServiceArguments
    $exitCode = $LASTEXITCODE
    Write-Warning "$ServiceName exited with code $exitCode; retrying in 3 seconds."
    Start-Sleep -Seconds 3
}

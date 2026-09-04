[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$Create
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    py tools/verify_station.py
    if ($LASTEXITCODE -ne 0) {
        throw 'Station verification failed.'
    }

    py -m uv --version
    if ($LASTEXITCODE -ne 0) {
        throw 'uv is unavailable through the Python launcher (`py -m uv`).'
    }

    $pythonPath = py -m uv python find 3.12
    if ($LASTEXITCODE -ne 0) {
        throw 'Python 3.12 is unavailable to uv.'
    }

    Write-Host "Python 3.12 candidate: $pythonPath"
    if (-not $Create) {
        Write-Host 'Read-only preflight passed. Re-run with -Create after the hardware upgrade to create .venv.'
        return
    }

    if ($PSCmdlet.ShouldProcess((Join-Path $repoRoot '.venv'), 'Create Python 3.12 virtual environment')) {
        py -m uv venv --python 3.12 .venv
        if ($LASTEXITCODE -ne 0) {
            throw 'Virtual-environment creation failed.'
        }
        & (Join-Path $repoRoot '.venv\Scripts\python.exe') -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) {
            throw 'Synthetic tests failed in the new environment.'
        }
    }

    Write-Host 'No ML package, Kaggle credential, competition data, or notebook was accessed.'
}
finally {
    Pop-Location
}

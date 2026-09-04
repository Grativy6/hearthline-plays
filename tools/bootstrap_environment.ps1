[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$Create
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    py -m uv --version
    if ($LASTEXITCODE -ne 0) {
        throw 'uv is unavailable through the Python launcher (`py -m uv`).'
    }

    $pythonCandidate = py -m uv python find 3.12 --offline --no-python-downloads --no-project --no-config
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($pythonCandidate)) {
        throw 'Python 3.12 is not already available; this script will not download it.'
    }
    $pythonPath = $pythonCandidate.Trim()

    Write-Host "Python 3.12 candidate: $pythonPath"
    & $pythonPath tools/verify_station.py
    if ($LASTEXITCODE -ne 0) {
        throw 'Station verification failed.'
    }

    if (-not $Create) {
        Write-Host 'Read-only preflight passed. Use -Create only after a separate setup instruction.'
        return
    }

    if ($PSCmdlet.ShouldProcess((Join-Path $repoRoot '.venv'), 'Create inert Python 3.12 environment')) {
        py -m uv venv --python $pythonPath --offline --no-python-downloads --no-project --no-config .venv
        if ($LASTEXITCODE -ne 0) {
            throw 'Virtual-environment creation failed.'
        }
        & (Join-Path $repoRoot '.venv\Scripts\python.exe') -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) {
            throw 'Synthetic tests failed in the new environment.'
        }
    }

    Write-Host 'No SDK package, credential, benchmark data, model, evaluator, or Kaggle task was accessed.'
}
finally {
    Pop-Location
}

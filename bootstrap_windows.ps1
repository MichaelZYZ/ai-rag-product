param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'

function Test-Python {
    param([string]$Executable, [string[]]$Prefix = @())
    try {
        & $Executable @Prefix -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Find-Python {
    $candidates = @(
        @{ Executable = 'py'; Prefix = @('-3.11') },
        @{ Executable = 'py'; Prefix = @('-3.12') },
        @{ Executable = 'py'; Prefix = @('-3') },
        @{ Executable = 'python'; Prefix = @() },
        @{ Executable = 'python3'; Prefix = @() }
    )
    if ($env:LOCALAPPDATA) {
        $candidates += @{ Executable = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'); Prefix = @() }
    }
    if ($env:ProgramFiles) {
        $candidates += @{ Executable = (Join-Path $env:ProgramFiles 'Python311\python.exe'); Prefix = @() }
    }
    foreach ($candidate in $candidates) {
        if (Test-Python -Executable $candidate.Executable -Prefix $candidate.Prefix) {
            return $candidate
        }
    }
    return $null
}

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments, [string]$Step)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed (exit code $LASTEXITCODE)."
    }
}

function Test-Pip {
    param([string]$PythonExecutable)
    try {
        & $PythonExecutable -m pip --version 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Test-ProjectImports {
    param([string]$PythonExecutable)
    try {
        & $PythonExecutable -c 'import fastapi, uvicorn, numpy, sklearn, pypdf; import importlib.metadata as m; m.version("python-multipart")' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

try {
    Set-Location -LiteralPath $ProjectRoot
    Write-Host '[1/5] Checking Python 3.9 or newer...'
    $python = Find-Python
    if (-not $python) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw 'Python is missing and winget is unavailable. Install Python 3.11 from https://www.python.org/downloads/windows/ with pip enabled, then run this file again.'
        }
        Write-Host 'Python is missing. Installing Python 3.11 for the current user with winget...'
        & winget install --id Python.Python.3.11 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            Write-Host "winget exited with code $LASTEXITCODE; checking whether Python was installed anyway..."
        }
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
        $python = Find-Python
        if (-not $python) {
            throw 'Python installation did not produce a usable Python 3.9+ command. Check the winget output and rerun this file.'
        }
    }

    $venvPath = Join-Path $ProjectRoot '.venv'
    $venvPython = Join-Path $venvPath 'Scripts\python.exe'
    Write-Host '[2/5] Checking the project virtual environment...'
    if (-not (Test-Python -Executable $venvPython)) {
        Write-Host 'Creating or repairing .venv...'
        $pythonArgs = $python.Prefix + @('-m', 'venv', '--clear', $venvPath)
        Invoke-Checked -Executable $python.Executable -Arguments $pythonArgs -Step 'Virtual environment creation'
    }
    if (-not (Test-Python -Executable $venvPython)) {
        throw 'The virtual environment Python is not usable after creation.'
    }

    Write-Host '[3/5] Checking pip and installing required packages...'
    if (-not (Test-Pip -PythonExecutable $venvPython)) {
        Invoke-Checked -Executable $venvPython -Arguments @('-m', 'ensurepip', '--upgrade') -Step 'pip installation'
    }
    Invoke-Checked -Executable $venvPython -Arguments @('-m', 'pip', 'install', '--disable-pip-version-check', '--prefer-binary', '-r', 'requirements.txt') -Step 'Dependency installation'
    if (-not (Test-ProjectImports -PythonExecutable $venvPython)) {
        Write-Host 'A package is installed but cannot be imported. Repairing dependencies...'
        Invoke-Checked -Executable $venvPython -Arguments @('-m', 'pip', 'install', '--disable-pip-version-check', '--prefer-binary', '--force-reinstall', '-r', 'requirements.txt') -Step 'Dependency repair'
        if (-not (Test-ProjectImports -PythonExecutable $venvPython)) {
            throw 'Required Python packages still cannot be imported after repair.'
        }
    }
    Invoke-Checked -Executable $venvPython -Arguments @('-m', 'pip', 'check') -Step 'Dependency verification'

    Write-Host '[4/5] Preparing the database without replacing saved data...'
    Invoke-Checked -Executable $venvPython -Arguments @('seed.py', '--if-empty') -Step 'Database initialization'

    Write-Host '[5/5] Starting the local server...'
    Invoke-Checked -Executable $venvPython -Arguments @('run_server.py') -Step 'Server startup'
    exit 0
} catch {
    Write-Host ('[ERROR] ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}

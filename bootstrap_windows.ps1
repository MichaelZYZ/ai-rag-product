param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'

function Get-PythonInfo {
    param([string]$Executable, [string[]]$Prefix = @())
    try {
        $output = & $Executable @Prefix -c 'import json,sys; print(json.dumps({"path":sys.executable,"major":sys.version_info.major,"minor":sys.version_info.minor,"version":sys.version.split()[0]}))' 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $output) { return $null }
        $info = @($output)[-1] | ConvertFrom-Json
        if ($info.major -ne 3 -or $info.minor -lt 9 -or -not $info.path) { return $null }
        return $info
    } catch {
        return $null
    }
}

function Add-PythonCandidate {
    param($Candidates, [hashtable]$Seen, [string]$Executable, [string[]]$Prefix = @())
    $info = Get-PythonInfo -Executable $Executable -Prefix $Prefix
    if (-not $info) { return }
    $key = $info.path.ToLowerInvariant()
    if ($Seen.ContainsKey($key)) { return }
    $Seen[$key] = $true
    $Candidates.Add([pscustomobject]@{
        Executable = $Executable
        Prefix = $Prefix
        Path = $info.path
        Version = $info.version
    }) | Out-Null
}

function Find-PythonCandidates {
    $candidates = New-Object 'System.Collections.Generic.List[System.Object]'
    $seen = @{}

    # Both the older Windows launcher and the newer Python install manager support -0p.
    $launcher = Get-Command py -CommandType Application -ErrorAction SilentlyContinue
    if ($launcher) {
        $detected = @()
        $launcherLines = @()
        try {
            $launcherLines = @(& $launcher.Source -0p 2>$null)
            foreach ($line in $launcherLines) {
                if ($line -match '3\.(\d+)') {
                    $minor = [int]$Matches[1]
                    if ($minor -ge 9) { $detected += $minor }
                }
            }
        } catch { }
        $detected = @($detected | Sort-Object -Unique)
        $preferred = @(11, 12, 13, 14, 10, 9)
        $ordered = @($preferred | Where-Object { $detected -contains $_ }) +
                   @($detected | Where-Object { $preferred -notcontains $_ } | Sort-Object -Descending)
        foreach ($minor in $ordered) {
            Add-PythonCandidate -Candidates $candidates -Seen $seen -Executable $launcher.Source -Prefix @("-3.$minor")
        }
        foreach ($line in $launcherLines) {
            if ($line -match '(?i)([A-Z]:\\[^\r\n]*?python\.exe)') {
                Add-PythonCandidate -Candidates $candidates -Seen $seen -Executable $Matches[1]
            }
        }
        # Covers launchers that do not return a parseable version list.
        Add-PythonCandidate -Candidates $candidates -Seen $seen -Executable $launcher.Source -Prefix @('-3')
    }

    foreach ($root in @($env:LOCALAPPDATA, $env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if (-not $root) { continue }
        $programs = if ($root -eq $env:LOCALAPPDATA) { Join-Path $root 'Programs\Python' } else { $root }
        if (-not (Test-Path -LiteralPath $programs)) { continue }
        foreach ($directory in @(Get-ChildItem -LiteralPath $programs -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue)) {
            $path = Join-Path $directory.FullName 'python.exe'
            if (Test-Path -LiteralPath $path) {
                Add-PythonCandidate -Candidates $candidates -Seen $seen -Executable $path
            }
        }
    }

    foreach ($name in @('python.exe', 'python3.exe', 'python3.11.exe', 'python3.12.exe',
                         'python3.13.exe', 'python3.14.exe', 'python3.10.exe', 'python3.9.exe')) {
        foreach ($command in @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
            Add-PythonCandidate -Candidates $candidates -Seen $seen -Executable $command.Source
        }
    }
    return $candidates.ToArray()
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

function Install-Dependencies {
    param([string]$PythonExecutable)
    if (-not (Test-Pip -PythonExecutable $PythonExecutable)) {
        Invoke-Checked -Executable $PythonExecutable -Arguments @('-m', 'ensurepip', '--upgrade') -Step 'pip installation'
    }
    Invoke-Checked -Executable $PythonExecutable -Arguments @('-m', 'pip', 'install', '--disable-pip-version-check', '--prefer-binary', '-r', 'requirements.txt') -Step 'Dependency installation'
    if (-not (Test-ProjectImports -PythonExecutable $PythonExecutable)) {
        Write-Host 'A package is installed but cannot be imported. Repairing dependencies...'
        Invoke-Checked -Executable $PythonExecutable -Arguments @('-m', 'pip', 'install', '--disable-pip-version-check', '--prefer-binary', '--force-reinstall', '-r', 'requirements.txt') -Step 'Dependency repair'
        if (-not (Test-ProjectImports -PythonExecutable $PythonExecutable)) {
            throw 'Required Python packages still cannot be imported after repair.'
        }
    }
    Invoke-Checked -Executable $PythonExecutable -Arguments @('-m', 'pip', 'check') -Step 'Dependency verification'
}

function Try-PythonCandidate {
    param($Candidate, [string]$VenvPath, [string]$VenvPython)
    Write-Host "Trying Python $($Candidate.Version): $($Candidate.Path)"
    $pythonArgs = @($Candidate.Prefix) + @('-m', 'venv', '--clear', $VenvPath)
    Invoke-Checked -Executable $Candidate.Executable -Arguments $pythonArgs -Step 'Virtual environment creation'
    if (-not (Get-PythonInfo -Executable $VenvPython)) {
        throw 'The virtual environment Python is not usable after creation.'
    }
    Install-Dependencies -PythonExecutable $VenvPython
}

try {
    Set-Location -LiteralPath $ProjectRoot
    $venvPath = Join-Path $ProjectRoot '.venv'
    $venvPython = Join-Path $venvPath 'Scripts\python.exe'
    $venvPythonFullPath = [System.IO.Path]::GetFullPath($venvPython)
    $ready = $false
    $attempted = @{}
    $attemptedPython311 = $false
    $failures = New-Object 'System.Collections.Generic.List[System.String]'

    Write-Host '[1/5] Checking Python 3.9 or newer...'
    Write-Host '[2/5] Checking the project virtual environment...'
    $existing = Get-PythonInfo -Executable $venvPython
    if ($existing) {
        Write-Host "Using existing .venv (Python $($existing.version))."
        try {
            Write-Host '[3/5] Checking pip and installing required packages...'
            Install-Dependencies -PythonExecutable $venvPython
            $ready = $true
        } catch {
            $failures.Add("Existing .venv: $($_.Exception.Message)") | Out-Null
            Write-Warning 'The existing .venv could not be repaired; trying installed Python versions.'
        }
    }

    if (-not $ready) {
        foreach ($candidate in @(Find-PythonCandidates)) {
            if ($candidate.Path -ieq $venvPythonFullPath) { continue }
            $attempted[$candidate.Path.ToLowerInvariant()] = $true
            if ($candidate.Version -match '^3\.11\.') { $attemptedPython311 = $true }
            try {
                Write-Host '[3/5] Checking pip and installing required packages...'
                Try-PythonCandidate -Candidate $candidate -VenvPath $venvPath -VenvPython $venvPython
                $ready = $true
                break
            } catch {
                $failures.Add("Python $($candidate.Version) ($($candidate.Path)): $($_.Exception.Message)") | Out-Null
                Write-Warning "Python $($candidate.Version) could not prepare the environment; trying the next version."
            }
        }
    }

    if (-not $ready) {
        $winget = Get-Command winget -CommandType Application -ErrorAction SilentlyContinue
        if ($winget -and -not $attemptedPython311) {
            Write-Host 'No installed Python completed setup. Installing Python 3.11 for the current user with winget...'
            & $winget.Source install --id Python.Python.3.11 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "winget exited with code $LASTEXITCODE; checking whether Python was installed anyway."
            }
            $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                        [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + $env:Path
            foreach ($candidate in @(Find-PythonCandidates)) {
                if ($candidate.Path -ieq $venvPythonFullPath) { continue }
                if ($attempted.ContainsKey($candidate.Path.ToLowerInvariant())) { continue }
                try {
                    Try-PythonCandidate -Candidate $candidate -VenvPath $venvPath -VenvPython $venvPython
                    $ready = $true
                    break
                } catch {
                    $failures.Add("Python $($candidate.Version) ($($candidate.Path)): $($_.Exception.Message)") | Out-Null
                }
            }
        }
    }

    if (-not $ready) {
        foreach ($failure in $failures) { Write-Warning $failure }
        throw 'No Python 3.9+ installation could complete setup. Check the errors above, network access, and https://www.python.org/downloads/windows/.'
    }

    $selected = Get-PythonInfo -Executable $venvPython
    Write-Host "Environment ready with Python $($selected.version): $($selected.path)"
    Write-Host '[4/5] Preparing the database without replacing saved data...'
    Invoke-Checked -Executable $venvPython -Arguments @('seed.py', '--if-empty') -Step 'Database initialization'

    Write-Host '[5/5] Starting the local server...'
    Invoke-Checked -Executable $venvPython -Arguments @('run_server.py') -Step 'Server startup'
    exit 0
} catch {
    Write-Host ('[ERROR] ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}

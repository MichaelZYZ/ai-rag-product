param([Parameter(Mandatory = $true)][string]$PythonExecutable, [string]$ExpectedVersion = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

# Load only function definitions; do not execute installation/server startup.
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $projectRoot 'bootstrap_windows.ps1'), [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
foreach ($statement in $ast.EndBlock.Statements) {
    if ($statement -is [System.Management.Automation.Language.FunctionDefinitionAst]) {
        . ([scriptblock]::Create($statement.Extent.Text))
    }
}

# Execute the real native Python commands under Windows PowerShell 5.1. This
# catches quote-stripping regressions that a mocked interpreter cannot catch.
$info = Get-PythonInfo -Executable $PythonExecutable
if (-not $info) { throw 'Native Python version detection failed.' }
if ($ExpectedVersion -and -not $info.version.StartsWith($ExpectedVersion + '.')) {
    throw "Expected Python $ExpectedVersion, but startup selected $($info.version)."
}
if (-not (Test-ProjectImports -PythonExecutable $PythonExecutable)) {
    throw 'Native dependency/application import check failed.'
}
$failedAsExpected = $false
try {
    Invoke-Checked -Executable $PythonExecutable -Arguments @('-c', 'import sys; sys.exit(7)') -Step 'Expected failure'
} catch {
    if ($_.Exception.Message -match 'exit code 7') { $failedAsExpected = $true }
}
if (-not $failedAsExpected) { throw 'A failed interpreter command must be reported.' }

function Fake-Python {
    param([Parameter(ValueFromRemainingArguments = $true)]$Arguments)
    $global:LASTEXITCODE = 0
    @{path = $script:fakePath; major = $script:fakeMajor; minor = $script:fakeMinor;
      version = "$($script:fakeMajor).$($script:fakeMinor).0"} | ConvertTo-Json -Compress
}
$script:fakePath = 'C:\Custom Python\python.exe'
$script:fakeMajor = 3
foreach ($minor in 9..14) {
    $script:fakeMinor = $minor
    $result = Get-PythonInfo -Executable 'Fake-Python'
    if (-not $result -or $result.minor -ne $minor) { throw "Python 3.$minor was rejected." }
}
$script:fakeMinor = 8
if (Get-PythonInfo -Executable 'Fake-Python') { throw 'Python 3.8 must be rejected.' }
$script:fakeMajor = 2
$script:fakeMinor = 7
if (Get-PythonInfo -Executable 'Fake-Python') { throw 'Python 2.7 must be rejected.' }

$script:fakeMajor = 3
$script:fakeMinor = 11
$candidates = New-Object 'System.Collections.Generic.List[System.Object]'
$seen = @{}
Add-PythonCandidate -Candidates $candidates -Seen $seen -Executable 'Fake-Python'
$script:fakePath = $script:fakePath.ToUpperInvariant()
Add-PythonCandidate -Candidates $candidates -Seen $seen -Executable 'Fake-Python'
if ($candidates.Count -ne 1) { throw 'Interpreter paths must be deduplicated case-insensitively.' }
Write-Host "Windows bootstrap checks passed with Python $($info.version)."

# Install PitchesPeaches. Detects uv, installs it if missing, then installs the
# tool. No admin rights, no PATH surgery beyond uv's own.
$ErrorActionPreference = 'Stop'

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv not found - installing it from astral.sh"
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    # uv's installer puts it here and updates your user PATH for next time.
    $uvBin = Join-Path $env:USERPROFILE ".local\bin"
    if (Test-Path (Join-Path $uvBin "uv.exe")) { $env:PATH = "$uvBin;$env:PATH" }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv still isn't on PATH. Open a new terminal and run this again."
    exit 1
}

uv tool install pitches-peaches

Write-Host ""
Write-Host "Installed. Set your key, then run:"
Write-Host ""
Write-Host '  $env:ANTHROPIC_API_KEY = "sk-ant-..."'
Write-Host '  peaches run https://the-job-posting --cv ~\cv.pdf'

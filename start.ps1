#Requires -Version 5.1
<#
  gatepack — the Windows entry point (the equivalent of ./start on POSIX).

    .\start.ps1              the desktop app
    .\start.ps1 dev          the desktop app with renderer live-reload
    .\start.ps1 cli ARGS...  the command-line core
    .\start.ps1 doctor       report what is installed and what is missing
    .\start.ps1 help         this text

  Everything below either works or says why it does not; nothing here fakes a
  result.  The native Windows build ships no bundled toolchain — synthesis and
  verification need OSS CAD Suite or WSL2, and `.\start.ps1 doctor` (which
  delegates to `gatepack doctor`) names where a Windows user gets each tool.
  See docs/WINDOWS.md.

  When a prerequisite is absent this script prints a readable message and
  exits non-zero; it never emits a stack trace.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Mode = "app",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$App = Join-Path $Root "app"
$Venv = Join-Path $Root ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"

# Subcommands that shell out to Yosys/sby/Icarus. Anything else runs natively.
$ToolchainCommands = @("estimate", "verify", "build", "simulate", "analyse")

function Fail {
    param([string]$Message)
    Write-Host "error: $Message" -ForegroundColor Red
    exit 1
}

function Warn {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Yellow
}

function Info {
    param([string]$Message)
    Write-Host $Message
}

function Report {
    param([string]$Name, [string]$Found, [string]$Note = "")
    if ($Found) {
        Write-Host ("  OK      {0,-12} {1}" -f $Name, $Found) -ForegroundColor Green
    } else {
        Write-Host ("  MISSING {0,-12} {1}" -f $Name, $Note) -ForegroundColor Red
    }
}

function Test-Have {
    param([string]$Name)
    return ($null -ne (Get-Command $Name -ErrorAction SilentlyContinue))
}

function Get-CoreImportable {
    if (-not (Test-Path $VenvPython)) { return $false }
    $env:PYTHONPATH = $Root
    & $VenvPython -c "import gatepack" *> $null
    return ($LASTEXITCODE -eq 0)
}

function Ensure-Venv {
    if (Get-CoreImportable) { return }

    if (Test-Path $Venv) {
        Fail "`n$Venv exists but 'import gatepack' fails there. Install the dependency:`n`n    $VenvPython -m pip install -e $Root`n`nNot doing this automatically: this venv may be shared with other checkouts."
    }

    # Fresh clone: create the venv and install the one runtime dependency.
    if (-not (Test-Have "python")) {
        Fail "no 'python' on PATH — install Python 3.11+ from python.org and re-run. gatepack will not run without a Python interpreter."
    }
    Info "Creating .venv..."
    & python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Fail "'python -m venv' failed (is Python 3.11+ installed?)." }
    & $VenvPython -m pip install --quiet --upgrade pip
    & $VenvPython -m pip install --quiet -e $Root
    if (-not (Get-CoreImportable)) {
        Fail "install finished but 'import gatepack' still fails"
    }
}

function Invoke-Core {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$CoreArgs)
    $env:PYTHONPATH = $Root
    & $VenvPython -m gatepack.cli @CoreArgs
    exit $LASTEXITCODE
}

function Test-NeedsToolchain {
    param([string[]]$Args)
    foreach ($a in $Args) {
        if ($a.StartsWith("-")) { continue }
        if ($ToolchainCommands -contains $a) { return $true }
        return $false
    }
    return $false
}

function Run-Cli {
    Ensure-Venv
    if ((Test-NeedsToolchain @CliArgs) -and -not (Test-Have "yosys")) {
        Warn "This command needs Yosys, which is not on PATH. On Windows, install OSS CAD Suite (YosysHQ/oss-cad-suite-build) or run gatepack under WSL2 — `.\start.ps1 doctor` lists each tool and where to get it."
    }
    Invoke-Core @CliArgs
}

function Ensure-NodeModules {
    if (-not (Test-Path (Join-Path $App "node_modules"))) {
        Fail "app\node_modules is missing. Run: cd app; npm ci"
    }
}

function Test-BuildStale {
    $out = Join-Path $App "dist\main\index.cjs"
    if (-not (Test-Path $out)) { return $true }
    if (-not (Test-Path (Join-Path $App "dist\renderer\index.html"))) { return $true }
    $outTime = (Get-Item $out).LastWriteTime
    foreach ($d in @("main", "preload", "renderer", "shared")) {
        $dir = Join-Path $App $d
        if (Test-Path $dir) {
            $newer = Get-ChildItem $dir -Recurse -File |
                Where-Object { $_.LastWriteTime -gt $outTime } |
                Select-Object -First 1
            if ($newer) { return $true }
        }
    }
    return $false
}

function Start-App {
    Ensure-Venv
    Ensure-NodeModules

    if (-not (Test-Have "node")) {
        Fail "no 'node' on PATH — install Node.js 20 (from nodejs.org) and re-run."
    }

    if (Test-BuildStale) {
        Info "Building the app..."
        Push-Location $App
        & npm run build
        $code = $LASTEXITCODE
        Pop-Location
        if ($code -ne 0) { Fail "'npm run build' failed" }
    }

    if (-not (Test-Have "yosys")) {
        Warn "Note: no Yosys and no toolchain image on Windows — the app will open, but Build and Verify will report the missing tool rather than producing a result. Install OSS CAD Suite or use WSL2 (docs/WINDOWS.md)."
    }

    Info "Starting gatepack..."
    Push-Location $App
    & npm start
    $code = $LASTEXITCODE
    Pop-Location
    exit $code
}

function Start-Dev {
    Ensure-Venv
    Ensure-NodeModules

    if (-not (Test-Have "node")) {
        Fail "no 'node' on PATH — install Node.js 20 (from nodejs.org) and re-run."
    }

    Info "Compiling main and preload..."
    Push-Location $App
    & npm run build:main
    $code = $LASTEXITCODE
    Pop-Location
    if ($code -ne 0) { Fail "'npm run build:main' failed" }

    $gpout = Join-Path $Root ".gpout"
    New-Item -ItemType Directory -Force -Path $gpout | Out-Null
    $log = Join-Path $gpout "vite.log"

    Info "Starting the Vite dev server..."
    $vite = Start-Process -FilePath "npm.cmd" `
        -ArgumentList @("run", "dev") `
        -WorkingDirectory $App `
        -RedirectStandardOutput $log `
        -RedirectStandardError $log `
        -PassThru -NoNewWindow

    $url = ""
    for ($i = 0; $i -lt 60; $i++) {
        if (Test-Path $log) {
            $match = Select-String -Path $log -Pattern "http://localhost:[0-9]+" | Select-Object -First 1
            if ($match) { $url = $match.Matches[0].Value; break }
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $url) {
        Stop-Process -Id $vite.Id -Force -ErrorAction SilentlyContinue
        Fail "Vite did not report a URL within 30s — see .gpout\vite.log"
    }

    Info "Renderer on $url — starting Electron (edits reload live)."
    $env:GATEPACK_DEV_SERVER = $url
    Push-Location $App
    & npm start
    $code = $LASTEXITCODE
    Pop-Location
    Stop-Process -Id $vite.Id -Force -ErrorAction SilentlyContinue
    exit $code
}

function Show-Doctor {
    Ensure-Venv
    Info "Core"
    # The core's own report (with Windows-specific tool guidance) is the source
    # of truth; this launcher only adds the desktop-app environment notes.
    & $VenvPython -m gatepack.cli doctor
    if ($LASTEXITCODE -ne 0) { Warn "`gatepack doctor` exited $LASTEXITCODE" }

    Write-Host ""
    Info "Desktop app"
    $node = Get-Command node -ErrorAction SilentlyContinue
    if ($node) { Report "node" ($node.Version.ToString()) } else { Report "node" "" }
    if (Test-Path (Join-Path $App "node_modules")) { Report "node_modules" "installed" } else { Report "node_modules" "" }
    if (Test-Path (Join-Path $App "dist\main\index.cjs")) { Report "build" "compiled" } else { Report "build" "" "not built yet" }
    $bundled = Join-Path $App "resources\bin\gatepack.exe"
    if (Test-Path $bundled) { Report "bundled-core" $bundled } else { Report "bundled-core" "" "not bundled — a packaged app would find no core" }
}

function Show-Usage {
    @(
        "gatepack — one entry point for the two things you can start.",
        "",
        "  .\start.ps1              the desktop app",
        "  .\start.ps1 dev          the desktop app with renderer live-reload",
        "  .\start.ps1 cli ARGS...  the command-line core",
        "  .\start.ps1 doctor       report what is installed and what is missing"
    ) | ForEach-Object { Write-Host $_ }
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root ".gpout") | Out-Null

$mode = $Mode.ToLower()
if ($mode -eq "app") {
    Start-App
} elseif ($mode -eq "dev") {
    Start-Dev
} elseif ($mode -eq "cli") {
    if ($CliArgs.Count -eq 0) { $CliArgs = @("--help") }
    Run-Cli
} elseif ($mode -eq "doctor") {
    Show-Doctor
} elseif ($mode -in @("help", "-h", "--help")) {
    Show-Usage
} else {
    Fail "Unknown mode '$Mode'. Try: .\start.ps1 [app|dev|cli|doctor|help]"
}

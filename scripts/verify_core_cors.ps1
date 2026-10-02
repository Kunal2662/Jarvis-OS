<#
.SYNOPSIS
    Live end-to-end verification that the packaged desktop shell can reach Core.

.DESCRIPTION
    Regression harness for the P0 fixed in ApiSettings.cors_origins: the packaged
    Tauri app's origin (http://tauri.localhost) was absent from the CORS allowlist,
    so every request was rejected with "400 Disallowed CORS origin".

    Starts the REAL console entry point (jarvis-api) under DEFAULT CONFIGURATION --
    no JARVIS_* environment override -- then exercises the full desktop request
    chain against it over real HTTP:

        start -> wait for port -> health -> CORS allow matrix -> CORS deny matrix
              -> session bootstrap -> authenticated request -> smart home -> stop

    Every assertion is a real socket round trip. Nothing is mocked.

.NOTES
    Requires Windows PowerShell 5.1+ (no pwsh dependency).
    Exits 0 when every check passes, 1 otherwise -- safe for CI.
#>
[CmdletBinding()]
param(
    # Repo root. Resolved below to the parent of this script's directory.
    [string]$RepoRoot = '',

    # Must match ApiSettings.host / ApiSettings.port defaults.
    [string]$ApiHost = '127.0.0.1',
    [int]$Port = 8765,

    # Seconds to wait for the port to accept connections.
    [int]$StartupTimeoutSec = 120,

    # Keep the server running after the checks (for manual poking).
    [switch]$NoStop
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# $PSScriptRoot is not populated while param defaults are evaluated in
# Windows PowerShell 5.1, so resolve the repo root here instead.
if ([string]::IsNullOrEmpty($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}

# TLS/HTTP plumbing: PS 5.1's Invoke-WebRequest defaults to the IE parsing
# engine, which needs -UseBasicParsing on a headless box.
$PSDefaultParameterValues['Invoke-WebRequest:UseBasicParsing'] = $true

$BaseUrl    = "http://${ApiHost}:${Port}"
$HealthPath = '/api/v1/health'

# --------------------------------------------------------------------------
# Origins. Kept as literals rather than read back from settings.py so that a
# silent edit to the allowlist fails this harness instead of agreeing with it.
# --------------------------------------------------------------------------
$AllowedOrigins = @(
    'http://localhost'            # plain browser dev on port 80
    'http://127.0.0.1'            # same, loopback literal
    'http://localhost:3000'       # canonical frontend dev server / Tauri devUrl
    'http://127.0.0.1:3000'       # same, loopback literal
    'http://tauri.localhost'      # PACKAGED desktop app (Windows) -- the P0
    'tauri://localhost'           # packaged desktop app (macOS/Linux)
)

# Near-misses on purpose: exact matching is the entire security property.
$BlockedOrigins = @(
    'https://evil.example'
    'http://evil.example'
    'http://tauri.localhost.evil.example'   # suffix attack on the Tauri host
    'http://localhost:9999'                 # a localhost port that is NOT configured
    'https://tauri.localhost'               # https variant (useHttpsScheme not enabled)
    'https://localhost:3000'                # right host/port, wrong scheme
)

# --------------------------------------------------------------------------
# Result accumulator
# --------------------------------------------------------------------------
$script:Results = [ordered]@{}
$script:Failures = New-Object System.Collections.Generic.List[string]

function Set-Result {
    param([string]$Name, [bool]$Ok, [string]$Detail = '')
    if ($script:Results.Contains($Name)) {
        # A stage with many sub-assertions latches to FAIL on first problem.
        if (-not $Ok) { $script:Results[$Name] = $false }
    } else {
        $script:Results[$Name] = $Ok
    }
    if (-not $Ok) {
        $script:Failures.Add("[$Name] $Detail")
        Write-Host "    FAIL  $Detail" -ForegroundColor Red
    }
}

function Write-Stage { param([string]$Text) Write-Host "`n== $Text" -ForegroundColor Cyan }

# --------------------------------------------------------------------------
# HTTP helper. Returns status + headers for BOTH success and error responses;
# PS 5.1 throws on any non-2xx, and a 400 is an expected outcome here.
# --------------------------------------------------------------------------
function Invoke-Http {
    param(
        [string]$Method = 'GET',
        [string]$Path,
        [hashtable]$Headers = @{},
        [string]$Body
    )
    $uri = "$BaseUrl$Path"
    # Not $args -- that is an automatic variable in PowerShell.
    $req = @{ Method = $Method; Uri = $uri; Headers = $Headers; TimeoutSec = 30 }
    if ($PSBoundParameters.ContainsKey('Body')) {
        $req['Body']        = $Body
        $req['ContentType'] = 'application/json'
    }
    try {
        $r = Invoke-WebRequest @req
        return [pscustomobject]@{
            Status  = [int]$r.StatusCode
            Headers = $r.Headers
            Content = $r.Content
            Threw   = $false
        }
    } catch {
        $resp = $null
        if ($_.PSObject.Properties['Exception'] -and $_.Exception.PSObject.Properties['Response']) {
            $resp = $_.Exception.Response
        }
        if ($null -eq $resp) {
            # Connection refused / DNS / timeout -- no HTTP response at all.
            return [pscustomobject]@{
                Status = 0; Headers = @{}; Content = $_.Exception.Message; Threw = $true
            }
        }
        $status = [int]$resp.StatusCode
        $hdrs = @{}
        foreach ($k in $resp.Headers.AllKeys) { $hdrs[$k] = $resp.Headers[$k] }
        $content = ''
        try {
            $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
            $content = $sr.ReadToEnd(); $sr.Close()
        } catch { }
        return [pscustomobject]@{
            Status = $status; Headers = $hdrs; Content = $content; Threw = $true
        }
    }
}

function Get-Header {
    param($Headers, [string]$Name)
    if ($null -eq $Headers) { return $null }
    foreach ($k in @($Headers.Keys)) {
        if ($k -and $k.ToString().ToLowerInvariant() -eq $Name.ToLowerInvariant()) {
            $v = $Headers[$k]
            if ($v -is [array]) { return ($v -join ',') }
            return $v
        }
    }
    return $null
}

function Test-PortOpen {
    # Raw TCP probe rather than Test-NetConnection: no NetTCPIP module
    # dependency, and no multi-second ICMP fallback.
    param([string]$TargetHost, [int]$TargetPort)
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect($TargetHost, $TargetPort)
        $c.Close()
        return $true
    } catch { return $false }
}

function Invoke-Preflight {
    param([string]$Origin, [string]$Method = 'GET')
    return Invoke-Http -Method 'OPTIONS' -Path $HealthPath -Headers @{
        'Origin'                         = $Origin
        'Access-Control-Request-Method'  = $Method
        'Access-Control-Request-Headers' = 'authorization,content-type'
    }
}

# ==========================================================================
# 1. ENVIRONMENT
# ==========================================================================
Write-Stage 'ENVIRONMENT'
$python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$apiExe = Join-Path $RepoRoot '.venv\Scripts\jarvis-api.exe'

if (-not (Test-Path $python)) { Set-Result 'Environment' $false "python not found at $python" }
elseif (-not (Test-Path $apiExe)) { Set-Result 'Environment' $false "jarvis-api not found at $apiExe" }
else {
    Write-Host "    python : $python"
    Write-Host "    server : $apiExe"

    # Fail loudly if a JARVIS_API_* override is in play -- the whole point is to
    # prove the SHIPPED DEFAULT works without operator intervention.
    $overrides = Get-ChildItem Env: | Where-Object { $_.Name -like 'JARVIS_API_*' }
    if ($overrides) {
        Set-Result 'Environment' $false ("config override present: " + (($overrides | ForEach-Object { $_.Name }) -join ', '))
    } else {
        Write-Host "    config : DEFAULT (no JARVIS_API_* override)" -ForegroundColor Green
        Set-Result 'Environment' $true
    }
}

if ($script:Results['Environment'] -ne $true) {
    Write-Host "`nRESULT: FAIL (environment)" -ForegroundColor Red
    exit 1
}

# Refuse to run if something already holds the port -- otherwise we would be
# testing an unknown process and reporting it as our own.
if (Test-PortOpen $ApiHost $Port) {
    Write-Host "`nRESULT: FAIL -- port $Port is already in use; stop that process first." -ForegroundColor Red
    exit 1
}

# ==========================================================================
# 2. START BACKEND
# ==========================================================================
Write-Stage "BACKEND (starting $apiExe, default config)"
$logOut = Join-Path $RepoRoot '.verify_core_stdout.log'
$logErr = Join-Path $RepoRoot '.verify_core_stderr.log'

$proc = Start-Process -FilePath $apiExe -WorkingDirectory $RepoRoot -PassThru `
    -RedirectStandardOutput $logOut -RedirectStandardError $logErr -WindowStyle Hidden

Write-Host "    pid    : $($proc.Id)"

$deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
$up = $false
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited) { break }
    if (Test-PortOpen $ApiHost $Port) { $up = $true; break }
    Start-Sleep -Milliseconds 400
}

if (-not $up) {
    $tail = if (Test-Path $logErr) { (Get-Content $logErr -Tail 25) -join "`n" } else { '(no stderr)' }
    Set-Result 'Backend' $false "port $Port never opened within ${StartupTimeoutSec}s. stderr:`n$tail"
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
    Write-Host "`nRESULT: FAIL (backend did not start)" -ForegroundColor Red
    exit 1
}
Write-Host "    listening on ${ApiHost}:${Port}" -ForegroundColor Green
Set-Result 'Backend' $true

try {
    # ======================================================================
    # 3. HEALTH
    # ======================================================================
    Write-Stage 'HEALTH'
    $h = Invoke-Http -Path $HealthPath
    if ($h.Status -eq 200) {
        Write-Host "    GET $HealthPath -> 200  $($h.Content)" -ForegroundColor Green
        Set-Result 'Health' $true
    } else {
        Set-Result 'Health' $false "GET $HealthPath -> $($h.Status)"
    }

    # ======================================================================
    # 4. CORS -- ALLOW MATRIX
    # ======================================================================
    Write-Stage 'CORS / allowed origins (preflight + simple request)'
    foreach ($o in $AllowedOrigins) {
        $pf = Invoke-Preflight -Origin $o
        $acao = Get-Header $pf.Headers 'Access-Control-Allow-Origin'
        if ($pf.Status -eq 200 -and $acao -eq $o) {
            Write-Host ("    OK    preflight {0,-38} -> 200, ACAO echoed exactly" -f $o) -ForegroundColor Green
        } else {
            Set-Result 'CORS' $false "preflight $o -> status=$($pf.Status) ACAO='$acao' (expected 200 + '$o')"
        }

        $sr = Invoke-Http -Path $HealthPath -Headers @{ 'Origin' = $o }
        $acao2 = Get-Header $sr.Headers 'Access-Control-Allow-Origin'
        if ($sr.Status -eq 200 -and $acao2 -eq $o) {
            Write-Host ("    OK    request   {0,-38} -> 200, ACAO echoed exactly" -f $o) -ForegroundColor Green
        } else {
            Set-Result 'CORS' $false "simple request $o -> status=$($sr.Status) ACAO='$acao2'"
        }
    }
    Set-Result 'CORS' $true   # latches to FAIL above if anything went wrong

    # ======================================================================
    # 5. CORS -- DENY MATRIX (the security half)
    # ======================================================================
    Write-Stage 'CORS / blocked origins must be rejected'
    foreach ($o in $BlockedOrigins) {
        $pf = Invoke-Preflight -Origin $o
        $acao = Get-Header $pf.Headers 'Access-Control-Allow-Origin'
        if ($pf.Status -eq 400 -and [string]::IsNullOrEmpty($acao)) {
            Write-Host ("    OK    blocked   {0,-38} -> 400, no ACAO" -f $o) -ForegroundColor Green
        } else {
            Set-Result 'CORS-Deny' $false "blocked origin $o leaked: status=$($pf.Status) ACAO='$acao'"
        }
    }
    Set-Result 'CORS-Deny' $true

    # Wildcard + credentials would be a cross-site exfiltration hole.
    Write-Stage 'CORS / credentials never paired with a wildcard'
    $pf = Invoke-Preflight -Origin 'http://tauri.localhost'
    $acao = Get-Header $pf.Headers 'Access-Control-Allow-Origin'
    $acac = Get-Header $pf.Headers 'Access-Control-Allow-Credentials'
    if ($acac -eq 'true' -and $acao -eq 'http://tauri.localhost' -and $acao -ne '*') {
        Write-Host "    OK    ACAC=true with exact ACAO (never '*')" -ForegroundColor Green
        Set-Result 'CORS-Creds' $true
    } else {
        Set-Result 'CORS-Creds' $false "ACAO='$acao' ACAC='$acac'"
    }

    # ======================================================================
    # 6. SESSION BOOTSTRAP  (POST /api/v1/sessions is intentionally open --
    #    it is what issues the Bearer token, so it cannot require one.)
    # ======================================================================
    Write-Stage 'SESSION BOOTSTRAP (from the packaged Tauri origin)'
    $tauriOrigin = 'http://tauri.localhost'
    $sess = Invoke-Http -Method 'POST' -Path '/api/v1/sessions' -Body '{}' -Headers @{ 'Origin' = $tauriOrigin }
    $token = $null
    if ($sess.Status -eq 201) {
        $acao = Get-Header $sess.Headers 'Access-Control-Allow-Origin'
        try { $token = ($sess.Content | ConvertFrom-Json).data.session_id } catch { }
        if ($token -and $acao -eq $tauriOrigin) {
            Write-Host "    POST /api/v1/sessions -> 201, session_id=$($token.Substring(0,[Math]::Min(8,$token.Length)))..., ACAO ok" -ForegroundColor Green
            Set-Result 'Session' $true
        } else {
            Set-Result 'Session' $false "201 but token='$token' ACAO='$acao'"
        }
    } else {
        Set-Result 'Session' $false "POST /api/v1/sessions -> $($sess.Status): $($sess.Content)"
    }

    # ======================================================================
    # 7. AUTHENTICATED REQUEST  (Authorization: Bearer <session_id>,
    #    validated against the live SessionManager by auth.get_current_session)
    # ======================================================================
    Write-Stage 'AUTH (Bearer session token, from the Tauri origin)'
    if (-not $token) {
        Set-Result 'Auth' $false 'skipped -- no session token was issued'
    } else {
        $authed = @{ 'Origin' = $tauriOrigin; 'Authorization' = "Bearer $token" }

        # Positive: a real protected route must accept the token.
        $ok = Invoke-Http -Path '/api/v1/homes' -Headers $authed
        if ($ok.Status -eq 200) {
            Write-Host "    GET /api/v1/homes  (Bearer)    -> 200" -ForegroundColor Green
        } else {
            Set-Result 'Auth' $false "GET /api/v1/homes with Bearer -> $($ok.Status): $($ok.Content)"
        }

        # Negative: the same route must reject a missing token, else "auth"
        # is decorative and the positive result above proves nothing.
        $no = Invoke-Http -Path '/api/v1/homes' -Headers @{ 'Origin' = $tauriOrigin }
        if ($no.Status -eq 401) {
            Write-Host "    GET /api/v1/homes  (no token)  -> 401 (correctly refused)" -ForegroundColor Green
        } else {
            Set-Result 'Auth' $false "unauthenticated GET /api/v1/homes -> $($no.Status), expected 401"
        }

        # Negative: a syntactically valid but unknown token must also fail.
        $bogus = Invoke-Http -Path '/api/v1/homes' -Headers @{ 'Origin' = $tauriOrigin; 'Authorization' = 'Bearer not-a-real-session' }
        if ($bogus.Status -eq 401) {
            Write-Host "    GET /api/v1/homes  (bad token) -> 401 (correctly refused)" -ForegroundColor Green
        } else {
            Set-Result 'Auth' $false "bogus-token GET /api/v1/homes -> $($bogus.Status), expected 401"
        }
        Set-Result 'Auth' $true
    }

    # ======================================================================
    # 8. SMART HOME / CORE API
    # ======================================================================
    Write-Stage 'SMART HOME / CORE API (authenticated, from the Tauri origin)'
    if (-not $token) {
        Set-Result 'SmartHome' $false 'skipped -- no session token was issued'
    } else {
        $authed = @{ 'Origin' = $tauriOrigin; 'Authorization' = "Bearer $token" }
        # Scenes live on the smart-LIGHTING router, not smart-home.
        foreach ($p in @('/api/v1/homes', '/api/v1/devices', '/api/v1/smart-home/zones',
                         '/api/v1/smart-home/rooms', '/api/v1/smart-lighting/scenes')) {
            $r = Invoke-Http -Path $p -Headers $authed
            $acao = Get-Header $r.Headers 'Access-Control-Allow-Origin'
            if ($r.Status -eq 200 -and $acao -eq $tauriOrigin) {
                Write-Host ("    OK    {0,-38} -> 200, ACAO ok" -f $p) -ForegroundColor Green
            } else {
                Set-Result 'SmartHome' $false "GET $p -> status=$($r.Status) ACAO='$acao'"
            }
        }
        Set-Result 'SmartHome' $true
    }

    # ======================================================================
    # 9. NO SERVER-SIDE FAILURE while we were driving it
    # ======================================================================
    Write-Stage 'SERVER LOG (no tracebacks / CORS rejections)'
    $errText = if (Test-Path $logErr) { Get-Content $logErr -Raw } else { '' }
    if ($null -eq $errText) { $errText = '' }
    $problems = @()
    if ($errText -match 'Traceback \(most recent call last\)') { $problems += 'Traceback' }
    if ($errText -match 'Disallowed CORS origin')              { $problems += 'Disallowed CORS origin' }
    if ($problems.Count -eq 0) {
        Write-Host "    clean (no traceback, no disallowed-origin rejection)" -ForegroundColor Green
        Set-Result 'ServerLog' $true
    } else {
        Set-Result 'ServerLog' $false ("server log contains: " + ($problems -join ', '))
    }

} finally {
    # ======================================================================
    # 10. STOP
    # ======================================================================
    Write-Stage 'SHUTDOWN'
    if ($NoStop) {
        Write-Host "    -NoStop given; leaving pid $($proc.Id) running on ${ApiHost}:${Port}" -ForegroundColor Yellow
    } elseif (-not $proc.HasExited) {
        # Kill the tree: uvicorn may have spawned children.
        & taskkill.exe /PID $proc.Id /T /F *> $null
        Start-Sleep -Milliseconds 500
        Write-Host "    stopped pid $($proc.Id)"
    } else {
        Write-Host "    process already exited (code $($proc.ExitCode))"
    }
}

# ==========================================================================
# SUMMARY
# ==========================================================================
Write-Host "`n$('-' * 46)"
foreach ($k in $script:Results.Keys) {
    $ok = $script:Results[$k]
    $tag = if ($ok) { 'PASS' } else { 'FAIL' }
    $col = if ($ok) { 'Green' } else { 'Red' }
    Write-Host ("{0,-20}{1}" -f $k, $tag) -ForegroundColor $col
}
Write-Host ('-' * 46)

if ($script:Failures.Count -eq 0) {
    Write-Host "RESULT: PASS" -ForegroundColor Green
    exit 0
}
Write-Host "RESULT: FAIL" -ForegroundColor Red
foreach ($f in $script:Failures) { Write-Host "  - $f" -ForegroundColor Red }
exit 1

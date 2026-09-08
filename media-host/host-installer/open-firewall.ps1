# Open inbound TCP 8766 for the Media Catalog / Media Host agent.
# If this window is not already Administrator, Windows shows a Yes/No prompt.

param(
    [int]$Port = 8766,
    [string]$RuleName = "Media Catalog Agent"
)

$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    $self = $MyInvocation.MyCommand.Path
    $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$self`" -Port $Port -RuleName `"$RuleName`""
    try {
        $p = Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $arg -Wait -PassThru
        if ($null -eq $p) { exit 2 }
        exit $p.ExitCode
    } catch {
        Write-Output "UAC_CANCELLED: $($_.Exception.Message)"
        exit 2
    }
}

$show = & netsh advfirewall firewall show rule name="$RuleName" 2>&1 | Out-String
if ($LASTEXITCODE -eq 0 -and $show -notmatch "No rules match" -and $show -match [regex]::Escape($RuleName)) {
    Write-Output "ALREADY_OPEN"
    exit 0
}

& netsh advfirewall firewall add rule name="$RuleName" dir=in action=allow protocol=TCP localport=$Port profile=any | Out-String | Write-Output
exit $LASTEXITCODE

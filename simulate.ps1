param (
    [string]$hostsfile
)

$targets = Get-Content $hostsfile
foreach ($target in $targets) {

    Start-Process powershell.exe -ArgumentList @("-NoLogo", "-NoProfil", "-file" , "simulate_check.ps1", "-target", $target)

}

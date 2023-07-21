$targets = gc .\hosts.txt
foreach ($target in $targets) {

    $uri =  'http://localhost:9220/redfish?target={0}&job=redfish/bb' -f $target
    $scriptblock = "while (`$true) {`$target;`$wait = (Get-Random -Maximum 20);Write-Host `"Waiting `$wait second ...`";Start-Sleep -Seconds `$wait; `$result = Invoke-webrequest -Uri `"$uri`"; `$result.content}"
    Start-Process powershell.exe -ArgumentList @("-NoLogo", "-NoProfil", "-Command" , $scriptblock)

}
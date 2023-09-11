param (
    $target
)

$uri = 'http://localhost:9220/redfish?target={0}&job=redfish/bb' -f $target

while ($true) {
    $wait = (Get-Random -Maximum 20)
    Write-Host "--------------------------"
    Write-Host "${target}: Waiting $wait second ..."
    Start-Sleep -Seconds $wait
    $result = Invoke-webrequest -Uri "$uri"
    $result.content
}

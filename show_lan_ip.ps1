$addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -ne '127.0.0.1' -and
        $_.AddressState -eq 'Preferred' -and
        $_.InterfaceAlias -notmatch 'Loopback|vEthernet|WSL|Bluetooth'
    } |
    Select-Object -ExpandProperty IPAddress -Unique
foreach ($address in $addresses) {
    Write-Output "  http://${address}:8501"
}

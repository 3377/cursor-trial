#region Check if running as administrator and self-elevate
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`"" -Verb RunAs -WindowStyle Hidden
    exit
}
#endregion

#region Generate and set new MachineGuid
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Cryptography" -Name "MachineGuid" -Value ([guid]::NewGuid()).ToString()
#endregion

#region Close Cursor
Stop-Process -Name "cursor" -Force -ErrorAction SilentlyContinue
#endregion
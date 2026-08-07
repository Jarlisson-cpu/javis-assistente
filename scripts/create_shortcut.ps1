$target = "$PSScriptRoot\\..\\.venv\\Scripts\\python.exe"
$shortcut = [Environment]::GetFolderPath('Desktop') + '\\JARVIS.lnk'
$wShell = New-Object -ComObject WScript.Shell
$sc = $wShell.CreateShortcut($shortcut)
$sc.TargetPath = $target
$sc.Arguments = "main.py --gui"
$sc.WorkingDirectory = "$PSScriptRoot\\.."
$iconPath = "$PSScriptRoot\\..\\resources\\jarvis.ico"
if (Test-Path $iconPath) {
    $sc.IconLocation = $iconPath
}
$sc.Save()
Write-Output "Atalho criado: $shortcut"

<#
.SYNOPSIS
  Cria atalhos do JARVIS na área de trabalho e, opcionalmente, na inicialização do Windows.

.EXAMPLE
  .\scripts\create_shortcut.ps1                 # atalho "JARVIS (voz)" na área de trabalho
  .\scripts\create_shortcut.ps1 -Modo gui       # atalho da interface gráfica
  .\scripts\create_shortcut.ps1 -IniciarComWindows   # JARVIS por voz sobe sozinho ao ligar o PC
  .\scripts\create_shortcut.ps1 -Usuario joao   # usa o perfil "joao"
#>
param(
    [ValidateSet("voz", "gui", "web", "terminal")]
    [string]$Modo = "voz",
    [string]$Usuario = "",
    [switch]$IniciarComWindows
)

$projeto = (Resolve-Path "$PSScriptRoot\..").Path
$venv = Join-Path $projeto ".venv\Scripts\pythonw.exe"
$python = if (Test-Path $venv) { $venv } else { (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source }
if (-not $python) { $python = (Get-Command python.exe).Source }

# o modo voz/terminal precisa de console para mostrar o que foi entendido
if ($Modo -in @("voz", "terminal")) { $python = $python -replace "pythonw\.exe$", "python.exe" }

$argumentos = switch ($Modo) {
    "voz" { "main.py --voice" }
    "gui" { "main.py --gui" }
    "web" { "main.py --web" }
    default { "main.py" }
}
if ($Usuario) { $argumentos += " --usuario $Usuario" }

$wShell = New-Object -ComObject WScript.Shell
$destinos = @([Environment]::GetFolderPath("Desktop"))
if ($IniciarComWindows) { $destinos += [Environment]::GetFolderPath("Startup") }

foreach ($pasta in $destinos) {
    $caminho = Join-Path $pasta "JARVIS ($Modo).lnk"
    $sc = $wShell.CreateShortcut($caminho)
    $sc.TargetPath = $python
    $sc.Arguments = $argumentos
    $sc.WorkingDirectory = $projeto
    $sc.WindowStyle = if ($Modo -eq "voz") { 7 } else { 1 }  # 7 = minimizado
    $icone = Join-Path $projeto "resources\jarvis.ico"
    if (Test-Path $icone) { $sc.IconLocation = $icone }
    $sc.Save()
    Write-Output "Atalho criado: $caminho"
}

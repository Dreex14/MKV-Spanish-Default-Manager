# Crea accesos directos con icono (escritorio y menu Inicio) para MKV Spanish Default Manager.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
$icon = Join-Path $root "assets\icon.ico"
$name = "MKV Spanish Default Manager.lnk"

if (-not (Test-Path $pythonw)) {
    Write-Host "No se encuentra el entorno (.venv). Ejecuta primero install.bat."
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$targets = @(
    [Environment]::GetFolderPath("Desktop"),
    [Environment]::GetFolderPath("Programs")
)
foreach ($dir in $targets) {
    $lnk = $shell.CreateShortcut((Join-Path $dir $name))
    $lnk.TargetPath = $pythonw
    $lnk.Arguments = '"' + (Join-Path $root "main.py") + '"'
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = $icon
    $lnk.Description = "Pone el castellano como subtitulo predeterminado en tus MKV"
    $lnk.Save()
    Write-Host "Creado: $(Join-Path $dir $name)"
}

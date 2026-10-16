param(
    [ValidateSet('Install', 'Compile', 'Upload', 'Ports', 'Monitor')]
    [string]$Action = 'Compile',
    [string]$Port,
    [string]$Board = 'esp32:esp32:esp32'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$toolsPath = Join-Path $projectRoot '.tools'
$cliPath = Join-Path $toolsPath 'arduino-cli\arduino-cli.exe'
if (-not (Test-Path -LiteralPath $cliPath)) { throw 'Run scripts/setup.ps1 first.' }
$cliConfig = Join-Path $toolsPath 'arduino-cli.yaml'
@{
    board_manager = @{ additional_urls = @('https://espressif.github.io/arduino-esp32/package_esp32_index.json') }
    directories = @{
        data = (Join-Path $toolsPath 'arduino-data')
        downloads = (Join-Path $toolsPath 'arduino-downloads')
        user = (Join-Path $toolsPath 'arduino-user')
    }
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $cliConfig -Encoding utf8
$cliArgs = @('--config-file', $cliConfig)
$sketch = Join-Path $projectRoot 'firmware\trolley'
switch ($Action) {
    'Install' {
        & $cliPath @cliArgs core update-index
        if ($LASTEXITCODE) { throw 'Arduino index download failed.' }
        & $cliPath @cliArgs core install esp32:esp32@3.3.12
    }
    'Compile' { & $cliPath @cliArgs compile --fqbn $Board --build-path (Join-Path $projectRoot 'build\esp32') $sketch }
    'Upload' {
        if (-not $Port) { throw 'Specify -Port COM3 (use -Action Ports to find it).' }
        & $cliPath @cliArgs compile --fqbn $Board --build-path (Join-Path $projectRoot 'build\esp32') $sketch
        if ($LASTEXITCODE) { throw 'Compilation failed; upload cancelled.' }
        & $cliPath @cliArgs upload --fqbn $Board --port $Port --input-dir (Join-Path $projectRoot 'build\esp32') $sketch
    }
    'Ports' { & $cliPath @cliArgs board list }
    'Monitor' {
        if (-not $Port) { throw 'Specify -Port COM3.' }
        & $cliPath @cliArgs monitor --port $Port --config baudrate=115200
    }
}
if ($LASTEXITCODE) { throw "Arduino command failed with exit code $LASTEXITCODE." }

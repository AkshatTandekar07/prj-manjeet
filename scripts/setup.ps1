$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    & uv sync --locked
    if ($LASTEXITCODE) { throw 'Python dependency installation failed.' }
    $cliDirectory = Join-Path $projectRoot '.tools\arduino-cli'
    if (-not (Test-Path -LiteralPath (Join-Path $cliDirectory 'arduino-cli.exe'))) {
        New-Item -ItemType Directory -Force -Path $cliDirectory | Out-Null
        $version = '1.5.1'
        $assetName = "arduino-cli_${version}_Windows_64bit.zip"
        $releaseUrl = "https://github.com/arduino/arduino-cli/releases/download/v$version"
        $archive = Join-Path $projectRoot '.tools\arduino-cli.zip'
        Invoke-WebRequest -Uri "$releaseUrl/$assetName" -OutFile $archive
        $checksumFile = Join-Path $projectRoot '.tools\arduino-cli-checksums.txt'
        Invoke-WebRequest -Uri "$releaseUrl/${version}-checksums.txt" -OutFile $checksumFile
        $entry = Get-Content -LiteralPath $checksumFile | Where-Object { $_ -match [regex]::Escape($assetName) }
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash
        if (-not $entry -or ($entry -split '\s+')[0] -ne $actual) { throw 'Arduino CLI checksum mismatch.' }
        Expand-Archive -LiteralPath $archive -DestinationPath $cliDirectory -Force
    }
    & (Join-Path $PSScriptRoot 'arduino.ps1') -Action Install
    if (-not (Test-Path -LiteralPath config.json)) { Copy-Item -LiteralPath config.example.json -Destination config.json }
    $secret = Join-Path $projectRoot 'firmware\trolley\secrets.h'
    if (-not (Test-Path -LiteralPath $secret)) { Copy-Item -LiteralPath firmware\trolley\secrets.example.h -Destination $secret }
    $settings = Get-Content -Raw -LiteralPath config.json | ConvertFrom-Json
    if ($settings.api_token -eq 'replace-with-the-same-random-token-as-secrets-h') {
        $settings.api_token = [guid]::NewGuid().ToString('N')
        $settings | ConvertTo-Json | Set-Content -LiteralPath config.json -Encoding utf8
    }
    $secretText = Get-Content -Raw -LiteralPath $secret
    if ($secretText.Contains('REPLACE_WITH_RANDOM_ALPHANUMERIC_TOKEN')) {
        $secretText.Replace('REPLACE_WITH_RANDOM_ALPHANUMERIC_TOKEN', $settings.api_token) | Set-Content -LiteralPath $secret -Encoding utf8
    }
    Write-Output 'Installed. Matching API tokens are configured. Enter your Wi-Fi settings in firmware/trolley/secrets.h and ESP32 address in config.json.'
}
finally { Pop-Location }

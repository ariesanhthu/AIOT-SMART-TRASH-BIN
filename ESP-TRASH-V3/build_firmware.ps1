[CmdletBinding()]
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$SketchDirectory = $PSScriptRoot
$RepositoryDirectory = Split-Path -Parent $SketchDirectory
$OutputDirectory = Join-Path $SketchDirectory "build"
$ArduinoUserDirectory = Join-Path $env:LOCALAPPDATA "ArduinoUser"
$LibraryDirectory = Join-Path $ArduinoUserDirectory "libraries\Chirale_TensorFLowLite"
$RequiredLibrary = "Chirale_TensorFLowLite@2.0.0"
$Fqbn = "esp32:esp32:esp32cam:CPUFreq=240,FlashFreq=80,FlashMode=qio,PartitionScheme=huge_app,DebugLevel=none,EraseFlash=none"

$CliCandidates = @(@(
    (Join-Path $env:ProgramFiles "Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"),
    (Get-Command arduino-cli -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) })

if ($CliCandidates.Count -eq 0) {
    throw "arduino-cli was not found. Install Arduino IDE 2.x first."
}
$ArduinoCli = @($CliCandidates)[0]

New-Item -ItemType Directory -Path $ArduinoUserDirectory -Force | Out-Null
$env:ARDUINO_DIRECTORIES_USER = $ArduinoUserDirectory

Push-Location $RepositoryDirectory
try {
    & python "ESP-TRASH-V3\verify_embedded_model.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Embedded model verification failed."
    }

    if (-not (Test-Path -LiteralPath $LibraryDirectory)) {
        & $ArduinoCli lib install $RequiredLibrary
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to install $RequiredLibrary."
        }
    }

    $Arguments = @(
        "compile",
        "--fqbn", $Fqbn,
        "--warnings", "all",
        "--output-dir", $OutputDirectory
    )
    if ($Clean) {
        $Arguments += "--clean"
    }
    $Arguments += $SketchDirectory

    & $ArduinoCli @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "ESP-TRASH-V3 firmware build failed."
    }

    $MergedBinary = Join-Path $OutputDirectory "ESP-TRASH-V3.ino.merged.bin"
    if (-not (Test-Path -LiteralPath $MergedBinary)) {
        throw "Build succeeded but merged firmware binary was not produced."
    }
    Get-FileHash -LiteralPath $MergedBinary -Algorithm SHA256
}
finally {
    Pop-Location
}

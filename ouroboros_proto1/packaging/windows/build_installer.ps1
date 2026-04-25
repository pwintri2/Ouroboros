$ErrorActionPreference = 'Stop'
$root = Join-Path $PSScriptRoot "../.."
Set-Location $root

if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    throw "cargo not found. Install Rust first (https://rustup.rs)."
}

cargo build --release

if (-not (Get-Command iscc -ErrorAction SilentlyContinue)) {
    throw "iscc not found. Install Inno Setup first."
}

$env:APP_VERSION = "0.1.0"
New-Item -ItemType Directory -Force -Path dist | Out-Null
iscc packaging\windows\OuroborosProto1.iss

Write-Host "Built: target\release\ouroboros_proto1.exe"
Write-Host "Built: dist\OuroborosProto1Setup.exe"

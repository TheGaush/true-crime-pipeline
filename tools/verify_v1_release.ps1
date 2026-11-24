$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
node schema/schema-test.js
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python3 -m pytest packages/integration_bridge/tests tests/integration -q --tb=line
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($env:ALLOW_PAID_SANDBOX -eq "1") {
  Write-Error "This runner does not place a paid call. Leave ALLOW_PAID_SANDBOX unset."
  exit 1
}
exit 0

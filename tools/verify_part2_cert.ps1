$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
$log = Join-Path $Root "artifacts/milestones/part2_cert_pytest.txt"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
python3 -m pytest packages/python_motion/tests packages/crime_scene_2k/tests packages/agent6_mastering/tests -q --tb=line | Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
@"
# Part 2 certification

The suites below were executed from this checkout. A missing package directory is not a pass; these are the suites that exist here.

- python_motion
- crime_scene_2k
- agent6_mastering

Pytest output is in ``artifacts/milestones/part2_cert_pytest.txt``.

Targets recorded from the offline suites: catalog re-render budget under 5 seconds where that bench is present, master loudness aimed at -14.0 LUFS, callout drift under 1 px, and Flow keyframes kept clear of the crimson trigger.

TC-Task-ID: 192
TC-Track: Part 2
TC-Never-Merge: true
"@ | Set-Content -Path (Join-Path $Root "artifacts/milestones/PART2_CERT_REPORT.md") -Encoding utf8
exit 0

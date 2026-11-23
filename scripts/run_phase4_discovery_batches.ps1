param(
    [switch]$RunInstagramCreators,
    [switch]$RunInstagramHashtags,
    [switch]$RunYouTubeChannels,
    [int]$RuntimeSeconds = 600,
    [int]$TargetNew = 200,
    [int]$MinMetric = 0,
    [string]$Database = ".shortslm/discovery.sqlite3"
)

$ErrorActionPreference = "Stop"
$catalogue = "outputs/phase4/catalogue"
$batches = Join-Path $catalogue "batches"
$reports = "outputs/phase4/discovery"
New-Item -ItemType Directory -Force -Path $reports | Out-Null

if (-not ($RunInstagramCreators -or $RunInstagramHashtags -or $RunYouTubeChannels)) {
    throw "Select at least one switch: -RunInstagramCreators, -RunInstagramHashtags, -RunYouTubeChannels"
}

$emptyCreators = Join-Path $catalogue "empty_creators.txt"
$emptyHashtags = Join-Path $catalogue "empty_hashtags.txt"
Set-Content -Path $emptyCreators -Value "" -Encoding utf8
Set-Content -Path $emptyHashtags -Value "" -Encoding utf8

function Invoke-ShortsLm([string[]]$Arguments, [string]$Label) {
    Write-Host ""
    Write-Host "===== $Label =====" -ForegroundColor Cyan
    & shorts-lm @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "shorts-lm failed for $Label (exit $LASTEXITCODE). Stopping batch campaign."
    }
}

if ($RunInstagramCreators) {
    Get-ChildItem $batches -Filter "instagram_creators_*.txt" | Sort-Object Name | ForEach-Object {
        $name = $_.BaseName
        Invoke-ShortsLm @(
            "discover", "graph-run", "--platform", "instagram",
            "--instagram-seeds-file", $_.FullName,
            "--instagram-hashtags-file", $emptyHashtags,
            "--max-creators", "100", "--instagram-max-hashtags", "0",
            "--max-runtime-seconds", "$RuntimeSeconds",
            "--target-new", "$TargetNew", "--min-metric", "$MinMetric",
            "--database", $Database, "--report", "$reports/$name.json"
        ) $name
        Start-Sleep -Seconds 15
    }
}

if ($RunInstagramHashtags) {
    Get-ChildItem $batches -Filter "hashtags_*.txt" | Sort-Object Name | ForEach-Object {
        $name = $_.BaseName
        Invoke-ShortsLm @(
            "discover", "graph-run", "--platform", "instagram",
            "--instagram-seeds-file", $emptyCreators,
            "--instagram-hashtags-file", $_.FullName,
            "--max-creators", "0", "--instagram-max-hashtags", "20",
            "--max-runtime-seconds", "$RuntimeSeconds",
            "--target-new", "$TargetNew", "--min-metric", "$MinMetric",
            "--database", $Database, "--report", "$reports/$name.json"
        ) $name
        Start-Sleep -Seconds 15
    }
}

if ($RunYouTubeChannels) {
    Get-ChildItem $batches -Filter "youtube_channel_ids_*.txt" | Sort-Object Name | ForEach-Object {
        $name = $_.BaseName
        Invoke-ShortsLm @(
            "discover", "graph-run", "--platform", "youtube",
            "--youtube-channel-ids-file", $_.FullName,
            "--max-creators", "100", "--max-seed-queries", "0", "--max-hashtag-queries", "0",
            "--max-runtime-seconds", "$RuntimeSeconds",
            "--target-new", "$TargetNew", "--min-metric", "$MinMetric",
            "--database", $Database, "--report", "$reports/$name.json"
        ) $name
        Start-Sleep -Seconds 15
    }
}

Write-Host "Selected Phase 4 discovery batches completed. Inspect $reports before continuing." -ForegroundColor Green

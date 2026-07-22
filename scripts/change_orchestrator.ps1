param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("explore", "propose", "validate")]
    [string]$Mode,

    [string]$Title,
    [string]$ChangeName,
    [string]$Impact = "unknown",
    [string]$Concern = "",
    [string]$Capability = "contract-review"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Section {
    param([string]$Text)
    Write-Host ""
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

function Ensure-OpenSpec {
    try {
        $null = & openspec.cmd --version
    }
    catch {
        throw "openspec.cmd is not available. Install OpenSpec CLI and ensure it is in PATH."
    }
}

function To-ImpactLevel {
    param([string]$Raw)
    $v = ($Raw | ForEach-Object { $_.Trim().ToLowerInvariant() })
    if ($v -in @("tiny", "small", "major")) {
        return $v
    }
    return "small"
}

function Get-ShouldCreateChange {
    param(
        [string]$TitleText,
        [string]$ImpactText,
        [string]$ConcernText
    )

    $text = "{0} {1} {2}" -f $TitleText, $ImpactText, $ConcernText
    $lower = $text.ToLowerInvariant()

    $triggerWords = @(
        "client", "consumer", "api", "response", "message", "error", "blocking",
        "trace", "metrics", "spec", "prompt", "check", "reason",
        "caller", "contract"
    )

    foreach ($w in $triggerWords) {
        if ($lower.Contains($w)) {
            return $true
        }
    }
    return $false
}

function Run-Explore {
    if ([string]::IsNullOrWhiteSpace($Title)) {
        throw "explore mode requires -Title."
    }

    $impactLevel = To-ImpactLevel -Raw $Impact
    $should = Get-ShouldCreateChange -TitleText $Title -ImpactText $Impact -ConcernText $Concern

    if ($should) {
        $path = "openspec"
        $reason = "Detected external behavior or review-rule change signals. OpenSpec is recommended."
        $acceptanceHint = "proposal/spec/tasks + validate"
        $shouldText = "yes"
    }
    else {
        $path = "quick-fix"
        $reason = "No explicit external behavior change detected. Quick fix can be considered first."
        $acceptanceHint = "code + test + minimal docs"
        $shouldText = "no"
    }

    Write-Section "Decision Card"
    Write-Output "should_create_change: $shouldText"
    Write-Output "impact_level: $impactLevel"
    Write-Output "reason: $reason"
    Write-Output "recommended_path: $path"
    Write-Output "acceptance_hint: $acceptanceHint"
}

function Ensure-ChangeName {
    if (-not [string]::IsNullOrWhiteSpace($ChangeName)) {
        return $ChangeName
    }
    if ([string]::IsNullOrWhiteSpace($Title)) {
        throw "propose mode requires -ChangeName or -Title."
    }

    $slug = $Title.ToLowerInvariant()
    $slug = $slug -replace "[^a-z0-9\s-]", ""
    $slug = $slug -replace "\s+", "-"
    $slug = $slug -replace "-+", "-"
    $slug = $slug.Trim('-')

    if ([string]::IsNullOrWhiteSpace($slug)) {
        return "change-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    }

    return $slug
}

function Ensure-File {
    param(
        [string]$Path,
        [string]$Content
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        $dir = Split-Path -Path $Path -Parent
        if ($dir -and -not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        Set-Content -Path $Path -Value $Content -Encoding UTF8
    }
}

function Run-Propose {
    Ensure-OpenSpec
    $name = Ensure-ChangeName

    Write-Section "Create Change"
    & openspec.cmd new change $name

    $changeDir = Join-Path -Path "openspec/changes" -ChildPath $name
    $proposalPath = Join-Path $changeDir "proposal.md"
    $tasksPath = Join-Path $changeDir "tasks.md"
    $designPath = Join-Path $changeDir "design.md"
    $specDir = Join-Path $changeDir ("specs/{0}" -f $Capability)
    $specPath = Join-Path $specDir "spec.md"

    Ensure-File -Path $proposalPath -Content @"
## Why

- TODO: describe the problem and business context.

## What Changes

- TODO: list externally visible behavior changes.

## Impact

- TODO: list impacted modules and regression scope.
"@

    Ensure-File -Path $tasksPath -Content @"
- [ ] Confirm scope and acceptance criteria
- [ ] Implement code and tests
- [ ] Sync OpenSpec and Superpowers docs
- [ ] Pass validate and regression checks
"@

    Ensure-File -Path $specPath -Content @"
## ADDED Requirements

### Requirement: TODO

System SHALL provide the target behavior.

#### Scenario: TODO

- When xxx
- Then the system SHALL yyy
"@

    Ensure-File -Path $designPath -Content @"
## Design (Optional)

Add this file only when multi-solution trade-offs or architectural changes are involved.
"@

    Write-Section "Propose Initialized"
    Write-Output "change: $name"
    Write-Output "created:"
    Write-Output "- $proposalPath"
    Write-Output "- $tasksPath"
    Write-Output "- $specPath"
    Write-Output "- $designPath (optional)"
    Write-Output "next: openspec.cmd validate $name --strict"
}

function Run-Validate {
    Ensure-OpenSpec

    if ([string]::IsNullOrWhiteSpace($ChangeName)) {
        throw "validate mode requires -ChangeName."
    }

    Write-Section "OpenSpec Validate"
    & openspec.cmd validate $ChangeName --strict

    Write-Section "Git Scope"
    & git status --short openspec docs/superpowers scripts .agents
}

switch ($Mode) {
    "explore" { Run-Explore }
    "propose" { Run-Propose }
    "validate" { Run-Validate }
    default { throw "Unknown mode: $Mode" }
}

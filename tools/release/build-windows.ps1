# Build and stage the Windows x64 release payload.
#
# Usage: tools/release/build-windows.ps1 -Rom PATH -SdlSource PATH
#            [-BuildDir DIR] [-OutDir DIR] [-Version V] [-Jobs N]
#
# Release profile: Release, native IPO on, TCP debug server and reverse-debug
# rings disabled, SDL2 and the MSVC runtime linked statically, so the payload
# is the executable plus launcher assets and needs nothing installed.
# Run from a Visual Studio 2022 x64 developer environment (the GitHub
# windows-latest image provides one).
param(
    [Parameter(Mandatory = $true)][string]$Rom,
    [Parameter(Mandatory = $true)][string]$SdlSource,
    [string]$BuildDir = 'build-release\windows',
    [string]$OutDir = 'build-release\dist\windows',
    [string]$Version = '0.1.0',
    [int]$Jobs = 8
)
$ErrorActionPreference = 'Continue'   # CMake warnings on stderr must not throw
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not [IO.Path]::IsPathRooted($BuildDir)) { $BuildDir = Join-Path $repo $BuildDir }
if (-not [IO.Path]::IsPathRooted($OutDir)) { $OutDir = Join-Path $repo $OutDir }
$Rom = (Resolve-Path -LiteralPath $Rom).Path
$SdlSource = (Resolve-Path -LiteralPath $SdlSource).Path

# Apply the engine patches without relying on Git Bash path conversion.
& python "$repo/tools/apply-engine-patches.py" --repo $repo
if ($LASTEXITCODE) { throw 'Applying engine patches failed' }

# Use whatever Visual Studio the runner has (the image may ship VS 2022 or a
# newer release): let CMake pick its default Visual Studio generator and keep
# the x64 platform explicit.
& cmake -S $repo -B $BuildDir -A x64 `
    "-DGENESIS_RECOMP_ROOT=$repo/segagenesisrecomp" `
    "-DTG2_ROM=$Rom" `
    "-DTG2_SDL_SOURCE=$SdlSource" `
    "-DTG2_BUILD_VERSION=$Version" `
    -DGEN_ENABLE_TRACE=OFF `
    -DSONIC_REVERSE_DEBUG=OFF `
    -DGENESIS_NATIVE_IPO=ON `
    -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded
if ($LASTEXITCODE) { throw 'Release configure failed' }

& cmake --build $BuildDir --config Release --target TG2Recomp --parallel $Jobs
if ($LASTEXITCODE) { throw 'Release build failed' }

$name = 'TG2Recomp-windows-x64'
$stage = Join-Path $OutDir $name
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage -Force | Out-Null
& python "$repo/tools/release/stage_payload.py" `
    --binary (Join-Path $BuildDir 'Release\TG2Recomp.exe') `
    --target-dir (Join-Path $BuildDir 'Release') `
    --dest $stage `
    --version $Version `
    --platform windows-x64 `
    --binary-name 'TG2Recomp.exe' `
    --sdl-source $SdlSource
if ($LASTEXITCODE) { throw 'Release staging failed' }

& python "$repo/tools/release/verify_artifact.py" --dir $stage `
    --require 'TG2Recomp.exe' --require 'assets' --require 'licenses' --require 'README.txt'
if ($LASTEXITCODE) { throw 'Release verification failed' }

Write-Host "Built $stage"

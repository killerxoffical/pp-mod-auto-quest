$ErrorActionPreference = "Stop"

$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-25.0.4.101-hotspot"
$env:Path = "$env:JAVA_HOME\bin;" + $env:Path

$sdk = "C:\Users\Rubel\AppData\Local\Android\Sdk"
$buildTools = "$sdk\build-tools\34.0.0"
$platform = "$sdk\platforms\android-34"

$aapt = "$buildTools\aapt.exe"
$zipalign = "$buildTools\zipalign.exe"
$androidJar = "$platform\android.jar"
$java = "$env:JAVA_HOME\bin\java.exe"
$javac = "$env:JAVA_HOME\bin\javac.exe"
$jar = "$env:JAVA_HOME\bin\jar.exe"
$d8Jar = "$buildTools\lib\d8.jar"
$apksignerJar = "$buildTools\lib\apksigner.jar"

Set-Location $PSScriptRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ">>> BUILD PROCESS STARTING: PP SERVER & PLAYQUEST TOKEN FINDER" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Ensure backup of base AndroidManifest.xml exists
if (-not (Test-Path "AndroidManifest_ppserver.xml")) {
    Copy-Item "AndroidManifest.xml" "AndroidManifest_ppserver.xml" -Force
}

# --- STEP 1: Compile base resources for Java compilation ---
Write-Host ">>> Step 1: Compiling resources with aapt..."
Copy-Item "AndroidManifest_ppserver.xml" "AndroidManifest.xml" -Force
& $aapt package -f -m -J src -M AndroidManifest.xml -S res -I $androidJar
if ($LASTEXITCODE -ne 0) { throw "aapt resource generation failed!" }

# --- STEP 2: Compiling Java sources ---
Write-Host ">>> Step 2: Compiling Java sources..."
if (Test-Path "bin") { Remove-Item "bin" -Recurse -Force }
New-Item -ItemType Directory -Path "bin" -Force | Out-Null
New-Item -ItemType Directory -Path "bin\dex" -Force | Out-Null

$javaFiles = Get-ChildItem -Path "src\com\vareon\playquest\*.java" | ForEach-Object { $_.FullName }
& $javac --release 8 -XDstringConcat=inline -d "bin" -cp "$androidJar" $javaFiles
if ($LASTEXITCODE -ne 0) { throw "javac compilation failed!" }

# --- STEP 3: Generating DEX with d8 ---
Write-Host ">>> Step 3: Generating DEX with d8..."
Push-Location "bin"
if (Test-Path "app.jar") { Remove-Item "app.jar" -Force }
& $jar cf "app.jar" "com"
$jarExit = $LASTEXITCODE
Pop-Location
if ($jarExit -ne 0) { throw "jar creation failed!" }

& $java -cp "$d8Jar" com.android.tools.r8.D8 --min-api 21 --lib "$androidJar" --output "bin\dex" "bin\app.jar"
if ($LASTEXITCODE -ne 0) { throw "d8 failed!" }

# Integrity Check: Verify classes.dex
$dexdumpOut = & "$buildTools\dexdump.exe" -f "bin\dex\classes.dex" | Select-String "class_defs_size"
Write-Host "DEX Class Count: $dexdumpOut"
$hasMainActivity = & "$buildTools\dexdump.exe" "bin\dex\classes.dex" | Select-String "Lcom/vareon/playquest/MainActivity;"
if (-not $hasMainActivity) {
    throw "CRITICAL ERROR: MainActivity is missing from classes.dex!"
}
Write-Host ">>> Verified MainActivity is present in DEX!" -ForegroundColor Green

# ==============================================================================
# --- STEP 4A: Packaging & Signing APP 1: PP_Server.apk (User Edition) ---
# ==============================================================================
Write-Host "----------------------------------------------------------" -ForegroundColor Yellow
Write-Host ">>> Step 4A: Packaging PP_Server.apk (User Edition)..." -ForegroundColor Yellow
Copy-Item "AndroidManifest_ppserver.xml" "AndroidManifest.xml" -Force

if (Test-Path "unaligned_pp.apk") { Remove-Item "unaligned_pp.apk" -Force }
& $aapt package -f -M AndroidManifest.xml -S res -A assets -I $androidJar -F unaligned_pp.apk bin\dex
if ($LASTEXITCODE -ne 0) { throw "aapt package failed for PP_Server!" }

if (Test-Path "PP_Server_aligned.apk") { Remove-Item "PP_Server_aligned.apk" -Force }
& $zipalign -f -p 4 unaligned_pp.apk PP_Server_aligned.apk
if ($LASTEXITCODE -ne 0) { throw "zipalign failed for PP_Server!" }

if (Test-Path "PP_Server.apk") { Remove-Item "PP_Server.apk" -Force }
& $java -jar "$apksignerJar" sign --ks release.keystore --ks-pass pass:ppserver123 --ks-key-alias ppserver --key-pass pass:ppserver123 --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true --v4-signing-enabled false --out PP_Server.apk PP_Server_aligned.apk
if ($LASTEXITCODE -ne 0) { throw "apksigner failed for PP_Server!" }

Write-Host ">>> Verifying PP_Server.apk signature..."
& $java -jar "$apksignerJar" verify PP_Server.apk
Write-Host ">>> SUCCESS: PP_Server.apk built and signed!" -ForegroundColor Green

# ==============================================================================
# --- STEP 4B: Packaging & Signing APP 2: PlayQuest_Token_Finder.apk (Dev Edition) ---
# ==============================================================================
Write-Host "----------------------------------------------------------" -ForegroundColor Yellow
Write-Host ">>> Step 4B: Packaging PlayQuest_Token_Finder.apk (Developer Edition)..." -ForegroundColor Yellow
Copy-Item "AndroidManifest_tokenfinder.xml" "AndroidManifest.xml" -Force

if (Test-Path "unaligned_tf.apk") { Remove-Item "unaligned_tf.apk" -Force }
& $aapt package -f -M AndroidManifest.xml -S res -A assets -I $androidJar -F unaligned_tf.apk bin\dex
if ($LASTEXITCODE -ne 0) { throw "aapt package failed for Token Finder!" }

if (Test-Path "PlayQuest_Token_Finder_aligned.apk") { Remove-Item "PlayQuest_Token_Finder_aligned.apk" -Force }
& $zipalign -f -p 4 unaligned_tf.apk PlayQuest_Token_Finder_aligned.apk
if ($LASTEXITCODE -ne 0) { throw "zipalign failed for Token Finder!" }

if (Test-Path "PlayQuest_Token_Finder.apk") { Remove-Item "PlayQuest_Token_Finder.apk" -Force }
& $java -jar "$apksignerJar" sign --ks release.keystore --ks-pass pass:ppserver123 --ks-key-alias ppserver --key-pass pass:ppserver123 --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true --v4-signing-enabled false --out PlayQuest_Token_Finder.apk PlayQuest_Token_Finder_aligned.apk
if ($LASTEXITCODE -ne 0) { throw "apksigner failed for Token Finder!" }

Write-Host ">>> Verifying PlayQuest_Token_Finder.apk signature..."
& $java -jar "$apksignerJar" verify PlayQuest_Token_Finder.apk
Write-Host ">>> SUCCESS: PlayQuest_Token_Finder.apk built and signed!" -ForegroundColor Green

# Restore original manifest
Copy-Item "AndroidManifest_ppserver.xml" "AndroidManifest.xml" -Force

# ==============================================================================
# --- STEP 5: Distribute to Root, App, and Web Portal Static Folders ---
# ==============================================================================
Write-Host "----------------------------------------------------------" -ForegroundColor Cyan
Write-Host ">>> Step 5: Distributing APKs to all locations..." -ForegroundColor Cyan

# PP Server (User)
Copy-Item "PP_Server.apk" "..\PP_Server.apk" -Force
Copy-Item "PP_Server.apk" "..\..\PP_Server.apk" -Force
Copy-Item "PP_Server.apk" "..\..\achievement_unlocker\PP_Server.apk" -Force
if (Test-Path "..\..\achievement_unlocker\static") {
    Copy-Item "PP_Server.apk" "..\..\achievement_unlocker\static\PP_Server.apk" -Force
}

# Token Finder (Dev)
Copy-Item "PlayQuest_Token_Finder.apk" "..\PlayQuest_Token_Finder.apk" -Force
Copy-Item "PlayQuest_Token_Finder.apk" "..\..\PlayQuest_Token_Finder.apk" -Force
Copy-Item "PlayQuest_Token_Finder.apk" "..\..\achievement_unlocker\PlayQuest_Token_Finder.apk" -Force
if (Test-Path "..\..\achievement_unlocker\static") {
    Copy-Item "PlayQuest_Token_Finder.apk" "..\..\achievement_unlocker\static\PlayQuest_Token_Finder.apk" -Force
}

# Also sync to achievement_unlocker/app/pp_server if that backup copy exists
if (Test-Path "..\..\achievement_unlocker\app\pp_server") {
    Copy-Item "PP_Server.apk" "..\..\achievement_unlocker\app\pp_server\PP_Server.apk" -Force
    Copy-Item "PlayQuest_Token_Finder.apk" "..\..\achievement_unlocker\app\pp_server\PlayQuest_Token_Finder.apk" -Force
}

Write-Host "==========================================================" -ForegroundColor Green
Write-Host ">>> SUCCESS: BOTH APKs SUCCESSFULLY COMPILED AND DISTRIBUTED!" -ForegroundColor Green
Write-Host ">>> [1] PP_Server.apk                 -> (User Mode: com.vareon.playquest)" -ForegroundColor Green
Write-Host ">>> [2] PlayQuest_Token_Finder.apk    -> (Dev Mode:  com.vareon.tokenfinder)" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green

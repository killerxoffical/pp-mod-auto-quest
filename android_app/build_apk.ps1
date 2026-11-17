$ErrorActionPreference = "Stop"

$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-25.0.4.101-hotspot"
$env:Path = "$env:JAVA_HOME\bin;" + $env:Path

$sdk = "C:\Users\Rubel\AppData\Local\Android\Sdk"
$buildTools = "$sdk\build-tools\34.0.0"
$platform = "$sdk\platforms\android-34"

$aapt = "$buildTools\aapt.exe"
$d8 = "$buildTools\d8.bat"
$zipalign = "$buildTools\zipalign.exe"
$apksigner = "$buildTools\apksigner.bat"
$androidJar = "$platform\android.jar"
$javac = "C:\Program Files\Eclipse Adoptium\jdk-25.0.4.101-hotspot\bin\javac.exe"

Set-Location $PSScriptRoot

Write-Host ">>> Step 1: Compiling resources with aapt..."
& $aapt package -f -m -J src -M AndroidManifest.xml -S res -I $androidJar
if ($LASTEXITCODE -ne 0) { throw "aapt resource generation failed!" }

Write-Host ">>> Step 2: Compiling Java sources..."
if (Test-Path "bin\com") { Remove-Item "bin\com" -Recurse -Force }
New-Item -ItemType Directory -Path "bin" -Force | Out-Null
New-Item -ItemType Directory -Path "bin\dex" -Force | Out-Null

$javaFiles = Get-ChildItem -Path "src\com\vareon\playquest\*.java" | ForEach-Object { $_.FullName }
& $javac -d "bin" -cp "$androidJar" -sourcepath "src" $javaFiles -source 1.8 -target 1.8
if ($LASTEXITCODE -ne 0) { throw "javac compilation failed!" }

Write-Host ">>> Step 3: Generating DEX with d8..."
$classFiles = Get-ChildItem -Path "bin\com\vareon\playquest\*.class" | ForEach-Object { $_.FullName }
& $d8 --lib "$androidJar" --output "bin\dex" $classFiles
if ($LASTEXITCODE -ne 0) { throw "d8 failed!" }

Write-Host ">>> Step 4: Packaging APK..."
if (Test-Path "unaligned.apk") { Remove-Item "unaligned.apk" -Force }
& $aapt package -f -M AndroidManifest.xml -S res -I $androidJar -F unaligned.apk bin\dex
if ($LASTEXITCODE -ne 0) { throw "aapt package failed!" }

Write-Host ">>> Step 5: Aligning APK with zipalign..."
if (Test-Path "PP_Server_aligned.apk") { Remove-Item "PP_Server_aligned.apk" -Force }
& $zipalign -f -p 4 unaligned.apk PP_Server_aligned.apk
if ($LASTEXITCODE -ne 0) { throw "zipalign failed!" }

Write-Host ">>> Step 6: Signing APK with official release certificate..."
if (Test-Path "PP_Server.apk") { Remove-Item "PP_Server.apk" -Force }
& $apksigner sign --ks release.keystore --ks-pass pass:ppserver123 --ks-key-alias ppserver --key-pass pass:ppserver123 --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true --v4-signing-enabled false --out PP_Server.apk PP_Server_aligned.apk
if ($LASTEXITCODE -ne 0) { throw "apksigner failed!" }

Write-Host ">>> Step 7: Verifying signature..."
& $apksigner verify --verbose PP_Server.apk

# Copy to root and legacy name for convenience
Copy-Item "PP_Server.apk" "..\PP_Server.apk" -Force
Copy-Item "PP_Server.apk" "..\PlayQuest_Token_Finder.apk" -Force

Write-Host ">>> SUCCESS: PP_Server.apk successfully built and signed!" -ForegroundColor Green

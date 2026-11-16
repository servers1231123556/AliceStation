$ErrorActionPreference = 'Stop'
$env:JAVA_HOME = 'F:\android\jdk'
$bt = 'F:\android\sdk\build-tools\34.0.0'
$androidJar = 'F:\android\sdk\platforms\android-34\android.jar'
$proj = 'F:\android\project'
$out = 'F:\android\out'

Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $out, "$out\gen", "$out\classes", "$out\dex" | Out-Null

Write-Host '1/7 resources'
& "$bt\aapt2.exe" compile --dir "$proj\res" -o "$out\res.zip"
if ($LASTEXITCODE -ne 0) { throw 'aapt2 compile failed' }

Write-Host '2/7 link'
& "$bt\aapt2.exe" link -o "$out\base.apk" -I $androidJar --manifest "$proj\AndroidManifest.xml" `
    "$out\res.zip" --java "$out\gen" --min-sdk-version 24 --target-sdk-version 34 `
    --version-code 1 --version-name "1.0"
if ($LASTEXITCODE -ne 0) { throw 'aapt2 link failed' }

Write-Host '3/7 javac'
$srcs = @(Get-ChildItem "$proj\src" -Recurse -Filter *.java | ForEach-Object { $_.FullName })
$srcs += @(Get-ChildItem "$out\gen" -Recurse -Filter *.java -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
& "$env:JAVA_HOME\bin\javac.exe" -source 8 -target 8 -nowarn -encoding UTF-8 -classpath $androidJar -d "$out\classes" $srcs
if ($LASTEXITCODE -ne 0) { throw 'javac failed' }

Write-Host '4/7 d8'
$classes = @(Get-ChildItem "$out\classes" -Recurse -Filter *.class | ForEach-Object { $_.FullName })
& "$bt\d8.bat" --lib $androidJar --min-api 24 --output "$out\dex" $classes
if ($LASTEXITCODE -ne 0) { throw 'd8 failed' }

Write-Host '5/7 add dex'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::Open("$out\base.apk", 'Update')
[void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, "$out\dex\classes.dex", 'classes.dex')
$zip.Dispose()

Write-Host '6/7 zipalign'
& "$bt\zipalign.exe" -f 4 "$out\base.apk" "$out\aligned.apk"
if ($LASTEXITCODE -ne 0) { throw 'zipalign failed' }

Write-Host '7/7 sign'
if (-not (Test-Path "F:\android\app.jks")) {
    & "$env:JAVA_HOME\bin\keytool.exe" -genkeypair -keystore "F:\android\app.jks" -alias app `
        -keyalg RSA -keysize 2048 -validity 10000 -storepass android -keypass android `
        -dname "CN=Alice Remote, O=Home, C=RU" | Out-Null
}
& "$bt\apksigner.bat" sign --ks "F:\android\app.jks" --ks-pass pass:android --key-pass pass:android `
    --out "$out\AliceHome.apk" "$out\aligned.apk"
if ($LASTEXITCODE -ne 0) { throw 'apksigner failed' }

& "$bt\apksigner.bat" verify --print-certs "$out\AliceHome.apk" | Select-Object -First 4
Write-Host ('OK -> ' + "$out\AliceHome.apk" + '  ' + [math]::Round((Get-Item "$out\AliceHome.apk").Length / 1KB, 1) + ' KB')




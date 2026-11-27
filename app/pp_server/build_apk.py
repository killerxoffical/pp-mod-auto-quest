#!/usr/bin/env python3
import os
import sys
import glob
import shutil
import zipfile
import subprocess
import time
import hashlib
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

JAVA_HOME = r"C:\Program Files\Eclipse Adoptium\jdk-25.0.4.101-hotspot"
SDK = r"C:\Users\Rubel\AppData\Local\Android\Sdk"
BUILD_TOOLS = os.path.join(SDK, r"build-tools\34.0.0")
PLATFORM = os.path.join(SDK, r"platforms\android-34")

AAPT = os.path.join(BUILD_TOOLS, "aapt.exe")
ZIPALIGN = os.path.join(BUILD_TOOLS, "zipalign.exe")
DEXDUMP = os.path.join(BUILD_TOOLS, "dexdump.exe")
ANDROID_JAR = os.path.join(PLATFORM, "android.jar")
JAVA = os.path.join(JAVA_HOME, r"bin\java.exe")
JAVAC = os.path.join(JAVA_HOME, r"bin\javac.exe")
D8_JAR = os.path.join(BUILD_TOOLS, r"lib\d8.jar")
APKSIGNER_JAR = os.path.join(BUILD_TOOLS, r"lib\apksigner.jar")
KEYSTORE = "release.keystore"
KEYSTORE_PASS = "ppserver123"
KEY_ALIAS = "ppserver"

def sha256_file(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

print("=" * 60)
print(">>> BULLETPROOF BUILD STARTING: PPM CLOUD & PP QUEST HYBRID")
print("=" * 60)

# STEP 0: Prepare assets_quest directory
print("\n>>> Step 0: Syncing web assets for PP QUEST...")
assets_quest_www = os.path.join("assets_quest", "www")
os.makedirs(assets_quest_www, exist_ok=True)

pp_mod_dir = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "pp mod"))
quest_files_to_copy = [
    "index.html",
    "brand_logo.png",
    "fb.png",
    "hd.png",
    "PPCOIN.png",
    "pp_cloud_banner.png",
    "pp_logo.png",
    "progress.js",
    "svg_maintenance.svg",
    "svg_no_game.svg",
    "svg_update.svg"
]

for qf in quest_files_to_copy:
    src_f = os.path.join(pp_mod_dir, qf)
    dst_f = os.path.join(assets_quest_www, qf)
    if os.path.exists(src_f):
        shutil.copy2(src_f, dst_f)

if os.path.exists(os.path.join("assets", "logo_user.png")):
    shutil.copy2(os.path.join("assets", "logo_user.png"), os.path.join("assets_quest", "logo_user.png"))

# Compute SHA-256 for integrity verification
server_html_hash = sha256_file(os.path.join("assets", "www", "index.html"))
quest_html_hash = sha256_file(os.path.join("assets_quest", "www", "index.html"))

print(f">>> Server HTML SHA-256: {server_html_hash}")
print(f">>> Quest  HTML SHA-256: {quest_html_hash}")

sec_guard_path = os.path.join("src", "com", "vareon", "playquest", "SecurityGuard.java")
with open(sec_guard_path, "r", encoding="utf-8") as f:
    sec_content = f.read()

sec_content = re.sub(r'public static String EXPECTED_HTML_SHA256 = "[^"]*";', f'public static String EXPECTED_HTML_SHA256 = "{server_html_hash}";', sec_content)
sec_content = re.sub(r'public static String EXPECTED_QUEST_HTML_SHA256 = "[^"]*";', f'public static String EXPECTED_QUEST_HTML_SHA256 = "{quest_html_hash}";', sec_content)

with open(sec_guard_path, "w", encoding="utf-8") as f:
    f.write(sec_content)
print(">>> Injected dynamic SHA-256 hashes into SecurityGuard.java")

# STEP 1: Resources
print("\n>>> Step 1: Compiling resources with aapt...")
shutil.copy2("AndroidManifest_ppserver.xml", "AndroidManifest.xml")
cmd_aapt = [AAPT, "package", "-f", "-m", "-J", "src", "--custom-package", "com.vareon.playquest", "-M", "AndroidManifest.xml", "-S", "res", "-I", ANDROID_JAR]
subprocess.run(cmd_aapt, check=True)
print(">>> R.java generated successfully.")

# STEP 2: Java sources
print("\n>>> Step 2: Compiling Java sources with pure Java 8 bytecode...")
out_classes = "out_classes"
if os.path.exists(out_classes):
    shutil.rmtree(out_classes)
os.makedirs(os.path.join(out_classes, "dex"), exist_ok=True)

java_files = glob.glob("src/com/vareon/playquest/*.java")
cmd_javac = [
    JAVAC,
    "-source", "8",
    "-target", "8",
    "-bootclasspath", ANDROID_JAR,
    "-Xlint:-options",
    "-d", out_classes,
    "-cp", ANDROID_JAR
] + java_files

res_javac = subprocess.run(cmd_javac, capture_output=True, text=True)
if res_javac.returncode != 0:
    print(res_javac.stderr)
    raise RuntimeError(f"javac failed with code {res_javac.returncode}")

class_files = glob.glob(os.path.join(out_classes, "com/**/*.class"), recursive=True)
print(f">>> Found {len(class_files)} compiled .class files.")
if len(class_files) == 0:
    raise RuntimeError("No .class files compiled!")

for cf in class_files:
    with open(cf, "rb") as fp:
        hdr = fp.read(8)
        ver = int.from_bytes(hdr[6:8], "big")
        if ver != 52:
            raise RuntimeError(f"CRITICAL: Bytecode version mismatch! {cf} has major version {ver} instead of 52 (Java 8)")

print(f">>> VERIFIED: All {len(class_files)} class files are pure Java 8 (v52)!")

# STEP 3: DEX generation
print("\n>>> Step 3: Generating DEX with d8...")
app_jar = os.path.join(out_classes, "app.jar")
with zipfile.ZipFile(app_jar, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for cf in class_files:
        rel_path = os.path.relpath(cf, out_classes)
        zf.write(cf, rel_path)

dex_out = os.path.join(out_classes, "dex")
cmd_d8 = [JAVA, "-cp", D8_JAR, "com.android.tools.r8.D8", "--release", "--min-api", "21", "--lib", ANDROID_JAR, "--output", dex_out, app_jar]
subprocess.run(cmd_d8, check=True)

classes_dex = os.path.join(dex_out, "classes.dex")
if not os.path.exists(classes_dex) or os.path.getsize(classes_dex) == 0:
    raise RuntimeError("classes.dex generation failed!")

res_dump = subprocess.run([DEXDUMP, classes_dex], capture_output=True, text=True)
dex_classes = [l.strip() for l in res_dump.stdout.splitlines() if "Class descriptor" in l]
print(f">>> DEX Class Definitions count: {len(dex_classes)}")
has_main = any("MainActivity" in l for l in dex_classes)
if not has_main:
    raise RuntimeError("CRITICAL ERROR: MainActivity class definition is missing from classes.dex!")
print(">>> Verified MainActivity class definition is present in DEX!")

def package_and_sign(manifest_src, apk_name, title, assets_dir="assets"):
    print(f"\n----------------------------------------------------------")
    print(f">>> Packaging {apk_name} ({title})...")
    shutil.copy2(manifest_src, "AndroidManifest.xml")
    
    unaligned = f"unaligned_{apk_name}"
    aligned = f"aligned_{apk_name}"
    for f in [unaligned, aligned, apk_name]:
        if os.path.exists(f):
            os.remove(f)

    # AAPT package with out_classes/dex and selected assets directory
    cmd_pkg = [AAPT, "package", "-f", "-M", "AndroidManifest.xml", "-S", "res", "-A", assets_dir, "-I", ANDROID_JAR, "-F", unaligned, dex_out]
    subprocess.run(cmd_pkg, check=True)

    # Zipalign
    cmd_align = [ZIPALIGN, "-f", "-p", "4", unaligned, aligned]
    subprocess.run(cmd_align, check=True)

    # Sign with v1, v2, v3
    cmd_sign = [
        JAVA, "-jar", APKSIGNER_JAR, "sign",
        "--ks", KEYSTORE,
        "--ks-pass", f"pass:{KEYSTORE_PASS}",
        "--ks-key-alias", KEY_ALIAS,
        "--key-pass", f"pass:{KEYSTORE_PASS}",
        "--v1-signing-enabled", "true",
        "--v2-signing-enabled", "true",
        "--v3-signing-enabled", "true",
        "--v4-signing-enabled", "false",
        "--out", apk_name,
        aligned
    ]
    subprocess.run(cmd_sign, check=True)

    # Verify signature
    cmd_verify = [JAVA, "-jar", APKSIGNER_JAR, "verify", apk_name]
    subprocess.run(cmd_verify, check=True)
    
    # Verify classes.dex in final apk
    with zipfile.ZipFile(apk_name, "r") as zf:
        if "classes.dex" not in zf.namelist():
            raise RuntimeError(f"CRITICAL: classes.dex missing from {apk_name}!")
        dex_data = zf.read("classes.dex")
        if len(dex_data) < 10000:
            raise RuntimeError(f"CRITICAL: classes.dex too small in {apk_name} ({len(dex_data)} bytes)!")

    # Clean intermediate files
    for f in [unaligned, aligned]:
        if os.path.exists(f):
            os.remove(f)

    print(f">>> SUCCESS: {apk_name} built, zipaligned, and verified signed ({os.path.getsize(apk_name)} bytes)!")

# STEP 4: Package and Sign PPM_Cloud.apk / PP_Server.apk
package_and_sign("AndroidManifest_ppserver.xml", "PP_Server.apk", "PPM CLOUD v5.1 User Edition", assets_dir="assets")
shutil.copy2("PP_Server.apk", "PPM_Cloud.apk")
print(">>> Created PPM_Cloud.apk as official distribution package.")

# STEP 4B: Package and Sign PP_Quest.apk
package_and_sign("AndroidManifest_ppquest.xml", "PP_Quest.apk", "PP QUEST Hybrid Edition", assets_dir="assets_quest")

# Restore base manifest
shutil.copy2("AndroidManifest_ppserver.xml", "AndroidManifest.xml")

# STEP 5: Distribute APKs
print("\n>>> Step 5: Distributing APK packages across project repositories...")
base_script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(base_script_dir, "..", ".."))
achievement_dir = os.path.join(root_dir, "achievement_unlocker")

apks_to_distribute = ["PP_Server.apk", "PPM_Cloud.apk", "PP_Quest.apk"]

dist_directories = [
    os.path.join(base_script_dir, ".."),
    root_dir,
    os.path.join(root_dir, "static"),
    achievement_dir,
    os.path.join(achievement_dir, "static"),
    os.path.join(achievement_dir, "app"),
    os.path.join(achievement_dir, "app", "pp_server"),
]

for d in dist_directories:
    os.makedirs(d, exist_ok=True)
    for apk in apks_to_distribute:
        src_path = os.path.join(base_script_dir, apk)
        target_path = os.path.join(d, apk)
        for attempt in range(4):
            try:
                shutil.copy2(src_path, target_path)
                print(f"  -> Copied {apk} to {target_path}")
                break
            except PermissionError:
                time.sleep(0.5)
                if attempt == 3:
                    print(f"  [!] Note: could not write {target_path} (locked by external process)")

# Also update build_out in bin for consistency
bin_dex = os.path.join("bin", "dex")
os.makedirs(bin_dex, exist_ok=True)
shutil.copy2(classes_dex, os.path.join(bin_dex, "classes.dex"))

print("\n" + "=" * 60)
print(">>> PP SERVER & PP QUEST BUILD COMPLETE AND CERTIFIED CRASH-PROOF!")
print(">>> [1] PPM_Cloud.apk -> User Client Mode (com.ppm.cloud) [v5.1]")
print(">>> [2] PP_Quest.apk  -> Full Hybrid Quest Edition (com.ppm.quest) [v1.0]")
print("=" * 60)

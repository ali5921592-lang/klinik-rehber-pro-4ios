#!/usr/bin/env python3
"""
patch-podfile.py
------------------
`npx cap add ios` calistiktan hemen sonra, `npx cap sync ios` (pod install'i
tetikleyen adim) calismadan ONCE calistirilmalidir.

SORUN 1: Manuel imzalama (CODE_SIGN_STYLE=Manual + PROVISIONING_PROFILE_SPECIFIER)
xcodebuild komut satirindan verildiginde, bu ayar workspace'teki TUM hedeflere
uygulanir - App hedefine degil, ayni zamanda CocoaPods kutuphane/framework
hedeflerine de (CapacitorLocalNotifications, CapacitorStatusBar, vb.).
Ancak framework/kutuphane hedefleri provisioning profile KULLANAMAZ, bu da
"X does not support provisioning profiles" hatasina ve arsivin basarisiz
olmasina yol acar.

COZUM 1: Podfile'a bir `post_install` kancasi ekleyerek, TUM Pods hedeflerinde
kod imzalamayi tamamen devre disi birakiyoruz (CODE_SIGNING_ALLOWED=NO).
Bu, sadece kutuphaneler icindir - asil App hedefinin imzalanmasini ETKILEMEZ,
o hala xcodebuild komut satirindaki PROVISIONING_PROFILE_SPECIFIER ile
duzgun sekilde imzalanir.

SORUN 2: @capacitor-firebase/analytics gibi Firebase tabanli Capacitor
eklentileri Swift ile yazilmistir ve `import FirebaseCore` icerir. CocoaPods
varsayilan olarak statik kutuphaneler kurar; statik kutuphaneler arasinda
Swift modul haritasi paylasimi calismaz, bu da "no such module 'FirebaseCore'"
derleme hatasina yol acar.

COZUM 2: Podfile'in basina `use_frameworks!` satirini ekliyoruz. Bu, CocoaPods'a
tum pod'lari dinamik framework olarak kurmasini soyler, boylece Swift modulleri
birbirleri arasinda dogru sekilde import edilebilir. Bu, Firebase'in resmi
kurulum dokumantasyonunda da Swift/Capacitor projeleri icin standart olarak
onerilen bir ayardir.

Bu duzeltmeler, Capacitor/CocoaPods + Firebase projelerinde standart ve
yaygin olarak onerilen duzeltmelerdir.
"""
import os
import re
import sys

PODFILE_PATH = os.path.join("ios", "App", "Podfile")

POST_INSTALL_SNIPPET = """    installer.pods_project.targets.each do |target|
      target.build_configurations.each do |config|
        config.build_settings['CODE_SIGNING_ALLOWED'] = 'NO'
        config.build_settings['CODE_SIGNING_REQUIRED'] = 'NO'
      end
    end
"""


def log(msg):
    print(f"[patch-podfile] {msg}")


def ensure_use_frameworks(content):
    """Podfile'da AKTIF (yorum satiri olmayan) 'use_frameworks!' yoksa,
    platform satirindan hemen sonra ekler. Onceki surum, basinda '#' olan
    yorum satirlarini da 'mevcut' sayan hatali bir regex kullaniyordu -
    bu yuzden Capacitor'in varsayilan Podfile'indaki yorumlu ornek satiri
    ('# use_frameworks!') gercek/aktif bir satir sanip atlıyordu. Simdi
    yorum satirlarini haric tutuyoruz."""
    active_pattern = re.compile(r"^[ \t]*use_frameworks!", re.MULTILINE)
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("use_frameworks!"):
            log("'use_frameworks!' zaten aktif halde mevcut, tekrar eklenmeyecek.")
            return content, False

    # Yorum satiri halindeki '# use_frameworks!' varsa, o satiri aktif hale getir
    commented_pattern = re.compile(r"^([ \t]*)#\s*use_frameworks!\s*$", re.MULTILINE)
    match = commented_pattern.search(content)
    if match:
        new_content = commented_pattern.sub(r"\1use_frameworks!", content, count=1)
        log("Yorum satirindaki '# use_frameworks!' etkinlestirildi (yorum isareti kaldirildi).")
        return new_content, True

    platform_pattern = re.compile(r"(platform\s+:ios[^\n]*\n)")
    match = platform_pattern.search(content)
    if match:
        insert_pos = match.end()
        new_content = content[:insert_pos] + "use_frameworks!\n" + content[insert_pos:]
        log("'use_frameworks!' satiri 'platform :ios' satirindan hemen sonra eklendi.")
        return new_content, True

    # platform satiri bulunamazsa, dosyanin en basina ekle
    new_content = "use_frameworks!\n" + content
    log("'platform :ios' satiri bulunamadi; 'use_frameworks!' dosyanin basina eklendi.")
    return new_content, True


def main():
    if not os.path.exists(PODFILE_PATH):
        log(f"HATA: {PODFILE_PATH} bulunamadi. 'npx cap add ios' calistirildi mi?")
        return 1

    with open(PODFILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    changed = False

    content, fw_changed = ensure_use_frameworks(content)
    changed = changed or fw_changed

    if "CODE_SIGNING_ALLOWED" in content:
        log("Podfile zaten kod imzalama yamasina sahip, tekrar eklenmeyecek.")
    else:
        post_install_pattern = re.compile(r"(post_install do \|installer\|\s*\n)")
        match = post_install_pattern.search(content)

        if match:
            insert_pos = match.end()
            content = content[:insert_pos] + POST_INSTALL_SNIPPET + content[insert_pos:]
            log("Mevcut 'post_install' bloguna kod imzalama devre disi birakma satirlari eklendi.")
        else:
            content = content.rstrip() + "\n\npost_install do |installer|\n" + POST_INSTALL_SNIPPET + "end\n"
            log("Podfile'da 'post_install' blogu bulunamadi, yeni bir tane eklendi.")
        changed = True

    if changed:
        with open(PODFILE_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        log(f"{PODFILE_PATH} basariyla yamalandi.")
    else:
        log(f"{PODFILE_PATH} icin yapilacak degisiklik yok.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

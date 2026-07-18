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
import shutil
import sys

PODFILE_PATH = os.path.join("ios", "App", "Podfile")

POST_INSTALL_SNIPPET = """    installer.pods_project.targets.each do |target|
      target.build_configurations.each do |config|
        config.build_settings['CODE_SIGNING_ALLOWED'] = 'NO'
        config.build_settings['CODE_SIGNING_REQUIRED'] = 'NO'
        config.build_settings['CODE_SIGN_IDENTITY'] = ''
        config.build_settings['EXPANDED_CODE_SIGN_IDENTITY'] = '-'
        config.build_settings['CODE_SIGN_STYLE'] = 'Automatic'
        config.build_settings['DEVELOPMENT_TEAM'] = ''
        config.build_settings['PROVISIONING_PROFILE'] = ''
        config.build_settings['PROVISIONING_PROFILE_SPECIFIER'] = ''
      end
    end
"""


PODS_DIR = os.path.join("ios", "App", "Pods")
PODFILE_LOCK_PATH = os.path.join("ios", "App", "Podfile.lock")


def log(msg):
    print(f"[patch-podfile] {msg}")


def clean_stale_lock_and_pods():
    """Repoya daha once commit edilmis eski bir ios/App klasoru varsa,
    icindeki Podfile.lock eski/uyumsuz surumleri (orn. GoogleUserMessagingPlatform
    3.1.0) kilitli tutabilir. 'npx cap add ios' mevcut klasoru silmeden calisirsa,
    bu eski kilit dosyasi pod install'da 'could not find compatible versions'
    hatasina yol acar. Podfile'i degistirmeden ONCE bu eski dosyalari temizleyerek
    CocoaPods'un yeni kisitlamalara (surum sabitlemeleri) gore sifirdan
    cozumleme yapmasini sagliyoruz."""
    removed_any = False
    if os.path.exists(PODFILE_LOCK_PATH):
        os.remove(PODFILE_LOCK_PATH)
        log(f"Eski {PODFILE_LOCK_PATH} silindi (guncel Podfile kisitlamalariyla uyumsuz olabilirdi).")
        removed_any = True
    if os.path.isdir(PODS_DIR):
        shutil.rmtree(PODS_DIR)
        log(f"Eski {PODS_DIR} klasoru silindi.")
        removed_any = True
    if not removed_any:
        log("Temizlenecek eski Podfile.lock veya Pods klasoru bulunamadi.")


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


def ensure_firebase_analytics_pod(content):
    """@capacitor-firebase/analytics kullanan projelerde 'no such module FirebaseCore'
    hatasinin GERCEK ve BELGELENMIS sebebi: `npx cap sync` sadece Podfile'daki
    `capacitor_pods` fonksiyonunu/bolumunu yeniden olusturur, ancak Firebase
    Analytics'in kendi alt-spec pod satirini asla otomatik eklemez. Bu satir
    'target 'App' do ... end' blogunun icine elle eklenmelidir. Kaynak:
    capawesome-team/capacitor-firebase resmi deposu, issue #622 (proje
    bakimcisinin dogrulanmis cevabi).
    Bu fonksiyon, sadece proje node_modules altinda @capacitor-firebase/analytics
    varsa (yani bu eklenti gercekten kullaniliyorsa) satiri ekler."""
    plugin_installed = os.path.exists(
        os.path.join("node_modules", "@capacitor-firebase", "analytics")
    )
    if not plugin_installed:
        log("@capacitor-firebase/analytics kurulu degil, bu adim atlanacak.")
        return content, False

    firebase_pod_line = "pod 'CapacitorFirebaseAnalytics/Analytics', :path => '../../node_modules/@capacitor-firebase/analytics'"

    if firebase_pod_line in content:
        log("Firebase Analytics pod satiri zaten mevcut, tekrar eklenmeyecek.")
        return content, False

    target_app_pattern = re.compile(r"(target\s+['\"]App['\"]\s+do\s*\n(?:[ \t]*capacitor_pods\s*\n)?)")
    match = target_app_pattern.search(content)
    if match:
        insert_pos = match.end()
        new_content = content[:insert_pos] + "  " + firebase_pod_line + "\n" + content[insert_pos:]
        log("Firebase Analytics pod satiri 'target App do' blogunun icine eklendi.")
        return new_content, True

    log("UYARI: 'target App do' blogu bulunamadi, Firebase Analytics pod satiri eklenemedi.")
    return content, False


def ensure_ump_version_pin(content):
    """@capacitor-community/admob kullanan projelerde, GoogleUserMessagingPlatform
    (UMP SDK) 3.0.0 surumunde TUM sinif/ozellik isimleri degistirildi (UMP onekleri
    kaldirildi: UMPConsentInformation -> ConsentInformation, sharedInstance -> shared,
    vb. - kaynak: Google'in resmi surum notlari, 24 Mart 2025). @capacitor-community/
    admob paketinin icindeki ConsentExecutor.swift dosyasi hala ESKI (UMP onekli)
    isimlendirmeyi kullaniyor, bu da 'has been renamed to' derleme hatalarina yol
    aciyor. Podfile'da GoogleUserMessagingPlatform surumunu 3.0'in altina sabitleyerek
    CocoaPods'un eski, uyumlu surumu kurmasini sagliyoruz."""
    admob_installed = os.path.exists(
        os.path.join("node_modules", "@capacitor-community", "admob")
    )
    if not admob_installed:
        log("@capacitor-community/admob kurulu degil, bu adim atlanacak.")
        return content, False

    ump_pod_line = "pod 'GoogleUserMessagingPlatform', '< 3.0'"

    if "GoogleUserMessagingPlatform" in content:
        log("GoogleUserMessagingPlatform icin zaten bir Podfile satiri var, tekrar eklenmeyecek.")
        return content, False

    target_app_pattern = re.compile(r"(target\s+['\"]App['\"]\s+do\s*\n(?:[ \t]*capacitor_pods\s*\n)?(?:[ \t]*pod\s+'CapacitorFirebaseAnalytics[^\n]*\n)?)")
    match = target_app_pattern.search(content)
    if match:
        insert_pos = match.end()
        new_content = content[:insert_pos] + "  " + ump_pod_line + "\n" + content[insert_pos:]
        log("GoogleUserMessagingPlatform '< 3.0' surumune sabitlendi (target App do blogu icine eklendi).")
        return new_content, True

    log("UYARI: 'target App do' blogu bulunamadi, GoogleUserMessagingPlatform satiri eklenemedi.")
    return content, False


def main():
    if not os.path.exists(PODFILE_PATH):
        log(f"HATA: {PODFILE_PATH} bulunamadi. 'npx cap add ios' calistirildi mi?")
        return 1

    clean_stale_lock_and_pods()

    with open(PODFILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    changed = False

    content, fw_changed = ensure_use_frameworks(content)
    changed = changed or fw_changed

    content, fb_changed = ensure_firebase_analytics_pod(content)
    changed = changed or fb_changed

    content, ump_changed = ensure_ump_version_pin(content)
    changed = changed or ump_changed

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

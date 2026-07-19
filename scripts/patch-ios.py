#!/usr/bin/env python3
"""
patch-ios.py
-------------
Capacitor `npx cap add ios` ile tazece uretilen native iOS projesini,
GitHub Actions icinde asagidaki sekilde otomatik duzenler:

  1) Privacy Manifest dosyasini (PrivacyInfo.xcprivacy) projeye ekler
     (Apple'in 2024+ App Store gereksinimi).
  2) ITSAppUsesNonExemptEncryption = false ekler (uygulama ozel sifreleme
     kullanmadigi icin - yalnizca standart HTTPS/local dosya erisimi).
  3) iPhone ve iPad icin uygun ekran yonu (orientation) destegini ayarlar.
  4) Gereksiz izin/aciklama anahtarlarinin (kamera, konum, mikrofon vb.)
     Info.plist'te bulunmadigini dogrular (varsayilan Capacitor sablonu
     zaten bunlari icermez; uygulama hicbirini kullanmaz).

NOT: Bundle Identifier, versiyon (CFBundleShortVersionString) ve build
numarasi (CFBundleVersion) bu script yerine dogrudan `xcodebuild` build
settings override'lari (PRODUCT_BUNDLE_IDENTIFIER, MARKETING_VERSION,
CURRENT_PROJECT_VERSION) ile GitHub Actions workflow'unda ayarlanir.
Bu, Xcode proje dosyasini (.pbxproj) elle/regex ile duzenlemekten çok
daha guvenli ve standart bir yontemdir.

Bu script yalnizca CI/CD tarafindan native ios/ klasoru uzerinde calisir;
projenin www/ icindeki asil web uygulama kodunu HICBIR sekilde etkilemez.
"""
import os
import plistlib
import shutil
import sys

IOS_APP_DIR = os.path.join("ios", "App", "App")
INFO_PLIST_PATH = os.path.join(IOS_APP_DIR, "Info.plist")
PRIVACY_MANIFEST_SRC = os.path.join("ios-privacy", "PrivacyInfo.xcprivacy")
PRIVACY_MANIFEST_DST = os.path.join(IOS_APP_DIR, "PrivacyInfo.xcprivacy")
GOOGLE_SERVICE_SRC = os.path.join("ios-config", "GoogleService-Info.plist")
GOOGLE_SERVICE_DST = os.path.join(IOS_APP_DIR, "GoogleService-Info.plist")


def log(msg):
    print(f"[patch-ios] {msg}")


def copy_google_service_info():
    """@capacitor-firebase/analytics kullanan projelerde, FirebaseApp.configure()
    calisma zamaninda ios/App/App/GoogleService-Info.plist dosyasini bulamazsa
    uygulama ACILISTA COKER (NSException: could not find a valid
    GoogleService-Info.plist). 'npx cap add ios' her calistirmada ios/ klasorunu
    sifirdan urettigi icin bu dosya reponun disinda (repo kokunde ios-config/
    klasorunde) saklanir ve her CI calistirmasinda buraya kopyalanir."""
    if not os.path.exists(GOOGLE_SERVICE_SRC):
        log(f"UYARI: {GOOGLE_SERVICE_SRC} bulunamadi. Firebase Analytics kullaniliyorsa "
            f"uygulama acilista cokecektir! Firebase Console'dan indirilen "
            f"GoogleService-Info.plist dosyasini repoya '{GOOGLE_SERVICE_SRC}' "
            f"yoluna eklemeniz gerekiyor.")
        return
    if not os.path.isdir(IOS_APP_DIR):
        log(f"HATA: {IOS_APP_DIR} bulunamadi. 'npx cap add ios' calistirildi mi?")
        return
    shutil.copyfile(GOOGLE_SERVICE_SRC, GOOGLE_SERVICE_DST)
    log(f"GoogleService-Info.plist kopyalandi: {GOOGLE_SERVICE_DST}")


def copy_privacy_manifest():
    if not os.path.exists(PRIVACY_MANIFEST_SRC):
        log(f"UYARI: {PRIVACY_MANIFEST_SRC} bulunamadi, Privacy Manifest eklenemedi.")
        return
    if not os.path.isdir(IOS_APP_DIR):
        log(f"HATA: {IOS_APP_DIR} bulunamadi. 'npx cap add ios' calistirildi mi?")
        return
    shutil.copyfile(PRIVACY_MANIFEST_SRC, PRIVACY_MANIFEST_DST)
    log(f"Privacy Manifest kopyalandi: {PRIVACY_MANIFEST_DST}")
    log("NOT: Bu dosyanin Xcode projesine (.pbxproj) gercek bir referans olarak "
        "eklenmesi ayri bir adimda (scripts/add_privacy_manifest_to_xcodeproj.rb) "
        "yapilir; sadece diske kopyalamak Xcode'un onu .ipa icine paketlemesi "
        "icin yeterli degildir.")


def patch_info_plist():
    if not os.path.exists(INFO_PLIST_PATH):
        log(f"HATA: {INFO_PLIST_PATH} bulunamadi.")
        return
    with open(INFO_PLIST_PATH, "rb") as f:
        plist = plistlib.load(f)

    # Sifreleme uyumluluk beyani: ozel/ek sifreleme kullanilmiyor.
    plist["ITSAppUsesNonExemptEncryption"] = False

    # iPhone: dikey (portre) kullanim odakli bir referans/klinik uygulamasi.
    plist["UISupportedInterfaceOrientations"] = [
        "UIInterfaceOrientationPortrait",
        "UIInterfaceOrientationPortraitUpsideDown",
    ]
    # iPad: App Store inceleme kurallarina uygun olarak birden fazla yon desteklenir.
    plist["UISupportedInterfaceOrientations~ipad"] = [
        "UIInterfaceOrientationPortrait",
        "UIInterfaceOrientationPortraitUpsideDown",
        "UIInterfaceOrientationLandscapeLeft",
        "UIInterfaceOrientationLandscapeRight",
    ]

    # iPad'de tam ekran zorunlulugu KALDIRILIR (Split View / Slide Over destegi icin).
    plist.pop("UIRequiresFullScreen", None)

    with open(INFO_PLIST_PATH, "wb") as f:
        plistlib.dump(plist, f)
    log("Info.plist guncellendi: ITSAppUsesNonExemptEncryption=false, "
        "iPhone/iPad ekran yonleri, UIRequiresFullScreen kaldirildi.")


def verify_no_unnecessary_permissions():
    if not os.path.exists(INFO_PLIST_PATH):
        return
    with open(INFO_PLIST_PATH, "rb") as f:
        plist = plistlib.load(f)
    permission_keys = [k for k in plist.keys() if k.startswith("NS") and k.endswith("UsageDescription")]
    if permission_keys:
        log(f"UYARI: Info.plist'te izin aciklama anahtarlari bulundu: {permission_keys}. "
            "Uygulama bu izinleri kullanmiyorsa bu anahtarlar kaldirilmalidir.")
    else:
        log("Dogrulandi: Info.plist'te gereksiz izin aciklamasi (kamera/konum/mikrofon vb.) yok.")


def main():
    copy_privacy_manifest()
    copy_google_service_info()
    patch_info_plist()
    verify_no_unnecessary_permissions()
    log("iOS proje duzenlemeleri tamamlandi.")


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
generate-export-options.py
----------------------------
xcodebuild -exportArchive icin gereken exportOptions.plist dosyasini
ortam degiskenlerinden (env vars) okuyarak guvenli sekilde uretir.

Bu script, GitHub Actions workflow'u icine gomulu bir Python heredoc
kullanmak yerine ayri bir dosya olarak tutulur; boylece YAML girinti
(indentation) sorunlarindan etkilenmez ve test edilebilir/okunabilir olur.

DUZELTME (2): 'signingStyle' 'manual' yerine 'automatic' yapildi.
Kaynak: ionic-team/capacitor resmi deposu, issue #7625 - ayni "X.framework
does not support provisioning profiles" hatasini yasayan bir kullanici,
signingStyle degerini 'automatic' yaparak sorunu cozdugunu dogrulamis.
'manual' + use_frameworks! kombinasyonu, CocoaPods ile gomulen TUM
framework'lere (Capacitor, Firebase, vb.) de uygulamanin provisioning
profile'ini uygulamaya calisiyor ve frameworkler profil kabul etmedigi
icin hata veriyor. 'automatic' ile xcodebuild, .xcarchive icinde zaten
mevcut olan imzalari kullanarak her bileseni doğru sekilde paketliyor
(yeni profil talep etmiyor, sadece paketleme sirasinda -allowProvisioningUpdates
ile arsivde halihazirda gomulu olani kullanıyor).

Gerekli ortam degiskenleri:
  IOS_TEAM_ID       - Apple Developer Team ID
  IOS_PROFILE_NAME  - Provisioning profile adi (App Store Connect'te tanimli)
  BUNDLE_ID         - Uygulamanin bundle identifier'i
"""
import os
import plistlib
import sys


def main():
    team_id = os.environ.get("IOS_TEAM_ID", "")
    profile_name = os.environ.get("IOS_PROFILE_NAME", "")
    bundle_id = os.environ.get("BUNDLE_ID", "")

    missing = [name for name, val in [
        ("IOS_TEAM_ID", team_id),
        ("IOS_PROFILE_NAME", profile_name),
        ("BUNDLE_ID", bundle_id),
    ] if not val]
    if missing:
        print(f"[generate-export-options] HATA: eksik ortam degiskeni: {missing}")
        return 1

    opts = {
        "method": "app-store",
        "teamID": team_id,
        "signingStyle": "automatic",
        "uploadSymbols": True,
        "compileBitcode": False,
    }
    with open("exportOptions.plist", "wb") as f:
        plistlib.dump(opts, f)
    print("[generate-export-options] exportOptions.plist created:", opts)
    return 0


if __name__ == "__main__":
    sys.exit(main())

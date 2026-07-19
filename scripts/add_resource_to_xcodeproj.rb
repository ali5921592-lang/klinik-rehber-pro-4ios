#!/usr/bin/env ruby
# add_resource_to_xcodeproj.rb
# --------------------------------------
# Sadece bir dosyayi diske kopyalamak, Xcode'un onu .ipa icine paketlemesi
# icin YETERLI DEGILDIR -- dosyanin Xcode projesinin (.pbxproj) "Copy Bundle
# Resources" build phase'ine gercek bir referans olarak eklenmesi gerekir.
# Bu script, CocoaPods'un zaten bagimliligi oldugu (ve bu yuzden macOS
# runner'larda `pod install` sonrasi hazir bulunan) `xcodeproj` Ruby gem'ini
# kullanarak bu islemi programatik ve guvenilir sekilde yapar.
#
# add_privacy_manifest_to_xcodeproj.rb'nin genellestirilmis hali: artik
# PrivacyInfo.xcprivacy'ye ozel degil, komut satirindan verilen HERHANGI BIR
# dosya adini (orn. GoogleService-Info.plist) 'App' hedefine ekleyebilir.
#
# Kullanim: ruby scripts/add_resource_to_xcodeproj.rb <dosya_adi>
# Ornek:    ruby scripts/add_resource_to_xcodeproj.rb GoogleService-Info.plist

require 'xcodeproj'

project_path = 'ios/App/App.xcodeproj'
filename = ARGV[0]

if filename.nil? || filename.empty?
  puts "[add_resource] HATA: Dosya adi belirtilmedi. Kullanim: ruby scripts/add_resource_to_xcodeproj.rb <dosya_adi>"
  exit 1
end

unless File.exist?(project_path)
  puts "[add_resource] HATA: #{project_path} bulunamadi. 'npx cap add ios' calistirildi mi?"
  exit 1
end

unless File.exist?(File.join('ios/App/App', filename))
  puts "[add_resource] HATA: ios/App/App/#{filename} bulunamadi. patch-ios.py once calistirilmali."
  exit 1
end

project = Xcodeproj::Project.open(project_path)
app_target = project.targets.find { |t| t.name == 'App' }

if app_target.nil?
  puts "[add_resource] HATA: 'App' hedefi (target) bulunamadi."
  exit 1
end

# Ayni dosya zaten ekliyse tekrar eklemeyelim (idempotent).
already_added = app_target.resources_build_phase.files.any? do |bf|
  bf.file_ref && bf.file_ref.display_name == filename
end

if already_added
  puts "[add_resource] #{filename} zaten projede kayitli, tekrar eklenmedi."
  exit 0
end

# Capacitor'in olusturdugu, Info.plist'i iceren gercek "App" grubunu buluyoruz;
# boylece dosya referansi dogru fiziksel klasore (ios/App/App/) isaret eder.
# Bulunamazsa ana gruba (kok dizin) eklenir.
info_plist_ref = project.files.find { |f| f.display_name == 'Info.plist' }
app_group = info_plist_ref ? info_plist_ref.parent : project.main_group.find_subpath('App', true)

file_ref = app_group.new_reference(filename)
app_target.add_resources([file_ref])
project.save
puts "[add_resource] #{filename} basariyla 'Copy Bundle Resources' build phase'ine eklendi (grup: #{app_group.hierarchy_path})."

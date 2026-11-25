; YouTown Player installer (per-user, no admin rights needed)
Unicode true
SetCompressor /SOLID lzma
RequestExecutionLevel user

!define APP "YouTown Player"
!define VERSION "2.0.0"
!define SRC "..\dist\YouTown Player"
!define UNINST "Software\Microsoft\Windows\CurrentVersion\Uninstall\YouTownPlayer"

Name "${APP}"
OutFile "..\dist\YouTown-Player-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\${APP}"
InstallDirRegKey HKCU "${UNINST}" "InstallLocation"
Icon "..\assets\youtown.ico"
UninstallIcon "..\assets\youtown.ico"
BrandingText "${APP} ${VERSION}"

!include "MUI2.nsh"
!define MUI_ICON "..\assets\youtown.ico"
!define MUI_UNICON "..\assets\youtown.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP}.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Open ${APP}"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP}"
VIAddVersionKey "FileDescription" "${APP} Setup"
VIAddVersionKey "CompanyName" "YouTown"
VIAddVersionKey "LegalCopyright" "Copyright (c) 2026 YouTown Player contributors"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"

Section "Install"
  ; close a running copy so files can be replaced
  nsExec::Exec 'taskkill /IM "${APP}.exe" /F'
  SetOutPath "$INSTDIR"
  File /r "${SRC}\*.*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateShortcut "$SMPROGRAMS\${APP}.lnk" "$INSTDIR\${APP}.exe"
  CreateShortcut "$DESKTOP\${APP}.lnk" "$INSTDIR\${APP}.exe"
  WriteRegStr HKCU "${UNINST}" "DisplayName" "${APP}"
  WriteRegStr HKCU "${UNINST}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST}" "Publisher" "YouTown"
  WriteRegStr HKCU "${UNINST}" "DisplayIcon" "$INSTDIR\${APP}.exe"
  WriteRegStr HKCU "${UNINST}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "${UNINST}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  nsExec::Exec 'taskkill /IM "${APP}.exe" /F'
  ; file associations the app registered for "Default apps"
  DeleteRegKey HKCU "Software\Classes\YouTown.Media"
  DeleteRegKey HKCU "Software\YouTownPlayer"
  DeleteRegValue HKCU "Software\RegisteredApplications" "${APP}"
  !include "assoc_cleanup.nsh"
  Delete "$SMPROGRAMS\${APP}.lnk"
  Delete "$DESKTOP\${APP}.lnk"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "${UNINST}"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd

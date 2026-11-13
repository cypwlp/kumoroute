!macro NSIS_HOOK_PREINSTALL
  ; Older builds could leave the mihomo child process alive after the UI exits.
  ; Ask Restart Manager to close anything holding the bundled core before overwrite.
  !insertmacro CheckIfAppIsRunning "$INSTDIR\core\mihomo.exe" "KumoRoute 核心 (mihomo.exe)"
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro CheckIfAppIsRunning "$INSTDIR\core\mihomo.exe" "KumoRoute 核心 (mihomo.exe)"
!macroend

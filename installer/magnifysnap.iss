; Установщик Magnify.Snap (Inno Setup).
;
; Зачем он нужен: winget ставит «портативный» тип без единого ярлыка, и
; обычный человек после установки просто не может запустить программу.
; Установщик кладёт файл в пользовательскую папку (без прав администратора)
; и создаёт ярлык в меню «Пуск» сразу, до первого запуска.
;
; Сборка:  ISCC.exe /DMyVersion=1.4.1 installer\magnifysnap.iss

#ifndef MyVersion
  #define MyVersion "0.0.0"
#endif
#define MyAppName "Magnify.Snap"
#define MyPublisher "violet2code"
#define MyURL "https://violet2code.github.io/"
#define MyExe "MagnifySnap.exe"

[Setup]
; постоянный идентификатор — по нему находятся прошлые установки
AppId={{8C3F5E42-7A19-4B6D-9E52-2D4F1A8C0B37}
AppName={#MyAppName}
AppVersion={#MyVersion}
AppVerName={#MyAppName} {#MyVersion}
VersionInfoVersion={#MyVersion}
AppPublisher={#MyPublisher}
AppPublisherURL={#MyURL}
AppSupportURL=https://github.com/violet2code/magnify-snap/issues
AppUpdatesURL=https://github.com/violet2code/magnify-snap/releases
DefaultDirName={localappdata}\Programs\MagnifySnap
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
; установка от обычного пользователя: без UAC и без прав администратора,
; иначе программа не сможет обновлять сама себя
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=MagnifySnap-{#MyVersion}-windows-x64-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
; закрыть работающую копию при обновлении и запустить заново
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start {#MyAppName} when I sign in"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "..\dist\{#MyExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; ярлык появляется сразу при установке — до первого запуска программы
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyExe}"; Comment: "Fast screen magnifier"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MagnifySnap"; ValueData: """{app}\{#MyExe}"""; Flags: uninsdeletevalue; Tasks: startup
; автозапуск мог быть включён и в самой программе — тогда записи с Tasks
; выше нет, и при удалении осталась бы ссылка на несуществующий файл
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "MagnifySnap"; Flags: deletevalue uninsdeletevalue; Tasks: not startup

[Run]
Filename: "{app}\{#MyExe}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
; при самообновлении программа зовёт установщик с /AUTOLAUNCH=1 и должна
; подняться заново; при обычной тихой установке (winget) — не запускаем
Filename: "{app}\{#MyExe}"; Flags: nowait runasoriginaluser; Check: WantsAutoLaunch

[Code]
function WantsAutoLaunch: Boolean;
begin
  Result := ExpandConstant('{param:AUTOLAUNCH|0}') = '1';
end;

[UninstallRun]
; тихо снимаем работающую копию перед удалением файлов
Filename: "{sys}\taskkill.exe"; Parameters: "/IM {#MyExe} /F"; Flags: runhidden; RunOnceId: "StopMagnifySnap"

[UninstallDelete]
; ярлык, который программа могла создать сама (портативный режим)
Type: files; Name: "{autoprograms}\{#MyAppName}.lnk"

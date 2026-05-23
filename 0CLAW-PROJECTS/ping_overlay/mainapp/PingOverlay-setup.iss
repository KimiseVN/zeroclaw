; PingOverlay Inno Setup Script
; Build: iscc PingOverlay-setup.iss /DAppVersion=X.Y.ZZ
; Or let build_setup.ps1 pass the version automatically.

#ifndef AppVersion
  #define AppVersion "0.0.00"
#endif

#define AppName       "WWM Overlay"
#define AppPublisher  "ムKim"
#define AppURL        "https://wwmoverlay.com"
#define AppExeName    "PingOverlay.exe"
#define AppInternalDir "_internal"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\PingOverlay
DefaultGroupName={#AppName}
AllowNoIcons=no
; Require admin (app itself needs admin for raw sockets + ETW)
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=
OutputDir=dist
OutputBaseFilename=PingOverlay-Setup-v{#AppVersion}
SetupIconFile=wwm-logo.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSmallImageFile=wwm-logo.png
; Uninstaller
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
; Version info embedded in Setup.exe
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
; Minimum Windows 10
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; Main executable
Source: "dist\PingOverlay\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; OptizNW — network optimizer companion (standalone onefile exe)
Source: "dist\PingOverlay\OptizNW.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; _internal — entire PyInstaller runtime tree:
;   flat root: python3xx.dll, *.pyd, *.dll, base_library.zip
;   subdirs:   assets\, bin\, data\, PIL\, pystray\, certifi\, tcl8\, _tcl_data\, _tk_data\, etc.
Source: "dist\PingOverlay\{#AppInternalDir}\*"; DestDir: "{app}\{#AppInternalDir}"; Flags: ignoreversion recursesubdirs createallsubdirs

; manifest.json for incremental updater
Source: "dist\PingOverlay\manifest.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}";       Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent runasoriginaluser

[InstallDelete]
; Remove stale loose .py module files that old builds may have left in _internal\.
; Only the root level is targeted (PIL\ and pystray\ subdirs are intentional).
; Inno Setup deletes these BEFORE copying the new files so the stale .py files
; cannot shadow the PYZ-compiled versions in the new build.
Type: files; Name: "{app}\{#AppInternalDir}\*.py"

[UninstallDelete]
; Remove user config on uninstall (optional — comment out to keep user settings)
; Type: filesandordirs; Name: "{commonappdata}\PingOverlay"

[Code]
// AppWasAlreadyInstalled: used by GetCustomSetupExitCode to return 8 (upgrade)
// instead of 0 (fresh install) — required by Intune/WinGet.
var
  AppWasAlreadyInstalled: Boolean;

// ── Registry helpers ──────────────────────────────────────────────────────────

function GetUninstallRegKey(): String;
begin
  if RegKeyExists(HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}_is1') then
    Result := 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}_is1'
  else if RegKeyExists(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}_is1') then
    Result := 'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}_is1'
  else
    Result := '';
end;

function GetInstalledVersion(): String;
var
  Key, Ver: String;
begin
  Key := GetUninstallRegKey();
  if (Key = '') or (not RegQueryStringValue(HKLM, Key, 'DisplayVersion', Ver)) then
    Ver := '';
  Result := Ver;
end;

function GetUninstallerPath(): String;
var
  Key, Path: String;
begin
  Key := GetUninstallRegKey();
  if (Key = '') or (not RegQueryStringValue(HKLM, Key, 'UninstallString', Path)) then
    Path := '';
  Result := Path;
end;

function StripQuotes(S: String): String;
begin
  if (Length(S) >= 2) and (S[1] = '"') and (S[Length(S)] = '"') then
    Result := Copy(S, 2, Length(S) - 2)
  else
    Result := S;
end;

// ── Version comparison ────────────────────────────────────────────────────────

// Returns the Nth dot-separated numeric component of a version string.
function VersionPart(const V: String; Part: Integer): Integer;
var
  S: String;
  P, i: Integer;
begin
  S := V;
  Result := 0;
  for i := 1 to Part do begin
    P := Pos('.', S);
    if P = 0 then begin
      if i = Part then
        Result := StrToIntDef(Trim(S), 0);
      Exit;
    end;
    if i = Part then begin
      Result := StrToIntDef(Trim(Copy(S, 1, P - 1)), 0);
      Exit;
    end;
    S := Copy(S, P + 1, Length(S));
  end;
end;

// Returns: 1 if V1 > V2, -1 if V1 < V2, 0 if equal.
function CompareVersionStrings(const V1, V2: String): Integer;
var
  i, n1, n2: Integer;
begin
  Result := 0;
  for i := 1 to 3 do begin
    n1 := VersionPart(V1, i);
    n2 := VersionPart(V2, i);
    if n1 > n2 then begin Result :=  1; Exit; end;
    if n1 < n2 then begin Result := -1; Exit; end;
  end;
end;

// ── Setup entry point ─────────────────────────────────────────────────────────

function InitializeSetup(): Boolean;
var
  ResultCode, Cmp, Choice: Integer;
  InstalledVer, InstallerVer, UninstPath: String;
begin
  // Always kill the running process first so files can be replaced.
  Exec('taskkill.exe', '/F /IM PingOverlay.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  InstalledVer := GetInstalledVersion();
  InstallerVer := '{#AppVersion}';

  AppWasAlreadyInstalled := InstalledVer <> '';

  if InstalledVer <> '' then begin
    Cmp := CompareVersionStrings(InstalledVer, InstallerVer);

    // ── Newer version already installed → block ───────────────────────────
    if Cmp > 0 then begin
      MsgBox(
        'A newer version is already installed.' + #13#10 +
        '  Installed : v' + InstalledVer + #13#10 +
        '  This setup: v' + InstallerVer + #13#10#13#10 +
        'Installation cancelled.',
        mbInformation, MB_OK
      );
      Result := False;
      Exit;
    end;

    // ── Same version → Repair / Uninstall ────────────────────────────────
    if Cmp = 0 then begin
      Choice := MsgBox(
        'Version ' + InstallerVer + ' is already installed.' + #13#10#13#10 +
        'Yes    — Repair (reinstall all files)' + #13#10 +
        'No     — Uninstall' + #13#10 +
        'Cancel — Exit',
        mbConfirmation, MB_YESNOCANCEL
      );
      if Choice = IDYES then begin
        // Repair: fall through and let setup overwrite files.
        Result := True;
        Exit;
      end else if Choice = IDNO then begin
        // Uninstall: launch the existing uninstaller.
        UninstPath := StripQuotes(GetUninstallerPath());
        if UninstPath <> '' then
          Exec(UninstPath, '/NORESTART', '', SW_SHOW, ewWaitUntilTerminated, ResultCode)
        else
          MsgBox(
            'Uninstaller not found.' + #13#10 +
            'Please uninstall via Windows Settings → Apps.',
            mbError, MB_OK
          );
        Result := False;
        Exit;
      end else begin
        // Cancel.
        Result := False;
        Exit;
      end;
    end;

    // Cmp < 0: older version installed → proceed with upgrade (fall through).
  end;

  Result := True;
end;

// ── Exit code ─────────────────────────────────────────────────────────────────

// Return code 8 when upgrading an existing install, 0 for fresh install.
function GetCustomSetupExitCode(): Integer;
begin
  if AppWasAlreadyInstalled then
    Result := 8   // Upgrade / reinstall
  else
    Result := 0;  // Fresh install
end;

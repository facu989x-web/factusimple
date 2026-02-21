; Inno Setup template (editar rutas según build local)
#define MyAppName "FacturaSimple"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "FacturaSimple"
#define MyAppExeName "app.exe"

[Setup]
AppId={{F5B02A5E-2F0F-4A53-A4E9-FACTUSIMPLE001}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf32}\FacturaSimple
DefaultGroupName=FacturaSimple
OutputDir=dist
OutputBaseFilename=factusimple_installer
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\factusimple_bundle\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Run]
; Opcional: post-install para setear openssl_path + defaults de impresión
Filename: "{app}\python.exe"; Parameters: "installer\post_install_config.py --install-dir ""{app}"""; Flags: runhidden
; Ejecutar app al finalizar
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir FacturaSimple"; Flags: nowait postinstall skipifsilent

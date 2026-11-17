import argparse
import base64
import ctypes
import glob
import os
import shutil
import subprocess
import sys
import uuid
from xml.sax.saxutils import escape, quoteattr

from build_vsix import build_vsix

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "Installer")
COMPILER = os.path.join(ROOT, "Compiler")
RELEASE = os.path.join(ROOT, "release")
WORK = os.path.join(ROOT, "build", "installer")
ICON = os.path.join(ROOT, "Icons", "Vamp.ico")
DATA_ICON = os.path.join(ROOT, "Icons", "Data.ico")
UPGRADE_CODE = "{6B1F2E4A-9C3D-4E57-8A21-5D7C0F3B9E14}"
NAMESPACE = uuid.UUID(UPGRADE_CODE)
HOMEPAGE = "https://github.com/Clxtus/Vamp"
VSCODE_USER = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{771FD6B0-FA20-440A-A002-3B3BAC16DC50}_is1"
VSCODE_SYSTEM = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{EA457B21-F73E-494C-ACAB-524FDE069978}_is1"
PANEL_TOP = (236, 200, 200)
PANEL_BOTTOM = (214, 160, 160)
ACCENT = (125, 0, 0)
FONTS = {"WixUI_Font_Normal": "Segoe UI", "WixUI_Font_Bigger": "Segoe UI Semibold",
         "WixUI_Font_Title": "Segoe UI Semibold", "WixUI_Font_Emphasized": "Segoe UI Semibold"}

# The helper PowerShell process is started with Run(..., 0) (hidden from creation, no console flash)
# and its output is read back from a temp file; Exec() always shows a console window.
FOLDER_PICKER_SCRIPT = '''Sub ChooseInstallFolder()
Dim shell
Dim windowShell
Dim fso
Dim tempFile
Dim stream
Dim selectedFolder
Dim installPath
Dim windowHandle
Set shell = CreateObject("Shell.Application")
Set windowShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
tempFile = fso.BuildPath(fso.GetSpecialFolder(2), fso.GetTempName())
windowHandle = 0
On Error Resume Next
windowShell.Run "cmd.exe /s /c ""powershell.exe -NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand WINDOW_HANDLE_COMMAND > """ & tempFile & """""", 0, True
If fso.FileExists(tempFile) Then
  Set stream = fso.OpenTextFile(tempFile, 1)
  windowHandle = Trim(stream.ReadAll())
  stream.Close
  fso.DeleteFile tempFile, True
End If
On Error GoTo 0
If IsNumeric(windowHandle) And Len(windowHandle) > 0 Then
  windowHandle = CLng(windowHandle)
Else
  windowHandle = 0
End If
If windowHandle = 0 Then
  windowHandle = Session.Property("HWND")
  If IsNumeric(windowHandle) And Len(windowHandle) > 0 Then
    windowHandle = CLng(windowHandle)
  Else
    windowHandle = 0
  End If
End If
Set selectedFolder = shell.BrowseForFolder(windowHandle, "Choose an installation folder for Vamp", &H51)
If Not selectedFolder Is Nothing Then
  installPath = selectedFolder.Self.Path
  If Right(installPath, 1) <> Chr(92) Then installPath = installPath & Chr(92)
  Session.Property("INSTALLDIR") = installPath
End If
End Sub
'''
# Launches "vamp.exe setup" completely hidden and without waiting for it.
BUILD_TOOLS_SCRIPT = '''Sub RunBuildTools()
Dim windowShell
Set windowShell = CreateObject("WScript.Shell")
windowShell.Run Chr(34) & Session.Property("INSTALLDIR") & "vamp.exe" & Chr(34) & " setup", 0, False
End Sub
'''
WINDOW_HANDLE_SCRIPT = """Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public class MsiWindow { [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr FindWindow(string className, string windowName); }'
[MsiWindow]::FindWindow($null, 'Vamp Setup').ToInt64()
"""


def run(arguments, cwd=None):
    print(">", " ".join(arguments), flush=True)
    subprocess.run(arguments, cwd=cwd, check=True)


def encode_powershell_command(script):
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def find_wix(given):
    candidates = [given, os.environ.get("WIX") and os.path.join(os.environ["WIX"], "bin"),
                  os.path.dirname(shutil.which("candle.exe") or "")]
    for folder in candidates:
        if folder and os.path.isfile(os.path.join(folder, "candle.exe")):
            return folder
    sys.exit("WiX Toolset 3.14 was not found. Download wix314-binaries.zip from "
             "https://github.com/wixtoolset/wix3/releases and pass --wix <folder>.")


def guid(text):
    return "{" + str(uuid.uuid5(NAMESPACE, text)).upper() + "}"


def identifier(prefix, text):
    return prefix + "_" + uuid.uuid5(NAMESPACE, text).hex[:24]


def file_tree(folder, relative="", directory="INSTALLDIR"):
    directories, components = [], []
    for name in sorted(os.listdir(os.path.join(folder, relative))):
        child = os.path.join(relative, name) if relative else name
        if os.path.isdir(os.path.join(folder, child)):
            inner_id = identifier("dir", child)
            inner_directories, inner_components = file_tree(folder, child, inner_id)
            directories.append(f'<Directory Id="{inner_id}" Name={quoteattr(name)}>{"".join(inner_directories)}</Directory>')
            components += inner_components
        else:
            file_id = {"vamp.exe": "VampExe", "Vamp.ico": "VampIco", "Data.ico": "DataIco"}.get(child, identifier("file", child))
            component = identifier("cmp", child)
            components.append((directory, (component, file_id, os.path.join(folder, child), child)))
    return directories, components


def make_artwork(folder):
    from PIL import Image, ImageDraw, ImageFont
    logo = Image.open(ICON).convert("RGBA")
    fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    title_font = ImageFont.truetype(os.path.join(fonts, "seguisb.ttf"), 30)
    small_font = ImageFont.truetype(os.path.join(fonts, "segoeui.ttf"), 13)

    dialog = Image.new("RGB", (493, 312), "white")
    draw = ImageDraw.Draw(dialog)
    for y in range(312):
        mix = y / 311
        draw.line([(0, y), (159, y)], fill=tuple(int(top + (bottom - top) * mix)
                                                 for top, bottom in zip(PANEL_TOP, PANEL_BOTTOM)))
    draw.rectangle([(160, 0), (163, 311)], fill=ACCENT)
    mark = logo.resize((112, 112), Image.LANCZOS)
    dialog.paste(mark, (24, 48), mark)
    draw.text((80, 186), "Vamp", fill=ACCENT, font=title_font, anchor="mm")
    draw.text((80, 214), "programming language", fill=(90, 50, 50), font=small_font, anchor="mm")
    dialog.save(os.path.join(folder, "dialog.bmp"))

    banner = Image.new("RGB", (493, 58), "white")
    mark = logo.resize((44, 44), Image.LANCZOS)
    banner.paste(mark, (438, 7), mark)
    ImageDraw.Draw(banner).line([(0, 57), (492, 57)], fill=ACCENT, width=2)
    banner.save(os.path.join(folder, "banner.bmp"))


def make_license_rtf(target):
    with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as fh:
        paragraphs = [" ".join(block.split()) for block in fh.read().strip().split("\n\n")]
    body = "".join(
        "\\pard\\sa160 " + text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}") + "\\par\n"
        for text in paragraphs)
    with open(target, "w", encoding="ascii") as fh:
        fh.write("{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0\\fswiss Segoe UI;}}\\f0\\fs18\n" + body + "}")


def make_wxs(payload, version):
    directories, components = file_tree(payload)
    file_components = []
    for dirpath, (component, file_id, src, relative) in components:
        file_components.append(
            f'<Component Id="{component}" Directory="{dirpath}" Guid="{guid("file:" + relative)}">'
            f'<File Id="{file_id}" Source={quoteattr(src)} KeyPath="yes" /></Component>')
    folder_removals = "".join(
        f'<RemoveFolder Id="{identifier("rm", d)}" Directory="{d}" On="uninstall" />'
        for d in sorted({dirpath for dirpath, _ in components} - {"INSTALLDIR"}))
    references = "".join(f'<ComponentRef Id="{component}" />' for _, (component, _, _, _) in components)
    run_command = 'cmd.exe /c ""[INSTALLDIR]vamp.exe" run "%1" &amp; echo. &amp; pause"'
    folder_picker_script = quoteattr(os.path.join(WORK, "choose_install_folder.vbs"))
    build_tools_script = quoteattr(os.path.join(WORK, "run_build_tools.vbs"))
    opener_components = []
    for name, cond, cmd in (
            ("User", "VSCODEUSER", '"[VSCODEUSER]Code.exe" "%1"'),
            ("System", "VSCODESYSTEM AND NOT VSCODEUSER", '"[VSCODESYSTEM]Code.exe" "%1"'),
            ("Notepad", "NOT VSCODEUSER AND NOT VSCODESYSTEM", 'notepad.exe "%1"')):
        vals = "".join(
            f'<RegistryValue Root="HKCU" Key="Software\\Classes\\{prog_id}\\shell\\open\\command" Type="string" '
            f'Value={quoteattr(cmd)} />' for prog_id in ("Vamp.Source", "Vamp.Data"))
        opener_components.append(
            f'<Component Id="Open{name}" Directory="INSTALLDIR" Guid="{guid("open:" + name)}">'
            f'<Condition>{cond}</Condition>'
            f'<RegistryValue Root="HKCU" Key="Software\\Vamp" Name="Open{name}" Type="integer" Value="1" KeyPath="yes" />'
            f'{vals}</Component>')
    file_types = []
    for extension, prog_id, description, icon in ((".vp", "Vamp.Source", "Vamp Source File", "Vamp.ico"),
                                                  (".vpdata", "Vamp.Data", "Vamp Data File", "Data.ico")):
        classes = f"Software\\Classes\\{prog_id}"
        file_types += [
            f'<RegistryValue Root="HKCU" Key="Software\\Classes\\{extension}" Type="string" Value="{prog_id}" />',
            f'<RegistryValue Root="HKCU" Key="{classes}" Type="string" Value="{description}" />',
            f'<RegistryValue Root="HKCU" Key="{classes}\\DefaultIcon" Type="string" Value="&quot;[INSTALLDIR]{icon}&quot;,0" />',
        ]
    file_types += [
        '<RegistryValue Root="HKCU" Key="Software\\Classes\\Vamp.Source\\shell\\run" Type="string" Value="Run with Vamp" />',
        '<RegistryValue Root="HKCU" Key="Software\\Classes\\Vamp.Source\\shell\\run" Name="Icon" Type="string" '
        'Value="&quot;[INSTALLDIR]vamp.exe&quot;,0" />',
        f'<RegistryValue Root="HKCU" Key="Software\\Classes\\Vamp.Source\\shell\\run\\command" Type="string" '
        f'Value="{escape(run_command, {chr(34): "&quot;"})}" />',
    ]
    quiet = 'BinaryKey="WixCA" DllEntry="WixQuietExec64" Execute="immediate" Return="ignore"'
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi" xmlns:util="http://schemas.microsoft.com/wix/UtilExtension">
  <Product Id="*" Name="Vamp" Language="1033" Version="{version}" Manufacturer="Clxtus" UpgradeCode="{UPGRADE_CODE}">
    <Package InstallerVersion="500" Compressed="yes" InstallScope="perUser" InstallPrivileges="limited"
             Platform="x64" Description="Vamp programming language {version}" />
    <MajorUpgrade DowngradeErrorMessage="A newer version of Vamp is already installed." />
    <MediaTemplate EmbedCab="yes" CompressionLevel="high" />
    <Icon Id="VampIcon" SourceFile={quoteattr(ICON)} />
    <Binary Id="ChooseInstallFolderScript" SourceFile={folder_picker_script} />
    <Binary Id="BuildToolsScript" SourceFile={build_tools_script} />
    <Property Id="ARPPRODUCTICON" Value="VampIcon" />
    <Property Id="ARPHELPLINK" Value="{HOMEPAGE}" />
    <Property Id="ARPURLINFOABOUT" Value="{HOMEPAGE}" />
    <Property Id="VSCODEUSER"><RegistrySearch Id="FindCodeUser" Root="HKCU" Key="{VSCODE_USER}" Name="InstallLocation" Type="directory" /></Property>
    <Property Id="VSCODESYSTEM"><RegistrySearch Id="FindCodeSystem" Root="HKLM" Key="{VSCODE_SYSTEM}" Name="InstallLocation" Type="directory" Win64="yes" /></Property>
    <Property Id="CLANGFOUND"><DirectorySearch Id="FindLlvm" Path="[ProgramFiles64Folder]LLVM\\bin" Depth="0"><FileSearch Id="FindClang" Name="clang.exe" /></DirectorySearch></Property>
    <Property Id="WIXUI_INSTALLDIR" Value="INSTALLDIR" />
    <Property Id="WIXUI_EXITDIALOGOPTIONALCHECKBOXTEXT" Value="Download and install LLVM and the C++ build tools if they are missing (needed to build programs)" />
    <SetProperty Id="WIXUI_EXITDIALOGOPTIONALCHECKBOX" Value="1" After="AppSearch" Sequence="ui">NOT CLANGFOUND</SetProperty>

    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="LocalAppDataFolder">
        <Directory Id="ProgramsDir" Name="Programs">
          <Directory Id="INSTALLDIR" Name="Vamp">{"".join(directories)}</Directory>
        </Directory>
      </Directory>
      <Directory Id="ProgramMenuFolder"><Directory Id="VampMenu" Name="Vamp" /></Directory>
    </Directory>

    {"".join(file_components)}
    <Component Id="Registration" Directory="INSTALLDIR" Guid="{guid("registration")}">
      <RegistryValue Root="HKCU" Key="Software\\Vamp" Name="InstallFolder" Type="string" Value="[INSTALLDIR]" KeyPath="yes" />
      <RemoveFolder Id="RemoveInstallFolder" Directory="INSTALLDIR" On="uninstall" />
      {folder_removals}
    </Component>
    <Component Id="PathEntry" Directory="INSTALLDIR" Guid="{guid("path")}">
      <Environment Id="VampPath" Name="PATH" Value="[INSTALLDIR]" Part="last" Action="set" System="no" Permanent="no" />
      <RegistryValue Root="HKCU" Key="Software\\Vamp" Name="Path" Type="integer" Value="1" KeyPath="yes" />
    </Component>
    <Component Id="FileTypes" Directory="INSTALLDIR" Guid="{guid("filetypes")}">
      <RegistryValue Root="HKCU" Key="Software\\Vamp" Name="FileTypes" Type="integer" Value="1" KeyPath="yes" />
      {"".join(file_types)}
    </Component>
    {"".join(opener_components)}
    <Component Id="Shortcuts" Directory="VampMenu" Guid="{guid("shortcuts")}">
      <Shortcut Id="ExamplesShortcut" Name="Vamp Examples" Target="[INSTALLDIR]Examples" Icon="VampIcon" />
      <Shortcut Id="UninstallShortcut" Name="Uninstall Vamp" Target="[System64Folder]msiexec.exe" Arguments="/x [ProductCode]" Icon="VampIcon" />
      <util:InternetShortcut Id="DocsShortcut" Name="Vamp Documentation" Target="{HOMEPAGE}/blob/main/DOCUMENTATION.md" />
      <RemoveFolder Id="RemoveMenu" On="uninstall" />
      <RegistryValue Root="HKCU" Key="Software\\Vamp" Name="StartMenu" Type="integer" Value="1" KeyPath="yes" />
    </Component>
    <Component Id="EditorMarker" Directory="INSTALLDIR" Guid="{guid("vscode")}">
      <RegistryValue Root="HKCU" Key="Software\\Vamp" Name="VSCode" Type="integer" Value="1" KeyPath="yes" />
    </Component>

    <Feature Id="Core" Title="Vamp" Description="The Vamp compiler, documentation and examples." Level="1"
             Absent="disallow" AllowAdvertise="no" Display="expand" ConfigurableDirectory="INSTALLDIR">
      {references}<ComponentRef Id="Registration" />
      <Feature Id="PathFeature" Title="Add to PATH" Description="Use the vamp command from any terminal." Level="1" AllowAdvertise="no">
        <ComponentRef Id="PathEntry" />
      </Feature>
      <Feature Id="FileTypesFeature" Title="File icons" Description="Vamp icons for .vp and .vpdata files, and Run with Vamp in the right-click menu." Level="1" AllowAdvertise="no">
        <ComponentRef Id="FileTypes" />
        <ComponentRef Id="OpenUser" /><ComponentRef Id="OpenSystem" /><ComponentRef Id="OpenNotepad" />
      </Feature>
      <Feature Id="ShortcutsFeature" Title="Start menu" Description="Shortcuts to the examples, the documentation and the uninstaller." Level="1" AllowAdvertise="no">
        <ComponentRef Id="Shortcuts" />
      </Feature>
      <Feature Id="VSCode" Title="Visual Studio Code extension" Description="Highlighting, error checking, completion and debugging for Vamp in Visual Studio Code." Level="1" AllowAdvertise="no">
        <ComponentRef Id="EditorMarker" />
        <Condition Level="0">NOT VSCODEUSER AND NOT VSCODESYSTEM</Condition>
      </Feature>
    </Feature>

    <CustomAction Id="ChooseInstallFolder" BinaryKey="ChooseInstallFolderScript"
                  VBScriptCall="ChooseInstallFolder" Execute="immediate" Return="check" />
    <CustomAction Id="SetInstallExtension" Property="WixQuietExecCmdLine" Value="&quot;[INSTALLDIR]vamp.exe&quot; setup --vscode" />
    <CustomAction Id="InstallExtension" {quiet} />
    <CustomAction Id="SetRemoveExtension" Property="WixQuietExecCmdLine" Value="&quot;[INSTALLDIR]vamp.exe&quot; setup --remove-vscode" />
    <CustomAction Id="RemoveExtension" {quiet} />
    <CustomAction Id="SetupBuildTools" BinaryKey="BuildToolsScript"
                  VBScriptCall="RunBuildTools" Execute="immediate" Return="ignore" />
    <InstallExecuteSequence>
      <Custom Action="SetRemoveExtension" Before="RemoveFiles">!VSCode=3 AND &amp;VSCode=2 AND NOT UPGRADINGPRODUCTCODE</Custom>
      <Custom Action="RemoveExtension" After="SetRemoveExtension">!VSCode=3 AND &amp;VSCode=2 AND NOT UPGRADINGPRODUCTCODE</Custom>
      <Custom Action="SetInstallExtension" After="InstallFinalize">&amp;VSCode=3</Custom>
      <Custom Action="InstallExtension" After="SetInstallExtension">&amp;VSCode=3</Custom>
    </InstallExecuteSequence>

    <UI>
      <TextStyle Id="WixUI_Font_Normal" FaceName="Segoe UI" Size="8" />
      <TextStyle Id="WixUI_Font_Bigger" FaceName="Segoe UI Semibold" Size="12" />
      <TextStyle Id="WixUI_Font_Title" FaceName="Segoe UI Semibold" Size="9" Bold="yes" />
      <Property Id="DefaultUIFont" Value="WixUI_Font_Normal" />
      <Property Id="WixUI_Mode" Value="InstallDir" />
      <Property Id="ARPNOMODIFY" Value="1" />

      <DialogRef Id="CancelDlg" />
      <DialogRef Id="ErrorDlg" />
      <DialogRef Id="ExitDialog" />
      <DialogRef Id="FatalError" />
      <DialogRef Id="FilesInUse" />
      <DialogRef Id="InvalidDirDlg" />
      <DialogRef Id="MaintenanceTypeDlg" />
      <DialogRef Id="MaintenanceWelcomeDlg" />
      <DialogRef Id="MsiRMFilesInUse" />
      <DialogRef Id="PrepareDlg" />
      <DialogRef Id="ProgressDlg" />
      <DialogRef Id="ResumeDlg" />
      <DialogRef Id="VerifyReadyDlg" />
      <DialogRef Id="WelcomeDlg" />
      <DialogRef Id="UserExit" />

      <Dialog Id="VampLicenseDlg" Width="370" Height="270" Title="!(loc.LicenseDlgWindowTitle)">
        <Control Id="BannerBitmap" Type="Bitmap" X="0" Y="0" Width="370" Height="44" TabSkip="no" Text="!(loc.LicenseAgreementDlgBannerBitmap)" />
        <Control Id="BannerLine" Type="Line" X="0" Y="44" Width="370" Height="0" />
        <Control Id="BottomLine" Type="Line" X="0" Y="234" Width="370" Height="0" />
        <Control Id="Description" Type="Text" X="25" Y="23" Width="340" Height="15" Transparent="yes" NoPrefix="yes" Text="!(loc.LicenseAgreementDlgDescription)" />
        <Control Id="Title" Type="Text" X="15" Y="6" Width="200" Height="15" Transparent="yes" NoPrefix="yes" Text="!(loc.LicenseAgreementDlgTitle)" />
        <Control Id="LicenseAcceptedCheckBox" Type="CheckBox" X="20" Y="207" Width="330" Height="18" CheckBoxValue="1" Property="LicenseAccepted" Text="!(loc.LicenseAgreementDlgLicenseAcceptedCheckBox)" />
        <Control Id="Back" Type="PushButton" X="180" Y="243" Width="56" Height="17" Text="!(loc.WixUIBack)" />
        <Control Id="Next" Type="PushButton" X="236" Y="243" Width="56" Height="17" Default="yes" Text="!(loc.WixUINext)">
          <Condition Action="disable"><![CDATA[LicenseAccepted <> "1"]]></Condition>
          <Condition Action="enable">LicenseAccepted = "1"</Condition>
        </Control>
        <Control Id="Cancel" Type="PushButton" X="304" Y="243" Width="56" Height="17" Cancel="yes" Text="!(loc.WixUICancel)">
          <Publish Event="SpawnDialog" Value="CancelDlg">1</Publish>
        </Control>
        <Control Id="LicenseText" Type="ScrollableText" X="20" Y="60" Width="330" Height="140" Sunken="yes" TabSkip="no">
          <Text SourceFile="!(wix.WixUILicenseRtf=$(var.licenseRtf))" />
        </Control>
      </Dialog>

      <Dialog Id="InstallLocationDlg" Width="370" Height="270" Title="!(loc.PathDlgWindowTitle)">
        <Control Id="Title" Type="Text" X="15" Y="6" Width="300" Height="15" Transparent="yes" NoPrefix="yes" Text="!(loc.PathDlgTitle)" />
        <Control Id="Description" Type="Text" X="25" Y="23" Width="320" Height="15" Transparent="yes" NoPrefix="yes" Text="!(loc.PathDlgDescription)" />
        <Control Id="BannerBitmap" Type="Bitmap" X="0" Y="0" Width="370" Height="44" TabSkip="no" Text="!(loc.InstallDirDlgBannerBitmap)" />
        <Control Id="BannerLine" Type="Line" X="0" Y="44" Width="370" Height="0" />
        <Control Id="BottomLine" Type="Line" X="0" Y="234" Width="370" Height="0" />
        <Control Id="FolderLabel" Type="Text" X="25" Y="76" Width="320" Height="15" NoPrefix="yes" Text="!(loc.PathDlgFolderLabel)" />
        <Control Id="Folder" Type="PathEdit" X="25" Y="100" Width="250" Height="18" Property="WIXUI_INSTALLDIR" Indirect="yes" />
        <Control Id="ChoosePath" Type="PushButton" X="289" Y="100" Width="56" Height="17" Text="!(loc.PathDlgChoosePath)">
          <Publish Event="DoAction" Value="ChooseInstallFolder">1</Publish>
        </Control>
        <Control Id="Back" Type="PushButton" X="168" Y="243" Width="56" Height="17" Text="!(loc.WixUIBack)" />
        <Control Id="Install" Type="PushButton" X="224" Y="243" Width="68" Height="17" Default="yes" Text="!(loc.PathDlgInstall)">
          <Publish Event="SetTargetPath" Value="[WIXUI_INSTALLDIR]" Order="1">1</Publish>
          <Publish Event="DoAction" Value="WixUIValidatePath" Order="2">NOT WIXUI_DONTVALIDATEPATH</Publish>
          <Publish Event="SpawnDialog" Value="InvalidDirDlg" Order="3"><![CDATA[NOT WIXUI_DONTVALIDATEPATH AND WIXUI_INSTALLDIR_VALID<>"1"]]></Publish>
          <Publish Event="EndDialog" Value="Return" Order="4">WIXUI_DONTVALIDATEPATH OR WIXUI_INSTALLDIR_VALID="1"</Publish>
        </Control>
        <Control Id="Cancel" Type="PushButton" X="304" Y="243" Width="56" Height="17" Cancel="yes" Text="!(loc.WixUICancel)">
          <Publish Event="SpawnDialog" Value="CancelDlg">1</Publish>
        </Control>
      </Dialog>

      <Publish Dialog="WelcomeDlg" Control="Next" Event="NewDialog" Value="VampLicenseDlg">NOT Installed</Publish>
      <Publish Dialog="WelcomeDlg" Control="Next" Event="NewDialog" Value="VerifyReadyDlg">Installed AND PATCH</Publish>
      <Publish Dialog="VampLicenseDlg" Control="Back" Event="NewDialog" Value="WelcomeDlg">1</Publish>
      <Publish Dialog="VampLicenseDlg" Control="Next" Event="NewDialog" Value="InstallLocationDlg">LicenseAccepted = "1"</Publish>
      <Publish Dialog="InstallLocationDlg" Control="Back" Event="NewDialog" Value="VampLicenseDlg">1</Publish>
      <Publish Dialog="ExitDialog" Control="Finish" Event="EndDialog" Value="Return" Order="999">1</Publish>
      <Publish Dialog="MaintenanceWelcomeDlg" Control="Next" Event="NewDialog" Value="MaintenanceTypeDlg">1</Publish>
      <Publish Dialog="MaintenanceTypeDlg" Control="RepairButton" Event="NewDialog" Value="VerifyReadyDlg">1</Publish>
      <Publish Dialog="MaintenanceTypeDlg" Control="RemoveButton" Event="NewDialog" Value="VerifyReadyDlg">1</Publish>
      <Publish Dialog="MaintenanceTypeDlg" Control="Back" Event="NewDialog" Value="MaintenanceWelcomeDlg">1</Publish>
      <Publish Dialog="VerifyReadyDlg" Control="Back" Event="NewDialog" Value="MaintenanceTypeDlg">Installed AND NOT PATCH</Publish>
      <Publish Dialog="VerifyReadyDlg" Control="Back" Event="NewDialog" Value="WelcomeDlg">Installed AND PATCH</Publish>
      <InstallUISequence>
        <Show Dialog="UserExit" OnExit="cancel">0</Show>
      </InstallUISequence>
      <AdminUISequence>
        <Show Dialog="UserExit" OnExit="cancel">0</Show>
      </AdminUISequence>
      <UIRef Id="WixUI_Common" />

      <Publish Dialog="ExitDialog" Control="Finish" Event="DoAction" Value="SetupBuildTools">WIXUI_EXITDIALOGOPTIONALCHECKBOX = 1 AND NOT Installed</Publish>
    </UI>
  </Product>
</Wix>
"""


def set_fonts(msi):
    database = ctypes.c_ulong()
    view = ctypes.c_ulong()
    library = ctypes.windll.msi
    if library.MsiOpenDatabaseW(msi, ctypes.c_wchar_p(1), ctypes.byref(database)):
        raise RuntimeError("could not open the .msi to set fonts")
    try:
        for style, face in FONTS.items():
            query = f"UPDATE `TextStyle` SET `FaceName` = '{face}' WHERE `TextStyle` = '{style}'"
            if library.MsiDatabaseOpenViewW(database, query, ctypes.byref(view)):
                raise RuntimeError("could not update " + style)
            library.MsiViewExecute(view, 0)
            library.MsiViewClose(view)
            library.MsiCloseHandle(view)
        if library.MsiDatabaseCommit(database):
            raise RuntimeError("could not save the .msi")
    finally:
        library.MsiCloseHandle(database)



    
  




def main():

    options = argparse.ArgumentParser(description="Build the Vamp .msi installer and the VS Code extension.")

    options.add_argument("--version", default="1.0.0", help="version shown by the installer (major.minor.patch)")

    options.add_argument("--skip-compiler", action="store_true", help="reuse Compiler/dist/vamp.exe as it is")

    options.add_argument("--wix", help="folder with candle.exe and light.exe (WiX Toolset 3.14)")

    settings = options.parse_args()

    wix = find_wix(settings.wix)



    if not settings.skip_compiler:

        run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "vamp.spec"], cwd=COMPILER)

    compiler = os.path.join(COMPILER, "dist", "vamp.exe")

    if not os.path.isfile(compiler):

        sys.exit("Compiler/dist/vamp.exe is missing; run without --skip-compiler")



    shutil.rmtree(WORK, ignore_errors=True)

    os.makedirs(RELEASE, exist_ok=True)

    for old in glob.glob(os.path.join(RELEASE, "vamp-lang-*.vsix")):

        os.remove(old)

    vsix = build_vsix(RELEASE)



    payload = os.path.join(WORK, "payload")

    os.makedirs(payload)

    for src in (compiler, vsix, ICON, DATA_ICON, os.path.join(ROOT, "LICENSE"),

                   os.path.join(ROOT, "DOCUMENTATION.md"), os.path.join(ROOT, "README.md")):

        shutil.copy2(src, payload)

    shutil.copytree(os.path.join(ROOT, "Examples"), os.path.join(payload, "Examples"),

                    ignore=shutil.ignore_patterns("*.exe", "*.pdb"))



    make_artwork(WORK)

    make_license_rtf(os.path.join(WORK, "license.rtf"))

    with open(os.path.join(WORK, "choose_install_folder.vbs"), "w", encoding="ascii") as fh:

        fh.write(FOLDER_PICKER_SCRIPT)

    with open(os.path.join(WORK, "run_build_tools.vbs"), "w", encoding="ascii") as fh:

        fh.write(BUILD_TOOLS_SCRIPT)

    src = os.path.join(WORK, "vamp.wxs")

    with open(src, "w", encoding="utf-8") as fh:

        fh.write(make_wxs(payload, settings.version))



    msi = os.path.join(RELEASE, f"Vamp-{settings.version}-x64.msi")

    extensions = ["-ext", "WixUIExtension", "-ext", "WixUtilExtension"]

    run([os.path.join(wix, "candle.exe"), "-nologo", "-arch", "x64", *extensions,

         "-dlicenseRtf=" + os.path.join(WORK, "license.rtf"), "-out",

         os.path.join(WORK, "vamp.wixobj"), src])

    run([os.path.join(wix, "light.exe"), "-nologo", *extensions, "-cultures:en-us",

         "-loc", os.path.join(HERE, "vamp.wxl"),

         "-dWixUILicenseRtf=" + os.path.join(WORK, "license.rtf"),

         "-dWixUIDialogBmp=" + os.path.join(WORK, "dialog.bmp"),

         "-dWixUIBannerBmp=" + os.path.join(WORK, "banner.bmp"),

         "-sice:ICE38", "-sice:ICE64", "-sice:ICE91", "-sice:ICE43", "-sice:ICE57",

         "-spdb", "-out", msi, os.path.join(WORK, "vamp.wixobj")])

    set_fonts(msi)

    print("\ninstaller:", msi)

    print("extension:", vsix)





if __name__ == "__main__":

    main()
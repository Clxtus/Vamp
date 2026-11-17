import json
import os
import sys
import zipfile
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTENSION = os.path.join(ROOT, "vamp-vscode")
INCLUDED = ("package.json", "extension.js", "language-configuration.json", "README.md", "CHANGELOG.md",
            "LICENSE", "LICENSE.md", "LICENSE.txt")
INCLUDED_FOLDERS = ("syntaxes", "icons")

CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension=".json" ContentType="application/json"/>
<Default Extension=".vsixmanifest" ContentType="text/xml"/>
<Default Extension=".js" ContentType="application/javascript"/>
<Default Extension=".md" ContentType="text/markdown"/>
<Default Extension=".png" ContentType="image/png"/>
<Default Extension=".svg" ContentType="image/svg+xml"/>
<Default Extension=".txt" ContentType="text/plain"/>
<Default Extension="" ContentType="text/plain"/>
</Types>
"""


def extension_files():
    files = [name for name in INCLUDED if os.path.isfile(os.path.join(EXTENSION, name))]
    for folder in INCLUDED_FOLDERS:
        for base, _, names in os.walk(os.path.join(EXTENSION, folder)):
            for name in sorted(names):
                files.append(os.path.relpath(os.path.join(base, name), EXTENSION).replace("\\", "/"))
    return files


def manifest(package, files):
    license_file = next((name for name in files if name.startswith("LICENSE")), None)
    properties = {
        "Microsoft.VisualStudio.Code.Engine": package["engines"]["vscode"],
        "Microsoft.VisualStudio.Code.ExtensionDependencies": "",
        "Microsoft.VisualStudio.Code.ExtensionPack": "",
        "Microsoft.VisualStudio.Code.ExtensionKind": "workspace",
        "Microsoft.VisualStudio.Code.LocalizedLanguages": "",
        "Microsoft.VisualStudio.Services.GitHubFlavoredMarkdown": "true",
        "Microsoft.VisualStudio.Services.Content.Pricing": "Free",
    }
    repository = package.get("repository", {}).get("url")
    if repository:
        properties["Microsoft.VisualStudio.Services.Links.Source"] = repository
        properties["Microsoft.VisualStudio.Services.Links.Getstarted"] = repository
        properties["Microsoft.VisualStudio.Services.Links.GitHub"] = repository
    if package.get("bugs", {}).get("url"):
        properties["Microsoft.VisualStudio.Services.Links.Support"] = package["bugs"]["url"]
    if package.get("homepage"):
        properties["Microsoft.VisualStudio.Services.Links.Learn"] = package["homepage"]
    banner = package.get("galleryBanner", {})
    if banner.get("color"):
        properties["Microsoft.VisualStudio.Services.Branding.Color"] = banner["color"]
    if banner.get("theme"):
        properties["Microsoft.VisualStudio.Services.Branding.Theme"] = banner["theme"]
    property_lines = "\n".join(
        f'      <Property Id="{key}" Value="{escape(value, {chr(34): "&quot;"})}" />' for key, value in properties.items())
    assets = [("Microsoft.VisualStudio.Code.Manifest", "extension/package.json")]
    if "README.md" in files:
        assets.append(("Microsoft.VisualStudio.Services.Content.Details", "extension/README.md"))
    if "CHANGELOG.md" in files:
        assets.append(("Microsoft.VisualStudio.Services.Content.Changelog", "extension/CHANGELOG.md"))
    if license_file:
        assets.append(("Microsoft.VisualStudio.Services.Content.License", f"extension/{license_file}"))
    if package.get("icon"):
        assets.append(("Microsoft.VisualStudio.Services.Icons.Default", f"extension/{package['icon']}"))
    asset_lines = "\n".join(f'    <Asset Type="{kind}" Path="{path}" Addressable="true" />' for kind, path in assets)
    extras = ""
    if license_file:
        extras += f"\n    <License>extension/{license_file}</License>"
    if package.get("icon"):
        extras += f"\n    <Icon>extension/{package['icon']}</Icon>"
    return f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="{escape(package['name'])}" Version="{escape(package['version'])}" Publisher="{escape(package['publisher'])}" />
    <DisplayName>{escape(package['displayName'])}</DisplayName>
    <Description xml:space="preserve">{escape(package['description'])}</Description>
    <Tags>{escape(','.join(package.get('keywords', [])))}</Tags>
    <Categories>{escape(','.join(package.get('categories', [])))}</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
{property_lines}
    </Properties>{extras}
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code" />
  </Installation>
  <Dependencies />
  <Assets>
{asset_lines}
  </Assets>
</PackageManifest>
"""


def build_vsix(output_folder):
    with open(os.path.join(EXTENSION, "package.json"), encoding="utf-8") as fh:
        package = json.load(fh)
    files = extension_files()
    os.makedirs(output_folder, exist_ok=True)
    target = os.path.join(output_folder, f"{package['name']}-{package['version']}.vsix")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("extension.vsixmanifest", manifest(package, files))
        for name in files:
            archive.write(os.path.join(EXTENSION, name), f"extension/{name}")
    return target


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "release")
    print(build_vsix(folder))

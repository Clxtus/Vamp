# Privacy Policy

## Data Collection & Telemetry
**Vamp** (both the `vamp.exe` compiler/runtime and the Windows `.msi` installer) does **not** collect, store, track, or transmit any personal data, usage analytics, or telemetry.

## Network Communication
Vamp does not initiate background network connections on its own. Network activity occurs only when explicitly triggered by the user:
- **Compiler & Runtime (`vamp.exe`):** Performs no network requests unless the user's own Vamp program explicitly calls functions from the `net` standard library (such as `net.Http_Get`, `net.Download`, or TCP socket functions).
- **Optional Build Tools Setup (`vamp.exe setup`):** If the user leaves the optional build-tools checkbox enabled at the end of installation (or manually runs `vamp setup`), the tool checks for and downloads official LLVM / C++ build tools needed to compile native executables.
- **Documentation Links:** Opening documentation shortcuts or links navigates to GitHub in the user's default web browser.

## Local System Changes
During installation, the Windows installer writes files only to the user-selected installation directory (`%LocalAppData%\Programs\Vamp` by default), registers `.vp` and `.vpdata` file associations under `HKEY_CURRENT_USER`, adds the installation folder to the user `PATH`, and creates Start Menu shortcuts. All changes are reverted automatically when uninstalling Vamp via Windows Settings or the included uninstaller.
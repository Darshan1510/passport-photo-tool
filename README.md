# Passport Photo Tool

A small desktop app that helps you edit your photo a regular photo to create a passport-size photo for Indian passport application. It removes the background, evens the lighting, detects your face, and crops to the required 630x810 px dimensions.

## Install

### macOS

Open Terminal (Spotlight → type "Terminal" → Enter) and paste:

```sh
curl -LsSf https://raw.githubusercontent.com/smitkiri/passport-photo-tool/main/install.sh | sh
```

This downloads the latest release, installs it to `~/Applications`, strips the macOS quarantine flag (so Gatekeeper doesn't block the unsigned app), and launches it. After the first install, you can open the app normally from Launchpad or Spotlight by searching for "PassportPhotoTool".

To update, re-run the same command.

**Why is this needed?** The app isn't signed with an Apple Developer ID (that costs me $99/year), so double-clicking the downloaded `.app` shows a "damaged" or "unidentified developer" dialog. Stripping the quarantine attribute is the standard workaround and doesn't require paying Apple.

**Want to inspect the script before running it?** You should. View it here: [install.sh](./install.sh).

### Windows

Download `PassportPhotoTool-Windows.zip` from the [latest release](https://github.com/smitkiri/passport-photo-tool/releases/latest), unzip it, and run `PassportPhotoTool.exe`.

## Troubleshooting (macOS)

**"PassportPhotoTool is damaged and can't be opened"** after installing manually (not via the script): the quarantine attribute wasn't removed. Run:

```sh
xattr -cr ~/Applications/PassportPhotoTool.app
```

**Installer says "Unsupported architecture"**: the installer only supports `arm64` (Apple Silicon) and `x86_64` (Intel) Macs. If you're seeing this on a supported Mac, please open an issue.

**Can't find the app after install**: it's in `~/Applications` (your personal Applications folder, not the system one). Launchpad and Spotlight both index it.

## Development

```sh
uv sync
uv run main.py
```

### Building

```sh
make build-mac        # macOS .app bundle
make build-windows    # Windows .exe directory
```

Releases are built automatically by GitHub Actions on pushing a `v*` tag.

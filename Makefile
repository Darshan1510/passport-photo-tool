# Build targets for Passport Photo Tool.
#
# Usage:
#   make build-mac        # Build the macOS .app bundle into dist/
#   make build-windows    # Build the Windows .exe directory into dist/
#   make clean            # Remove build artifacts

PYI := uv run pyinstaller
NAME := PassportPhotoTool
ENTRY := main.py

COLLECT := \
	--collect-all uvicorn \
	--collect-all fastapi \
	--collect-all webview \
	--collect-all rembg \
	--collect-all onnxruntime \
	--collect-data cv2 \
	--copy-metadata pymatting

.PHONY: build-mac build-windows build-mac-ci build-windows-ci clean

build-mac:
	$(PYI) --noconfirm --onedir --windowed \
		--add-data "static:static" \
		$(COLLECT) \
		--name "$(NAME)" \
		--icon assets/app.icns \
		$(ENTRY)

build-windows:
	$(PYI) --noconfirm --onedir --windowed \
		--add-data "static;static" \
		$(COLLECT) \
		--name "$(NAME)" \
		--icon assets/app.ico
		$(ENTRY)

build-mac-ci: build-mac
	hdiutil create -volname "$(NAME)" -srcfolder "dist/$(NAME).app" -ov -format UDZO "$(NAME).dmg"

build-windows-ci: build-windows
	powershell Compress-Archive -Path "dist/$(NAME)" -DestinationPath "$(NAME)-Windows.zip" -Force

clean:
	rm -rf build/ dist/

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
	--collect-all onnxruntime

.PHONY: build-mac build-windows clean

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
		$(ENTRY)

clean:
	rm -rf build dist

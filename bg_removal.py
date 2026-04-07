"""Background removal: local (rembg), remote (remove.bg), and passthrough.

The local path uses rembg's `u2net_human_seg` ONNX model, cached at the
standard rembg location (`~/.u2net/`). We download the model ourselves (rather
than letting rembg fetch it on first use) so we can report progress to the UI.
"""
import io
import threading
from pathlib import Path
from typing import Optional, TypedDict

import requests as http_requests
from PIL import Image


MODEL_NAME = "u2net_human_seg"
# Verified against rembg.sessions.u2net_human_seg.U2netHumanSegSession.
MODEL_URL = (
    "https://github.com/danielgatis/rembg/releases/download/v0.0.0/"
    "u2net_human_seg.onnx"
)
_MODEL_DIR = Path.home() / ".u2net"
_MODEL_PATH = _MODEL_DIR / f"{MODEL_NAME}.onnx"


class DownloadState(TypedDict):
    state: str  # "idle" | "downloading" | "done" | "error"
    bytes: int
    total: int
    error: Optional[str]


_download_lock = threading.Lock()
_download_state: DownloadState = {
    "state": "idle",
    "bytes": 0,
    "total": 0,
    "error": None,
}

# Cached rembg session. Lazy-initialized on first local removal in a process.
_rembg_session = None


# --- Model cache helpers ---


def model_cache_path() -> Path:
    return _MODEL_PATH


def is_model_cached() -> bool:
    return _MODEL_PATH.exists() and _MODEL_PATH.stat().st_size > 0


def get_download_state() -> DownloadState:
    with _download_lock:
        return dict(_download_state)


def _set_state(**kwargs) -> None:
    with _download_lock:
        _download_state.update(kwargs)


# --- Download ---


def start_download() -> bool:
    """Begin downloading the model in a background thread.

    Returns True if a download was started, False if one was already in
    progress.
    """
    with _download_lock:
        if _download_state["state"] == "downloading":
            return False
        _download_state.update(
            {"state": "downloading", "bytes": 0, "total": 0, "error": None}
        )
    threading.Thread(target=_download_worker, daemon=True).start()
    return True


def _download_worker() -> None:
    tmp_path = _MODEL_PATH.with_suffix(".onnx.partial")
    try:
        _MODEL_DIR.mkdir(parents=True, exist_ok=True)
        with http_requests.get(MODEL_URL, stream=True, timeout=30) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))
            _set_state(total=total)
            downloaded = 0
            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    _set_state(bytes=downloaded)
        tmp_path.replace(_MODEL_PATH)
        _set_state(state="done", bytes=downloaded, total=total or downloaded)
    except Exception as e:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        _set_state(state="error", error=str(e))


# --- Background removal ---


def _composite_on_white(img: Image.Image) -> Image.Image:
    if img.mode != "RGBA":
        return img.convert("RGB")
    white = Image.new("RGB", img.size, (255, 255, 255))
    white.paste(img, mask=img.split()[3])
    return white


def remove_background_local(input_path: Path, output_path: Path) -> None:
    """Run rembg locally. Requires the model to already be cached."""
    global _rembg_session
    from rembg import new_session, remove  # lazy import: keeps startup fast

    if not is_model_cached():
        raise RuntimeError("Local model is not cached. Download it first.")
    if _rembg_session is None:
        _rembg_session = new_session(MODEL_NAME)

    with open(input_path, "rb") as f:
        data = f.read()
    try:
        result_bytes = remove(data, session=_rembg_session)
    except Exception as e:
        # Likely a corrupt model file. Delete it so the user can re-download.
        _rembg_session = None
        try:
            _MODEL_PATH.unlink(missing_ok=True)
        except Exception:
            pass
        raise RuntimeError(
            f"Local background removal failed (model may be corrupt; "
            f"please re-download): {e}"
        )

    fg = Image.open(io.BytesIO(result_bytes)).convert("RGBA")
    result = _composite_on_white(fg)
    result.save(output_path, "PNG")


def remove_background_remote(
    input_path: Path, output_path: Path, api_key: str
) -> None:
    """Call remove.bg API. Caller is responsible for providing the api_key."""
    with open(input_path, "rb") as f:
        response = http_requests.post(
            "https://api.remove.bg/v1.0/removebg",
            files={"image_file": f},
            data={"size": "auto"},
            headers={"X-Api-Key": api_key},
        )
    if response.status_code != 200:
        raise RuntimeError(f"remove.bg API error: {response.status_code}")
    fg = Image.open(io.BytesIO(response.content)).convert("RGBA")
    result = _composite_on_white(fg)
    result.save(output_path, "PNG")


def passthrough(input_path: Path, output_path: Path) -> None:
    """Skip mode: copy the input to the output, normalized to RGB PNG."""
    img = Image.open(input_path).convert("RGB")
    img.save(output_path, "PNG")

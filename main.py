import os
import io
import uuid
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import requests as http_requests
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

app = FastAPI()

TMP_DIR = Path("tmp")
TMP_DIR.mkdir(exist_ok=True)


def _session_dir(session_id: str) -> Path:
    d = TMP_DIR / session_id
    d.mkdir(exist_ok=True)
    return d


# --- Image Processing Functions ---

def apply_clahe(img: np.ndarray, clip_limit: float = 2.0) -> np.ndarray:
    """Apply CLAHE to the L channel in LAB color space for even lighting."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    l = clahe.apply(l)
    lab = cv2.merge([l, a, b])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def detect_face(img: np.ndarray) -> tuple[int, int, int, int] | None:
    """Detect the largest face using Haar cascades. Returns (x, y, w, h) or None."""
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    if len(faces) == 0:
        return None
    faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
    x, y, w, h = faces[0]
    return (int(x), int(y), int(w), int(h))


def calculate_crop_region(
    face_box: tuple[int, int, int, int],
    img_w: int,
    img_h: int,
    target_face_pct: float = 0.825,
) -> tuple[int, int, int, int]:
    """Calculate a 7:9 crop region where the head is ~80-85% of the crop height."""
    fx, fy, fw, fh = face_box
    ASPECT = 630 / 810

    head_height = fh * 1.3
    crop_h = head_height / target_face_pct
    crop_w = crop_h * ASPECT

    face_cx = fx + fw / 2
    crop_x = face_cx - crop_w / 2

    face_cy = fy + fh / 2
    crop_y = face_cy - crop_h * 0.42

    crop_x = max(0, min(crop_x, img_w - crop_w))
    crop_y = max(0, min(crop_y, img_h - crop_h))
    crop_w = min(crop_w, img_w - crop_x)
    crop_h = min(crop_h, img_h - crop_y)

    return (int(crop_x), int(crop_y), int(crop_w), int(crop_h))


def composite_on_white(img: Image.Image) -> Image.Image:
    """Composite an RGBA image onto a white RGB background."""
    if img.mode != "RGBA":
        return img.convert("RGB")
    white = Image.new("RGB", img.size, (255, 255, 255))
    white.paste(img, mask=img.split()[3])
    return white


def resize_to_passport(img: Image.Image) -> Image.Image:
    """Resize image to exactly 630x810 pixels."""
    return img.convert("RGB").resize((630, 810), Image.LANCZOS)


# --- API Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def index():
    index_path = Path("static/index.html")
    return HTMLResponse(index_path.read_text())


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    session = _session_dir(session_id)
    ext = Path(file.filename).suffix or ".jpg"
    original_path = session / f"original{ext}"
    with open(original_path, "wb") as f:
        content = await file.read()
        f.write(content)
    return {"session_id": session_id}


@app.get("/image/{session_id}/{step}")
async def get_image(session_id: str, step: str):
    session = TMP_DIR / session_id
    if not session.exists():
        raise HTTPException(404, "Session not found")
    matches = list(session.glob(f"{step}.*"))
    if not matches:
        raise HTTPException(404, f"Image '{step}' not found")
    return FileResponse(matches[0])


@app.post("/remove-background")
async def remove_background(body: dict):
    session_id = body["session_id"]
    session = _session_dir(session_id)
    original = list(session.glob("original.*"))
    if not original:
        raise HTTPException(404, "Original image not found")

    api_key = os.environ.get("REMOVE_BG_API_KEY")
    if not api_key:
        raise HTTPException(500, "REMOVE_BG_API_KEY environment variable not set")

    with open(original[0], "rb") as f:
        response = http_requests.post(
            "https://api.remove.bg/v1.0/removebg",
            files={"image_file": f},
            data={"size": "auto"},
            headers={"X-Api-Key": api_key},
        )

    if response.status_code != 200:
        raise HTTPException(502, f"remove.bg API error: {response.status_code}")

    fg = Image.open(io.BytesIO(response.content)).convert("RGBA")
    result = composite_on_white(fg)
    out_path = session / "no_bg.png"
    result.save(out_path, "PNG")
    return {"status": "ok"}


@app.post("/fix-lighting")
async def fix_lighting(body: dict):
    session_id = body["session_id"]
    session = _session_dir(session_id)
    no_bg = list(session.glob("no_bg.*"))
    if not no_bg:
        raise HTTPException(404, "Background-removed image not found")

    src = cv2.imread(str(no_bg[0]))

    if body.get("skip", False):
        out_path = session / "lighting.png"
        cv2.imwrite(str(out_path), src)
        return {"status": "ok"}

    clip_limit = body.get("clip_limit", 2.0)
    result = apply_clahe(src, clip_limit=clip_limit)
    out_path = session / "lighting.png"
    cv2.imwrite(str(out_path), result)
    return {"status": "ok"}


@app.post("/detect-face")
async def detect_face_endpoint(body: dict):
    session_id = body["session_id"]
    session = _session_dir(session_id)
    lighting = list(session.glob("lighting.*"))
    if not lighting:
        raise HTTPException(404, "Lighting-corrected image not found")

    img = cv2.imread(str(lighting[0]))
    face_box = detect_face(img)
    h, w = img.shape[:2]

    suggested_crop = None
    if face_box is not None:
        suggested_crop = list(calculate_crop_region(face_box, w, h))

    return {
        "face_box": list(face_box) if face_box is not None else None,
        "suggested_crop": suggested_crop,
        "image_size": [w, h],
    }


@app.post("/crop")
async def crop(body: dict):
    session_id = body["session_id"]
    session = _session_dir(session_id)
    lighting = list(session.glob("lighting.*"))
    if not lighting:
        raise HTTPException(404, "Lighting-corrected image not found")

    img = Image.open(lighting[0])
    x, y, w, h = body["x"], body["y"], body["w"], body["h"]
    cropped = img.crop((x, y, x + w, y + h))
    out_path = session / "cropped.png"
    cropped.save(out_path, "PNG")
    return {"status": "ok"}


@app.post("/export")
async def export(body: dict):
    session_id = body["session_id"]
    session = _session_dir(session_id)
    cropped = list(session.glob("cropped.*"))
    if not cropped:
        raise HTTPException(404, "Cropped image not found")

    img = Image.open(cropped[0])
    result = resize_to_passport(img)
    out_path = session / "final.jpg"
    result.save(out_path, "JPEG", quality=95)
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

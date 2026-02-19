from __future__ import annotations

import qrcode
from PIL import Image

def make_qr_image(data: str, *, box_size: int = 4, border: int = 2) -> Image.Image:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=int(box_size),
        border=int(border),
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img.convert("RGB")

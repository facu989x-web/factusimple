from __future__ import annotations

import win32print
import win32ui
import win32con

from PIL import Image, ImageDraw, ImageFont, ImageWin


class TicketPrinter:
    """
    Modos:
      - mode="escpos": manda RAW ESC/POS (ideal térmicas).
      - mode="gdi": imprime con Windows GDI (sirve para Microsoft Print to PDF y cualquier impresora con driver).
    """

    def __init__(self, printer_name_contains: str | None = None, mode: str = "escpos"):
        self.printer_name = self._find_printer(printer_name_contains)
        if not self.printer_name:
            raise RuntimeError("No se encontró impresora")
        self.mode = (mode or "escpos").lower().strip()
        print("Usando impresora:", self.printer_name, "| mode:", self.mode)

    def _find_printer(self, contains: str | None):
        default = win32print.GetDefaultPrinter()

        if not contains:
            return default

        printers = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
        for p in printers:
            name = p[2]
            if contains.lower() in name.lower():
                return name
        return default

    # ---------------- RAW / ESC-POS ----------------
    def _raw_print(self, data: bytes):
        hPrinter = win32print.OpenPrinter(self.printer_name)
        try:
            win32print.StartDocPrinter(hPrinter, 1, ("Ticket", None, "RAW"))
            try:
                win32print.StartPagePrinter(hPrinter)
                win32print.WritePrinter(hPrinter, data)
                win32print.EndPagePrinter(hPrinter)
            finally:
                win32print.EndDocPrinter(hPrinter)
        finally:
            win32print.ClosePrinter(hPrinter)

    def print_text(self, text: str):
        if self.mode == "gdi":
            img = self._render_ticket_image(text, None, max_width_px=760)
            self._gdi_print_image(img)
            return

        INIT = b"\x1b\x40"
        CUT = b"\x1d\x56\x41\x10"  # corte parcial
        data = INIT + text.encode("cp850", errors="replace") + CUT
        self._raw_print(data)

    # ---------------- IMAGEN (ESC/POS raster) ----------------
    def _image_to_escpos_raster(self, img: Image.Image) -> bytes:
        """
        Convierte imagen a comando ESC/POS raster: GS v 0 (monocromo).
        """
        img = img.convert("L")
        img = img.point(lambda p: 0 if p < 160 else 255, mode="1")

        width, height = img.size
        if width % 8 != 0:
            new_w = width + (8 - width % 8)
            padded = Image.new("1", (new_w, height), 1)  # 1=blanco
            padded.paste(img, (0, 0))
            img = padded
            width = new_w

        width_bytes = width // 8
        xL = width_bytes & 0xFF
        xH = (width_bytes >> 8) & 0xFF
        yL = height & 0xFF
        yH = (height >> 8) & 0xFF

        pixels = img.load()
        data = bytearray()
        for y in range(height):
            for xb in range(width_bytes):
                b = 0
                for bit in range(8):
                    x = xb * 8 + bit
                    if pixels[x, y] == 0:
                        b |= (1 << (7 - bit))
                data.append(b)

        cmd = b"\x1d\x76\x30\x00" + bytes([xL, xH, yL, yH]) + bytes(data)
        return cmd

    def print_text_and_qr(self, text: str, qr_img: Image.Image):
        if self.mode == "gdi":
            img = self._render_ticket_image(text, qr_img, max_width_px=760)
            self._gdi_print_image(img)
            return

        INIT = b"\x1b\x40"
        ALIGN_CENTER = b"\x1b\x61\x01"
        ALIGN_LEFT = b"\x1b\x61\x00"
        LF = b"\n"
        CUT = b"\x1d\x56\x41\x10"

        raster = self._image_to_escpos_raster(qr_img)

        payload = INIT
        payload += text.encode("cp850", errors="replace")
        payload += LF
        payload += ALIGN_CENTER
        payload += raster
        payload += LF
        payload += ALIGN_LEFT
        payload += LF
        payload += CUT

        self._raw_print(payload)

    # ---------------- GDI helpers ----------------
    def _get_monospace_font(self, size: int = 22):
        try:
            return ImageFont.truetype("consola.ttf", size=size)  # Consolas
        except Exception:
            try:
                return ImageFont.truetype("cour.ttf", size=size)  # Courier New
            except Exception:
                return ImageFont.load_default()

    def _render_ticket_image(self, text: str, qr_img: Image.Image | None, *, max_width_px: int = 760) -> Image.Image:
        """
        Renderiza texto + QR en una imagen blanca (1-bit) para imprimir por GDI.
        max_width_px más grande -> en PDF no sale "micro".
        """
        font = self._get_monospace_font(22)
        line_gap = 8
        pad = 24

        lines = (text or "").splitlines() if text else []
        dummy = Image.new("RGB", (max_width_px, 10), "white")
        draw = ImageDraw.Draw(dummy)

        y = pad
        for ln in lines:
            bbox = draw.textbbox((0, 0), ln, font=font)
            h = bbox[3] - bbox[1]
            y += h + line_gap

        if qr_img is not None:
            target = 320
            y += 12 + target + 12

        total_h = y + pad
        img = Image.new("RGB", (max_width_px, total_h), "white")
        draw = ImageDraw.Draw(img)

        y = pad
        for ln in lines:
            draw.text((pad, y), ln, fill="black", font=font)
            bbox = draw.textbbox((0, 0), ln, font=font)
            h = bbox[3] - bbox[1]
            y += h + line_gap

        if qr_img is not None:
            qr = qr_img.convert("RGB").resize((320, 320), Image.NEAREST)
            x = (max_width_px - 320) // 2
            y += 12
            img.paste(qr, (x, y))
            y += 320 + 12

        # b/n
        img = img.convert("L")
        img = img.point(lambda p: 0 if p < 200 else 255, mode="1")
        return img

    def _gdi_print_image(self, img: Image.Image):
        """
        Imprime una imagen con Windows GDI. Evita SetBitmapBits (que falla en algunas builds).
        Usa ImageWin.Dib.draw sobre el DC.
        """
        hdc = win32ui.CreateDC()
        hdc.CreatePrinterDC(self.printer_name)

        # resolución imprimible
        HORZRES = hdc.GetDeviceCaps(win32con.HORZRES)
        VERTRES = hdc.GetDeviceCaps(win32con.VERTRES)

        # márgenes (en pixels del device)
        margin_x = int(HORZRES * 0.05)
        margin_y = int(VERTRES * 0.03)

        img_rgb = img.convert("RGB")
        w, h = img_rgb.size

        max_w = max(200, HORZRES - margin_x * 2)
        scale = min(1.0, max_w / float(w))
        dst_w = int(w * scale)
        dst_h = int(h * scale)

        x = (HORZRES - dst_w) // 2
        y = margin_y

        hdc.StartDoc("Ticket")
        hdc.StartPage()
        try:
            dib = ImageWin.Dib(img_rgb)
            dib.draw(hdc.GetHandleOutput(), (x, y, x + dst_w, y + dst_h))
        finally:
            hdc.EndPage()
            hdc.EndDoc()
            hdc.DeleteDC()

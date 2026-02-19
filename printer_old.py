import win32print
import win32ui
from datetime import datetime

def _line(text: str, width: int = 32) -> str:
  return (text[:width]).ljust(width)

def _find_printer(name_contains: str) -> str:
  printers = [p[2] for p in win32print.EnumPrinters(
    win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
  )]
  for p in printers:
    if name_contains.lower() in p.lower():
      return p
  raise RuntimeError(f"No encontré impresora que contenga '{name_contains}'. Encontradas: {printers}")

def print_ticket(printer_name_contains: str, *,
                 razon_social: str, cuit: str,
                 pv: int, cbte_nro: int,
                 cae: str, cae_vto: str,
                 doc_tipo: int, doc_nro: str,
                 total: float, items: list[dict]) -> None:
  target = _find_printer(printer_name_contains)

  dc = win32ui.CreateDC()
  dc.CreatePrinterDC(target)
  dc.StartDoc("Ticket Factura C")
  dc.StartPage()

  x = 50
  y = 50
  lh = 18

  def draw(t: str, bold: bool = False):
    nonlocal y
    font = win32ui.CreateFont({
      "name": "Consolas",
      "height": 18 if not bold else 20,
      "weight": 700 if bold else 400,
    })
    dc.SelectObject(font)
    dc.TextOut(x, y, t)
    y += lh

  draw(_line(razon_social), bold=True)
  draw(_line(f"CUIT: {cuit}"))
  draw(_line("FACTURA C"))
  draw(_line(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
  draw(_line(f"PV {pv:04d} - NRO {cbte_nro:08d}"))
  draw(_line("-" * 32))

  if doc_tipo == 99:
    draw(_line("Cliente: Consumidor Final"))
  else:
    draw(_line(f"Doc: {doc_nro} (tipo {doc_tipo})"))

  draw(_line("-" * 32))
  for it in items:
    draw(_line(str(it["name"])))
    draw(_line(f"{float(it['qty']):g} x {float(it['price']):.2f} = {float(it['subtotal']):.2f}"))
  draw(_line("-" * 32))
  draw(_line(f"TOTAL: {float(total):.2f}"), bold=True)
  draw(_line(f"CAE: {cae}"))
  draw(_line(f"VTO CAE: {cae_vto}"))
  draw(_line("-" * 32))
  draw(_line("Gracias!"))

  for _ in range(6):
    draw("")

  dc.EndPage()
  dc.EndDoc()

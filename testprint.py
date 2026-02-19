from printer import TicketPrinter

p = TicketPrinter("XP-58")

data = (
    "PROBANDO ESC/POS\n"
    "Si esto sale en NEGRITA, estamos ok.\n\n"
)

# probá negrita (ESC E n)
# ON:  1B 45 01
# OFF: 1B 45 00
raw = b"\x1b\x40" + b"Normal\n" + b"\x1b\x45\x01" + "NEGRITA\n".encode("cp850") + b"\x1b\x45\x00" + b"\n\n" + b"\x1d\x56\x41\x10"

# imprimimos raw directo usando el método interno:
p._raw_print(raw)

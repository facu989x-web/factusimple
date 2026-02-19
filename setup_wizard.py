
from __future__ import annotations

import hashlib
from PySide6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox,
    QSpinBox, QMessageBox
)

from db import get_setting, set_setting, set_template

def _hash_pin(pin: str) -> str:
    return hashlib.sha256(("POSPIN:" + pin).encode("utf-8")).hexdigest()

def _list_printers_safe() -> list[str]:
    try:
        import win32print
        printers = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
        names = [p[2] for p in printers]
        try:
            d = win32print.GetDefaultPrinter()
            if d in names:
                names.remove(d)
                names.insert(0, d)
        except Exception:
            pass
        return names
    except Exception:
        return []

class SetupWizard(QWizard):
    def __init__(self, *, db_path: str):
        super().__init__()
        self.db_path = db_path
        self.setWindowTitle("Asistente de instalación (RunOnce)")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(760, 520)

        self.addPage(PagePin(db_path))
        self.addPage(PagePrint(db_path))
        self.addPage(PageTicket(db_path))
        self.addPage(PageFinish(db_path))

class PagePin(QWizardPage):
    def __init__(self, db_path: str):
        super().__init__()
        self.db_path = db_path
        self.setTitle("PIN de administrador")
        self.setSubTitle("Se configura una sola vez. Se puede cambiar luego desde Configuración.")

        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.p1 = QLineEdit(); self.p1.setEchoMode(QLineEdit.Password)
        self.p2 = QLineEdit(); self.p2.setEchoMode(QLineEdit.Password)

        form.addRow("PIN:", self.p1)
        form.addRow("Repetir:", self.p2)
        lay.addLayout(form)
        lay.addWidget(QLabel("Recomendado: 4 a 8 dígitos."))

    def validatePage(self) -> bool:
        p1 = self.p1.text().strip()
        p2 = self.p2.text().strip()
        if not (p1.isdigit() and 4 <= len(p1) <= 8):
            QMessageBox.warning(self, "PIN inválido", "El PIN debe ser numérico (4 a 8 dígitos).")
            return False
        if p1 != p2:
            QMessageBox.warning(self, "PIN", "Los PIN no coinciden.")
            return False
        set_setting(self.db_path, "security.admin_pin_hash", _hash_pin(p1))
        return True

class PagePrint(QWizardPage):
    def __init__(self, db_path: str):
        super().__init__()
        self.db_path = db_path
        self.setTitle("Impresión")
        self.setSubTitle("Elegí impresora, modo y ancho/columnas.")

        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.cmb_printer = QComboBox()
        printers = _list_printers_safe()
        self.cmb_printer.addItem("(predeterminada)")
        for p in printers:
            self.cmb_printer.addItem(p)

        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["escpos", "gdi"])

        self.sp_cols = QSpinBox()
        self.sp_cols.setRange(16, 64)
        self.sp_cols.setValue(int(get_setting(db_path, "ticket.max_cols", "32") or "32"))

        form.addRow("Impresora:", self.cmb_printer)
        form.addRow("Modo:", self.cmb_mode)
        form.addRow("Columnas ticket:", self.sp_cols)
        lay.addLayout(form)

    def validatePage(self) -> bool:
        pr = self.cmb_printer.currentText().strip()
        if pr == "(predeterminada)":
            pr = ""
        set_setting(self.db_path, "print.printer_name_contains", pr)
        set_setting(self.db_path, "print.mode", self.cmb_mode.currentText().strip())
        set_setting(self.db_path, "ticket.max_cols", str(int(self.sp_cols.value())))
        return True

class PageTicket(QWizardPage):
    def __init__(self, db_path: str):
        super().__init__()
        self.db_path = db_path
        self.setTitle("Textos del ticket")
        self.setSubTitle("Mandamiento #1: TODO string se guarda en DB y es personalizable.")

        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.fant = QLineEdit("LocutorioWEB")
        self.inicio = QLineEdit("Inicio actividades: 01/09/2009")
        self.addr = QLineEdit("Av. Directorio 2015")
        self.city = QLineEdit("C.P. 1406 - CABA")
        self.defensa = QLineEdit("TEL 147 CABA PROTECCION AL CONSUMIDOR")

        form.addRow("Nombre fantasía:", self.fant)
        form.addRow("Inicio actividades:", self.inicio)
        form.addRow("Dirección:", self.addr)
        form.addRow("CP/Ciudad:", self.city)
        form.addRow("Defensa consumidor:", self.defensa)
        lay.addLayout(form)

    def validatePage(self) -> bool:
        set_template(self.db_path, "fantasy_name", self.fant.text().strip() or "Comercio")
        set_template(self.db_path, "start_activities_line", self.inicio.text().strip())
        set_template(self.db_path, "address_line", self.addr.text().strip())
        set_template(self.db_path, "cp_city_line", self.city.text().strip())
        set_template(self.db_path, "consumer_protection_line", self.defensa.text().strip())
        return True

class PageFinish(QWizardPage):
    def __init__(self, db_path: str):
        super().__init__()
        self.db_path = db_path
        self.setTitle("Finalizar")
        self.setSubTitle("Listo. Se guardará todo y no volverá a aparecer este asistente.")

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Click en Finalizar para empezar a usar el sistema."))

    def validatePage(self) -> bool:
        set_setting(self.db_path, "setup.done", "1")
        return True

"""USB Burning Tool V2.2.4 — диалог 102 из ресурсов exe, строки LangEn.dll."""

import os
import re
import signal
import subprocess
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QInputDialog,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from burn_tool.engine import burn_cmd, burn_percent, image_part_sizes, partition_names, usb_connected, usb_devices

def _assets_dir() -> Path:
    import sys

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parents[1] / "assets"


ASSETS = _assets_dir()
# DLGTEMPLATE 467x280, MS Shell Dlg 12pt → пиксели как MapDialogRect ~2x
DU = 2


def du(v: int) -> int:
    return v * DU


NOTICE = (
    "1.Make sure the devices and the hub is connected;\n"
    '2.Select "File"-"Import image" to load burning image package;\n'
    "3.Select burning configuration;\n"
    '4.Click "Start";\n'
    '5.Before close the tool, you need to pull out devices then click "Stop".\n'
    '6.Please click "stop" && close tool before you pull out a outside hub.'
)


class BurnWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("USB_Burning_Tool_V2.2.4")
        icon = ASSETS / "ubt_3_5.png"
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))
        self.image: Path | None = None
        self.parts = "all"
        self.password = ""
        self.temp_c = 0
        self._burn_failed = False
        self._parts: list[tuple[str, int]] = []
        self._writing = ""
        self._span: tuple[int, int, int] | None = None
        self._span_at = 0
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick)
        self._elapsed = 0
        self.proc: QProcess | None = None
        self.ok_n = 0
        self.err_n = 0
        self._build_menu()
        self._build_client()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_usb)
        self.timer.start(2000)
        self.refresh_usb()

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_m = bar.addMenu("File")
        file_m.addAction("Import image", self.import_image)
        file_m.addAction("CheckImg", self.check_image)
        file_m.addAction("Exit", self.close)
        lang = bar.addMenu("Language")
        self.lang_actions = []
        for name in ("中文（简体）", "English", "中文（傳統）"):
            act = lang.addAction(name)
            act.setCheckable(True)
            act.triggered.connect(lambda _=False, n=name: self.set_language(n))
            self.lang_actions.append(act)
        self.lang_actions[1].setChecked(True)
        self.lang = "English"
        view = bar.addMenu("View")
        view.addAction("Select...", self.select_parts)
        view.addAction("Temperature setting", self.temperature)
        view.addAction("InPut Password", self.input_password)
        self.act_ddr = view.addAction("Erase ddr para")
        self.act_ddr.setCheckable(True)
        view.addAction("Enable Erase Key", self.enable_key)
        about = bar.addMenu("About")
        about.addAction("Help", lambda: self.open_doc("Amlogic USB Burning Tool V2 Guide V1.0.doc"))
        about.addAction("About USB_Burning_Tool", self.about)
        about.addAction("Key Help", lambda: self.open_doc("AmlKey Burning Configuration Format.doc"))
        about.addAction("Burning Key Instruction", lambda: self.open_doc("Amlogic Burning Key Instruction.doc"))
        bar.addMenu("Upgrade").addAction("Online Upgrade", self.upgrade)

    def _table(self, parent, cols, bg: str) -> QTableWidget:
        table = QTableWidget(0, len(cols), parent)
        table.setHorizontalHeaderLabels(cols)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setShowGrid(True)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setFixedHeight(22)
        table.setFont(QFont("Tahoma", 8))
        table.setStyleSheet(
            "QTableWidget { background: %s; color: #000; gridline-color: #b0b0b0; border: 1px solid #7a7a7a; }"
            "QHeaderView::section { background: #f0f0f0; color: #000; border: 1px solid #d0d0d0;"
            " padding-left: 4px; font-weight: normal; }" % bg
        )
        return table

    def _build_client(self) -> None:
        # диалог 102: 467x280 DU. Живое окно: жёлтый грид сверху, белый лог снизу, статусбар.
        host = QWidget()
        host.setFixedSize(du(467), du(280))
        host.setStyleSheet(
            "QWidget { background: #f0f0f0; color: #000; }"
            "QPushButton { background: #e1e1e1; border: 1px solid #707070; padding: 0; }"
            "QPushButton:pressed { background: #b0b0b0; border-style: inset; padding-top: 2px; }"
            "QPushButton:disabled { color: #808080; background: #ececec; }"
            "QCheckBox { spacing: 2px; }"
            "QGroupBox { border: 1px solid #d0d0d0; margin-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 6px; padding: 0 2px; }"
            "QComboBox { background: #fff; border: 1px solid #7a7a7a; }"
        )
        self.setCentralWidget(host)
        font = QFont("Tahoma", 8)

        self.grid = self._table(host, ["Device ID", "Status", "Time", "Statistic"], "#F0F0CE")
        self.grid.setGeometry(du(7), du(7), du(338), du(156))
        self.grid.setColumnWidth(0, 72)
        self.grid.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.grid.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.grid.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.grid.setColumnWidth(2, 48)
        self.grid.setColumnWidth(3, 52)

        self.btn_start = QPushButton("Start", host)
        self.btn_start.setGeometry(du(351), du(7), du(41), du(29))
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self.toggle_burn)
        self.btn_refresh = QPushButton("Refresh", host)
        self.btn_refresh.setGeometry(du(403), du(7), du(41), du(29))
        self.btn_refresh.clicked.connect(self.refresh_usb)

        QGroupBox("Configuration", host).setGeometry(du(351), du(39), du(109), du(68))
        self.erase = QCheckBox("Erase flash", host)
        self.erase.setGeometry(du(356), du(49), du(90), du(12))
        self.erase.setChecked(True)
        self.erase_mode = QComboBox(host)
        self.erase_mode.setGeometry(du(363), du(60), du(90), du(14))
        self.erase_mode.addItems(
            ["Normal erase", "Force erase", "Erase all(Include Key)"]
        )
        self.erase_bl = QCheckBox("Erase bootloader", host)
        self.erase_bl.setGeometry(du(356), du(73), du(100), du(12))
        self.erase_bl.setChecked(True)
        self.reset = QCheckBox("Reset after success", host)
        self.reset.setGeometry(du(356), du(84), du(100), du(12))
        self.overwrite = QCheckBox("Whether overwrite key", host)
        self.overwrite.setGeometry(du(356), du(94), du(100), du(12))

        self.keys = self._table(host, ["Key(Overwrite)", "Available"], "#ffffff")
        self.keys.setGeometry(du(351), du(112), du(109), du(58))

        QGroupBox("Notice", host).setGeometry(du(351), du(174), du(109), du(100))
        text = QLabel(NOTICE, host)
        text.setGeometry(du(356), du(186), du(100), du(84))
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        text.setFont(QFont("Tahoma", 7))

        self.log = self._table(host, ["Device ID", "Time", "Result"], "#ffffff")
        self.log.setGeometry(du(7), du(168), du(338), du(95))
        header = self.log.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.log.setColumnWidth(0, 96)
        self.log.setColumnWidth(1, 148)
        self.log.verticalHeader().setDefaultSectionSize(18)
        self.log.setWordWrap(False)
        self.log.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.log.setTextElideMode(Qt.TextElideMode.ElideRight)

        for w in (
            self.erase,
            self.erase_bl,
            self.reset,
            self.overwrite,
            self.btn_start,
            self.btn_refresh,
            self.erase_mode,
        ):
            w.setFont(font)
            w.raise_()
        text.raise_()

        bar = QStatusBar()
        bar.setSizeGripEnabled(False)
        self.st_ready = QLabel("Ready")
        self.st_total = QLabel("Total :")
        self.st_ok = QLabel("Success:")
        self.st_err = QLabel("Error :")
        for lab in (self.st_ready, self.st_total, self.st_ok, self.st_err):
            lab.setFont(font)
        bar.addWidget(self.st_ready, 1)
        bar.addPermanentWidget(self.st_total)
        bar.addPermanentWidget(self.st_ok)
        bar.addPermanentWidget(self.st_err)
        self.setStatusBar(bar)
        self.setFixedSize(du(467) + 16, du(280) + self.menuBar().sizeHint().height() + 28)

    def _bar(self) -> QProgressBar:
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(True)
        bar.setFormat("")
        bar.setStyleSheet(
            "QProgressBar { border: 0; background: #F0F0CE; text-align: center; color: #000; }"
            "QProgressBar::chunk { background: #00b050; }"
        )
        return bar

    def _stamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _ok_phrase(self) -> str:
        if self.lang.startswith("中文"):
            return "烧录成功"
        return "Burning successful"

    def log_line(self, text: str) -> None:
        text = text.strip()
        if not text or set(text) <= {".", " "}:
            return
        row = self.log.rowCount()
        self.log.insertRow(row)
        dev = self.grid.item(0, 0).text() if self.grid.item(0, 0) else ""
        self.log.setItem(row, 0, QTableWidgetItem(dev))
        self.log.setItem(row, 1, QTableWidgetItem(self._stamp()))
        self.log.setItem(row, 2, QTableWidgetItem(text.rstrip()))
        self.log.scrollToBottom()

    def _show_image(self) -> None:
        if not self.image:
            self.st_ready.setText("Ready")
            return
        kb = self.image.stat().st_size // 1024
        self.st_ready.setText(f"{self.image}    {kb:,} KB")

    def import_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import image", str(Path.home() / "Downloads"), "Image (*.img)"
        )
        if path:
            self.load_image(Path(path))

    def load_image(self, path: Path) -> None:
        self.image = path
        try:
            names = partition_names(self.image)
        except OSError as e:
            self.log_line(str(e))
            return
        if not names:
            self.image = None
            self.btn_start.setEnabled(False)
            self.st_ready.setText("Parse burning image fail")
            QMessageBox.warning(self, "USB_Burning_Tool", "Parse burning image fail")
            return
        self.btn_start.setEnabled(True)
        self._parts = image_part_sizes(self.image)
        self._show_image()
        self.log_line(self.image.name)

    def check_image(self) -> None:
        if not self.image:
            self.log_line("Parse burning image fail")
            return
        names = partition_names(self.image)
        self.log_line("CheckImg OK" if names else "Parse burning image fail")

    def refresh_usb(self) -> None:
        if self.proc is not None:
            return
        devices = usb_devices()
        self.grid.setRowCount(len(devices))
        self._bars = []
        for row, dev_id in enumerate(devices):
            self.grid.setItem(row, 0, QTableWidgetItem(dev_id))
            bar = self._bar()
            self._bars.append(bar)
            self.grid.setCellWidget(row, 1, bar)
            self.grid.setItem(row, 2, QTableWidgetItem(""))
            self.grid.setItem(row, 3, QTableWidgetItem("0/1"))

    def _tick(self) -> None:
        self._elapsed += 1
        minutes, seconds = divmod(self._elapsed, 60)
        self.grid.setItem(0, 2, QTableWidgetItem(f"{minutes}:{seconds:02d}"))
        if not self._span or not self._bars:
            return
        start, end, size = self._span
        # ~6 МБ/с по USB 2. До [OK] не доходим до конца раздела.
        expect = max(size / 6_000_000, 1)
        frac = min((self._elapsed - self._span_at) / expect, 0.97)
        value = int(start + (end - start) * frac)
        if value > self._bars[0].value():
            self._bars[0].setValue(value)

    def toggle_burn(self) -> None:
        if self.proc is not None:
            self.stop_burn()
            return
        if not self.image or not self.image.is_file():
            self.log_line("Parse burning image fail")
            return
        try:
            if not usb_connected():
                self.log_line("You should put your board enter upgrade mode!")
                return
            cmd = burn_cmd(
                self.image,
                self.erase.isChecked(),
                self.reset.isChecked(),
                self.erase_bl.isChecked(),
                self.password,
                self.parts,
            )
        except RuntimeError as e:
            self.log_line(str(e))
            return
        self._burn_failed = False
        self._writing = ""
        self._span = None
        self._elapsed = 0
        if not self._parts and self.image:
            self._parts = image_part_sizes(self.image)
        if self._bars:
            self._bars[0].setFormat("%p%")
            self._bars[0].setValue(0)
        self.grid.setItem(0, 3, QTableWidgetItem("0/1"))
        self._clock.start(1000)
        self.log_line("Start")
        self.btn_start.setText("Stop")
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._on_out)
        self.proc.finished.connect(self._on_done)
        # скрипт aml-burn-tool
        self.proc.start(cmd[0], cmd[1:])
        if not self.proc.waitForStarted(3000):
            self.log_line(self.proc.errorString())
            self.proc = None
            self.btn_start.setText("Start")

    def _on_out(self) -> None:
        if not self.proc:
            return
        data = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        for line in data.splitlines():
            line = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
            if line:
                if "nothing to do more" in line or "not found" in line.lower() or "[KO]" in line:
                    self._burn_failed = True
                self._apply_progress(line)
                self.log_line(line)

    def _apply_progress(self, line: str) -> None:
        if not self._bars or not self._parts:
            return
        writing = re.search(r"Writing\s+([A-Za-z0-9_]+)", line, re.I)
        if writing:
            self._writing = writing.group(1)
            start = burn_percent(self._parts, self._writing, done=False)
            end = burn_percent(self._parts, self._writing, done=True)
            size = next((s for n, s in self._parts if n.lower() == self._writing.lower()), 0)
            if start is None or end is None:
                return
            self._span = (start, end, size)
            self._span_at = self._elapsed
            self._bars[0].setValue(start)
            return
        if self._writing and re.search(r"\[OK\]", line):
            end = burn_percent(self._parts, self._writing, done=True)
            self._span = None
            if end is None:
                return
            self._bars[0].setValue(end)
            if end >= 100:
                self._bars[0].setFormat(f"100% {self._ok_phrase()}")
                self.grid.setItem(0, 3, QTableWidgetItem("1/1"))

    def _on_done(self, code: int, _status) -> None:
        self._clock.stop()
        ok = code == 0 and not self._burn_failed
        if self._bars:
            self._bars[0].setValue(100 if ok else self._bars[0].value())
            phrase = self._ok_phrase() if ok else "Burning failed"
            self._bars[0].setFormat(f"%p% {phrase}")
        if ok:
            self.ok_n += 1
            self.grid.setItem(0, 3, QTableWidgetItem("1/1"))
            self.log_line(f"[0x00000000]{self._ok_phrase()}")
        else:
            self.err_n += 1
            self.log_line(f"[0x{code & 0xFFFFFFFF:08x}]")
        self.st_total.setText(f"Total : {self.ok_n + self.err_n}")
        self.st_ok.setText(f"Success: {self.ok_n}")
        self.st_err.setText(f"Error : {self.err_n}")
        self.proc = None
        self.btn_start.setText("Start")
        self.btn_start.setEnabled(self.image is not None)

    def stop_burn(self) -> None:
        self._clock.stop()
        if not self.proc:
            return
        self.log_line("Stopping...")
        pid = self.proc.processId()
        self.proc.kill()
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        self.btn_start.setText("Start")

    def set_language(self, name: str) -> None:
        self.lang = name
        for act in self.lang_actions:
            act.setChecked(act.text() == name)
        strings = {
            "English": ("Erase flash", "Erase bootloader", "Reset after success", "Whether overwrite key", "Start", "Refresh", "Ready"),
            "中文（简体）": ("擦除flash", "擦除bootloader", "成功后复位", "是否覆盖key", "开始", "刷新", "就绪"),
            "中文（傳統）": ("擦除flash", "擦除bootloader", "成功後復位", "是否覆蓋key", "開始", "刷新", "就緒"),
        }
        erase, bl, reset, key, start, refresh, ready = strings.get(name, strings["English"])
        self.erase.setText(erase)
        self.erase_bl.setText(bl)
        self.reset.setText(reset)
        self.overwrite.setText(key)
        self.btn_start.setText(start if self.proc is None else "Stop")
        self.btn_refresh.setText(refresh)
        self.st_ready.setText(ready)

    def select_parts(self) -> None:
        if not self.image:
            self.log_line("Parse burning image fail")
            return
        names = partition_names(self.image)
        text, ok = QInputDialog.getText(
            self, "Select...", "parts (all or comma list)", text=self.parts if self.parts != "all" else ",".join(names)
        )
        if ok and text.strip():
            self.parts = text.strip()
            self.log_line(f"parts={self.parts}")

    def temperature(self) -> None:
        value, ok = QInputDialog.getInt(self, "Temperature Testting Setting", "°C", self.temp_c, 0, 120)
        if ok:
            self.temp_c = value
            self.log_line(f"Temperature {value}")

    def input_password(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "InPut Password", "", "password (*.bin *)")
        if path:
            self.password = path
            self.log_line(Path(path).name)

    def enable_key(self) -> None:
        self.overwrite.setEnabled(True)
        self.overwrite.setChecked(True)
        self.log_line("Enable Erase Key")

    def open_doc(self, name: str) -> None:
        root = Path.home() / "Downloads/Khadas_SR2_install/Amlogic/V2/help" / name
        if not root.is_file():
            self.log_line(f"нет файла {name}")
            return
        subprocess.Popen(["open", str(root)])

    def upgrade(self) -> None:
        note = Path.home() / "Downloads/Khadas_SR2_install/Amlogic/V2/release_note.txt"
        if note.is_file():
            subprocess.Popen(["open", str(note)])
        else:
            self.log_line("Online Upgrade")

    def about(self) -> None:
        QMessageBox.information(
            self,
            "About USB_Burning_Tool",
            "USB_Burning_Tool (macOS port)\n"
            "UI layout after Amlogic USB_Burning_Tool V2.2.4\n"
            "Burn backend: Khadas aml-flash-tool\n\n"
            "Port: Vsevolod Vasin\n"
            "https://github.com/VsevolodVasin/usb-burning-tool-macos",
        )

    def closeEvent(self, event) -> None:
        self.stop_burn()
        event.accept()

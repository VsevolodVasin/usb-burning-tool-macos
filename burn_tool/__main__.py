import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from burn_tool.window import BurnWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar, True)
    app.setStyle("Fusion")
    win = BurnWindow()
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if path.is_file():
            win.load_image(path)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

"""Tema visual de la aplicación: negro neutro con acento blanco, inspirado en Windows 11 (Fluent).

Todos los colores de la interfaz salen de aquí, para que las páginas no tengan valores sueltos.
"""
from PySide6.QtGui import QColor, QFont, QPalette

# ---- Superficies ----
BG = "#0f0f10"            # fondo de la ventana (zona de contenido)
SIDEBAR = "#09090a"       # barra lateral
SURFACE = "#171718"       # tarjetas y paneles
SURFACE_2 = "#1f1f21"     # controles (botones, campos) y filas alternas
SURFACE_3 = "#2a2a2d"     # hover de controles
BORDER = "#252527"
BORDER_STRONG = "#353538"

# ---- Texto ----
TEXT = "#ededee"
MUTED = "#a0a0a6"
SUBTLE = "#6c6c72"

# ---- Acento y estados ----
ACCENT = "#f2f2f3"
ACCENT_HOVER = "#ffffff"
ACCENT_PRESSED = "#cfcfd2"
ACCENT_TEXT = "#0c0c0d"
ACCENT_SOFT = "#2c2c2f"   # selección / fondo suave del acento
SUCCESS = "#4cc38a"
WARNING = "#e8b44c"
DANGER = "#f06a6a"
INFO = ACCENT
BRAND = "#ffd24a"         # amarillo del icono (pista elegida)

# ---- Categorías de pistas (mismo significado que antes) ----
COLOR_CASTELLANO = SUCCESS
COLOR_LATINO = "#ee9a4d"
COLOR_AMBIGUO = "#f07a93"
COLOR_OTRO = MUTED
COLOR_CAMBIO = "#ffffff"   # «cambia» / «se modificará»
COLOR_REVISAR = WARNING

FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Inter", "sans-serif"]

QSS = f"""
* {{ font-size: 13px; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ color: {TEXT}; }}
QWidget#page, QWidget#content {{ background: {BG}; }}
QLabel {{ background: transparent; }}
QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; border-radius: 6px; padding: 6px 8px; }}

/* ---------- Barra lateral ---------- */
QFrame#sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
QLabel#brand {{ font-size: 14px; font-weight: 600; color: {TEXT}; }}
QLabel#brandSub {{ font-size: 11px; color: {SUBTLE}; }}
QToolButton#nav {{ background: transparent; border: none; border-radius: 6px; color: {MUTED};
    padding: 9px 10px; text-align: left; font-size: 13px; }}
QToolButton#nav:hover {{ background: {SURFACE}; color: {TEXT}; }}
QToolButton#nav:checked {{ background: {SURFACE_2}; color: {TEXT}; font-weight: 600; }}
QFrame#navIndicator {{ background: {BRAND}; border-radius: 2px; }}

/* ---------- Tipografía de página ---------- */
QLabel#pageTitle {{ font-size: 22px; font-weight: 600; }}
QLabel#pageSubtitle {{ color: {MUTED}; }}
QLabel#sectionTitle {{ font-size: 13px; font-weight: 600; color: {TEXT}; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#subtle {{ color: {SUBTLE}; font-size: 12px; }}
QLabel#path {{ font-size: 13px; color: {TEXT}; }}
QLabel#pathEmpty {{ font-size: 13px; color: {SUBTLE}; }}
QLabel#statValue {{ font-size: 20px; font-weight: 600; }}
QLabel#statLabel {{ color: {MUTED}; font-size: 12px; }}
QLabel#emptyTitle {{ font-size: 15px; font-weight: 600; }}
QLabel#emptyText {{ color: {MUTED}; }}

/* ---------- Tarjetas ---------- */
QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; }}
QFrame#stat {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; }}
QFrame#actionBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; }}
QFrame#divider {{ background: {BORDER}; max-height: 1px; min-height: 1px; border: none; }}

/* ---------- Avisos (InfoBar) ---------- */
QFrame#infobar {{ border-radius: 8px; border: 1px solid {BORDER}; background: {SURFACE}; }}
QFrame#infobar[severity="success"] {{ background: #16291f; border-color: #24543a; }}
QFrame#infobar[severity="warning"] {{ background: #2d2616; border-color: #5a4a22; }}
QFrame#infobar[severity="error"] {{ background: #2e1a1c; border-color: #5e2b30; }}
QFrame#infobar[severity="info"] {{ background: {SURFACE_2}; border-color: {BORDER_STRONG}; }}
QLabel#infoTitle {{ font-weight: 600; }}

/* ---------- Botones ---------- */
QPushButton {{ background: {SURFACE_2}; border: 1px solid {BORDER_STRONG}; border-bottom-color: #2c2c2f;
    border-radius: 6px; padding: 6px 14px; min-height: 20px; color: {TEXT}; }}
QPushButton:hover {{ background: {SURFACE_3}; }}
QPushButton:pressed {{ background: {SURFACE}; color: {MUTED}; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ background: {SURFACE}; color: {SUBTLE}; border-color: {BORDER}; }}
QPushButton#primary {{ background: {ACCENT}; border: 1px solid {ACCENT}; border-bottom-color: {ACCENT_PRESSED};
    color: {ACCENT_TEXT}; font-weight: 600; padding: 7px 18px; }}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton#primary:pressed {{ background: {ACCENT_PRESSED}; color: #2a2a2c; }}
QPushButton#primary:focus {{ border-color: {BRAND}; }}
QPushButton#primary:disabled {{ background: #262628; border-color: #262628; color: #6c6c72; }}
QPushButton#danger {{ background: transparent; border: 1px solid #5e2b30; color: {DANGER}; }}
QPushButton#danger:hover {{ background: #2e1a1c; border-color: {DANGER}; }}
QPushButton#danger:disabled {{ color: {SUBTLE}; border-color: {BORDER}; background: transparent; }}
QPushButton#subtle {{ background: transparent; border: 1px solid transparent; color: {MUTED}; padding: 5px 10px; }}
QPushButton#subtle:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
QPushButton#subtle:checked {{ background: {SURFACE_2}; color: {TEXT}; }}
QPushButton#subtle:disabled {{ color: {SUBTLE}; background: transparent; }}
QPushButton#link {{ background: transparent; border: none; color: {ACCENT}; padding: 2px 0; }}
QPushButton#link:hover {{ color: {ACCENT_HOVER}; text-decoration: underline; }}
QPushButton#chip {{ background: transparent; border: 1px solid {BORDER_STRONG}; border-radius: 13px;
    padding: 3px 12px; color: {MUTED}; min-height: 18px; }}
QPushButton#chip:hover {{ color: {TEXT}; background: {SURFACE_2}; }}
QPushButton#chip:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT}; color: {TEXT}; }}
QPushButton#chip:disabled {{ color: {SUBTLE}; border-color: {BORDER}; }}
QPushButton#iconButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 4px; }}
QPushButton#iconButton:hover {{ background: {SURFACE_2}; }}

/* ---------- Campos ---------- */
QLineEdit, QPlainTextEdit {{ background: {SURFACE_2}; border: 1px solid {BORDER_STRONG};
    border-bottom: 1px solid #4a4a4e; border-radius: 6px; padding: 5px 9px; selection-background-color: {ACCENT}; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border-bottom: 2px solid {ACCENT}; background: {SURFACE}; }}
QLineEdit:disabled {{ color: {SUBTLE}; background: {SURFACE}; }}
QPlainTextEdit#log {{ background: {SIDEBAR}; border: none; border-radius: 0; padding: 6px 10px;
    font-family: "Cascadia Mono", Consolas, monospace; font-size: 12px; color: {MUTED}; }}

QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator, QTreeView::indicator {{ width: 16px; height: 16px; border: 1px solid #5a5a60;
    border-radius: 4px; background: {SURFACE_2}; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url(mkvsd:check.svg); }}
QCheckBox:disabled {{ color: {SUBTLE}; }}
QCheckBox::indicator:disabled {{ background: {SURFACE}; border-color: {BORDER}; }}

/* ---------- Tablas y árboles ---------- */
QTreeWidget, QTableWidget {{ background: {SURFACE}; alternate-background-color: #131314; border: 1px solid {BORDER};
    border-radius: 8px; outline: 0; gridline-color: {BORDER}; }}
QTreeWidget::item, QTableWidget::item {{ padding: 4px 2px; border: none; }}
QTreeWidget::item:hover {{ background: #1e1e20; }}
QTreeWidget::item:selected, QTableWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {SURFACE}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 7px 8px; font-size: 12px; font-weight: 600; }}
QHeaderView::section:first {{ border-top-left-radius: 8px; }}
QTableCornerButton::section {{ background: {SURFACE}; border: none; }}

/* ---------- Progreso ---------- */
QProgressBar {{ background: {SURFACE_3}; border: none; border-radius: 2px; max-height: 4px; min-height: 4px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}

/* ---------- Desplazamiento ---------- */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #38383b; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #4c4c50; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #38383b; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 8px; }}

/* ---------- Menús y diálogos ---------- */
QMenu {{ background: {SURFACE_2}; border: 1px solid {BORDER_STRONG}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {SURFACE_3}; }}
QMessageBox {{ background: {BG}; }}
QMessageBox QLabel {{ color: {TEXT}; }}
"""


def apply_dark_theme(app):
    from . import icons   # registra los recursos (check de las casillas)
    icons.register_resources()
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPixelSize(13)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(SURFACE))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#131314"))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(SUBTLE))
    pal.setColor(QPalette.ColorRole.Button, QColor(SURFACE_2))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(ACCENT_TEXT))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(SURFACE_2))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(SUBTLE))
    app.setPalette(pal)
    app.setStyleSheet(QSS)

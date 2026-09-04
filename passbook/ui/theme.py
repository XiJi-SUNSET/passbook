"""视觉主题：citrus-letter 酸橙信笺设计 token → Qt 样式表。

token 全部原样搬运自参考项目 "citrus-letter-8bit"（一个酸橙色信笺主题的 8-bit
单文件静态网页播放器，配色规范见 DESIGN.md §8）：

    --red:#ed685f  --red-dark:#d94f46  --red-soft:rgba(237,104,95,.14)
    --white:#f2ede6（暖米白纸底）  --ink:#3a3a3a  --ink-dim:#8a8a8a
    --line:rgba(237,104,95,.18)
    .glass{ background:rgba(242,237,230,.36); backdrop-filter:blur(14px) saturate(1.3) }
    圆角 8~9px；顶栏 56px、padding 0 16px、gap 14px
    字体 "Segoe UI","Microsoft YaHei",system-ui

设计决策（2026-09-04）：**窗口一律铺不透明纸底，不做系统级真毛玻璃**。
试过走 Win32 DWM 亚克力（SetWindowCompositionAttribute），但它在远程桌面/虚拟机/
系统关闭透明效果的环境会"调用成功却不渲染"，窗口整片透明露黑，是不可靠的视觉来源。
毛玻璃质感用"纸底 + 半透明白玻璃层控件"近似，视觉仍接近 citrus 且永远不破。
"""

# ---------- 设计 token ----------
RED = "#ed685f"
RED_DARK = "#d94f46"
RED_SOFT = "rgba(237,104,95,.14)"
RED_HOVER = "rgba(237,104,95,.08)"
PAPER = "#f2ede6"
INK = "#3a3a3a"
INK_DIM = "#8a8a8a"
LINE = "rgba(237,104,95,.18)"

GLASS_BG = "rgba(242,237,230,.36)"   # 面板底色（叠在纸底上呈浅玻璃感）
CARD_BG = "rgba(255,255,255,.60)"    # 按钮/卡片底
FIELD_BG = "rgba(255,255,255,.65)"   # 输入框底

RADIUS = 9
RADIUS_SM = 8
HEADER_H = 56
GAP = 14
PAD_X = 16

FONT_FAMILY = '"Segoe UI","Microsoft YaHei",system-ui'
FONT_SIZE = 13


def stylesheet() -> str:
    """完整 QSS。窗口本体不透明纸底；内容控件自带底色保证可读。"""
    return f"""
    QWidget {{
        background: transparent; color: {INK};
        font-family: {FONT_FAMILY}; font-size: {FONT_SIZE}px;
    }}
    QMainWindow, QDialog {{ background: {PAPER}; }}
    QLabel[dim="true"] {{ color: {INK_DIM}; }}
    QLabel[brand="true"] {{ color: {RED_DARK}; font-weight: 700; font-size: 15px; }}
    QLabel[count="true"] {{ color: {INK_DIM}; font-size: 12px; }}

    QPushButton {{
        border: 1px solid {LINE}; background: {CARD_BG};
        border-radius: {RADIUS}px; padding: 7px 14px; color: {RED_DARK};
    }}
    QPushButton:hover {{ background: {RED}; color: #ffffff; border-color: {RED}; }}
    QPushButton:pressed {{ background: {RED_DARK}; color: #ffffff; }}
    QPushButton:disabled {{ color: {INK_DIM}; background: rgba(255,255,255,.30); }}
    QPushButton[primary="true"] {{
        background: {RED}; color: #ffffff; border-color: {RED}; font-weight: 600;
    }}
    QPushButton[primary="true"]:hover {{ background: {RED_DARK}; }}
    QPushButton[danger="true"]:hover {{
        background: {RED_DARK}; color: #ffffff; border-color: {RED_DARK};
    }}
    QPushButton[icon="true"] {{ min-width: 34px; max-width: 34px; padding: 6px 0; }}

    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
        border: 1px solid {LINE}; background: {FIELD_BG};
        border-radius: {RADIUS_SM}px; padding: 7px 10px;
        selection-background-color: rgba(237,104,95,.28);
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {RED}; }}

    QListWidget, QTreeWidget {{
        background: {GLASS_BG}; border: 1px solid {LINE};
        border-radius: {RADIUS}px; padding: 4px;
    }}
    QListWidget::item, QTreeWidget::item {{ padding: 8px 10px; border-radius: {RADIUS_SM}px; }}
    QListWidget::item:hover, QTreeWidget::item:hover {{ background: {RED_HOVER}; }}
    QListWidget::item:selected, QTreeWidget::item:selected {{
        background: {RED_SOFT}; color: {RED_DARK};
    }}

    QScrollBar:vertical {{ width: 9px; background: transparent; margin: 2px 0; }}
    QScrollBar:horizontal {{ height: 9px; background: transparent; margin: 0 2px; }}
    QScrollBar::handle:vertical {{
        background: rgba(237,104,95,.35); border-radius: 4px; min-height: 28px;
    }}
    QScrollBar::handle:horizontal {{
        background: rgba(237,104,95,.35); border-radius: 4px; min-width: 28px;
    }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
        background: rgba(237,104,95,.55);
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QFrame[sep="true"] {{ background: {LINE}; }}
    QToolTip {{
        background: {PAPER}; color: {INK}; border: 1px solid {LINE};
        padding: 4px 8px; border-radius: 6px;
    }}
    QStatusBar {{ background: transparent; color: {INK_DIM}; font-size: 12px; }}
    QMenu {{
        background: {PAPER}; border: 1px solid {LINE}; border-radius: {RADIUS_SM}px; padding: 4px;
    }}
    QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {RED_SOFT}; color: {RED_DARK}; }}
    """

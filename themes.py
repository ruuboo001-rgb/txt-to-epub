from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    key: str
    label: str
    accent: str
    accent_dark: str
    soft: str
    paper: str
    text: str
    muted: str
    ornament: str


THEMES = {
    "rose": Theme("rose", "로즈 핑크", "#d96b9f", "#9b3f68", "#fff2f7", "#fffafd", "#2f2930", "#7b6a74", "✦ ✦ ✦"),
    "blue": Theme("blue", "문라이트 블루", "#5c7fcb", "#2f5597", "#f1f5ff", "#fbfcff", "#242936", "#687385", "◆ ◆ ◆"),
    "beige": Theme("beige", "클래식 베이지", "#b88952", "#7b5632", "#fbf5ec", "#fffdf8", "#302820", "#77695a", "❖ ❖ ❖"),
    "violet": Theme("violet", "바이올렛", "#8f70d8", "#6043a3", "#f5f1ff", "#fdfbff", "#2b2733", "#726981", "◇ ◇ ◇"),
    "mono": Theme("mono", "모던 모노", "#666666", "#222222", "#f6f6f6", "#ffffff", "#222222", "#777777", "* * *"),
}


def get_theme(key: str) -> Theme:
    return THEMES.get(key, THEMES["rose"])


def epub_css(theme_key: str) -> str:
    t = get_theme(theme_key)
    return f"""
@charset "utf-8";

html, body {{
    margin: 0;
    padding: 0;
}}

body {{
    color: {t.text};
    background: {t.paper};
    font-family: serif;
    line-height: 1.85;
    word-break: keep-all;
    -epub-line-break: normal;
}}

p {{
    margin: 0 0 0.72em 0;
    text-align: justify;
    text-indent: 1em;
}}

.cover-page {{
    min-height: 100vh;
    margin: 0;
    padding: 0;
    text-align: center;
    page-break-after: always;
}}

.cover-image {{
    display: block;
    width: 100%;
    max-width: 100%;
    height: auto;
    margin: 0 auto;
}}

.title-page {{
    min-height: 90vh;
    text-align: center;
    padding: 18vh 1.4em 0 1.4em;
    page-break-after: always;
}}

.title-card {{
    border-top: 2px solid {t.accent};
    border-bottom: 2px solid {t.accent};
    padding: 2.6em 0.8em 2.4em 0.8em;
}}

.title-ornament {{
    color: {t.accent};
    font-size: 1.05em;
    letter-spacing: 0.18em;
    margin: 0 0 2.0em 0;
    text-indent: 0;
    text-align: center;
}}

.book-title {{
    color: {t.accent_dark};
    font-size: 1.75em;
    font-weight: 700;
    line-height: 1.55;
    margin: 0 0 1.1em 0;
    text-indent: 0;
    text-align: center;
    word-break: keep-all;
}}

.book-author {{
    color: {t.muted};
    font-size: 1.02em;
    margin: 0 0 3.8em 0;
    text-indent: 0;
    text-align: center;
}}

.book-maker-label {{
    color: {t.accent};
    font-size: 0.72em;
    margin: 4.8em 0 0.35em 0;
    text-indent: 0;
    text-align: center;
    letter-spacing: 0.12em;
}}

.book-maker {{
    color: {t.muted};
    font-size: 0.84em;
    margin: 0;
    text-indent: 0;
    text-align: center;
    letter-spacing: 0.06em;
}}

.toc-page {{
    min-height: 90vh;
    padding: 10vh 1.2em 0 1.2em;
    page-break-after: always;
}}

.toc-card {{
    border-top: 2px solid {t.accent};
    border-bottom: 2px solid {t.accent};
    background: {t.soft};
    padding: 2.1em 1.1em 2.4em 1.1em;
}}

.toc-ornament {{
    color: {t.accent};
    font-size: 0.9em;
    letter-spacing: 0.18em;
    margin: 0 0 1.5em 0;
    text-indent: 0;
    text-align: center;
}}

.toc-title {{
    color: {t.accent_dark};
    font-size: 1.5em;
    font-weight: 700;
    line-height: 1.4;
    margin: 0 0 0.5em 0;
    text-align: center;
    text-indent: 0;
}}

.toc-book-title {{
    color: {t.muted};
    font-size: 0.92em;
    margin: 0 0 2.2em 0;
    text-align: center;
    text-indent: 0;
}}

.toc-list {{
    margin: 0;
    padding: 0;
    list-style-type: none;
}}

.toc-item {{
    border-bottom: 1px solid {t.accent};
    margin: 0;
    padding: 0.72em 0.1em;
}}

.toc-item a {{
    color: {t.text};
    text-decoration: none;
}}

.chapter-title {{
    color: {t.accent_dark};
    font-size: 1.45em;
    font-weight: 700;
    line-height: 1.55;
    margin: 18vh 0 3.2em 0;
    padding: 0 0 1.1em 0;
    text-align: center;
    text-indent: 0;
    word-break: keep-all;
}}

.chapter-title::after {{
    content: "{t.ornament}";
    display: block;
    color: {t.accent};
    font-size: 0.58em;
    font-weight: 400;
    letter-spacing: 0.18em;
    margin-top: 1.7em;
}}

.scene-break {{
    color: {t.accent};
    font-size: 0.95em;
    letter-spacing: 0.22em;
    margin: 2.6em 0;
    text-align: center;
    text-indent: 0;
}}

.soft-quote {{
    color: {t.muted};
    font-style: italic;
}}

.system-line {{
    color: {t.muted};
    font-style: italic;
    text-align: center;
    text-indent: 0;
    margin: 1.2em 0;
}}

.soft-space {{
    height: 0.85em;
}}
""".strip()


APP_QSS = """
* {
    font-family: "Pretendard", "Segoe UI", "Malgun Gothic";
    font-size: 14px;
}

QMainWindow, QWidget#Root {
    background: #f7f2f6;
    color: #2f2930;
}

QFrame#SideBar {
    background: #ffffff;
    border-radius: 24px;
    border: 1px solid #f0e2ea;
}

QFrame#Card {
    background: #ffffff;
    border-radius: 20px;
    border: 1px solid #f0e2ea;
}

QLabel#AppTitle {
    font-size: 24px;
    font-weight: 800;
    color: #9b3f68;
}

QLabel#SectionTitle {
    font-size: 16px;
    font-weight: 800;
    color: #3a3037;
}

QLabel#Hint {
    color: #8a7b84;
    font-size: 12px;
}

QLabel#CoverPreview {
    background: #fffafd;
    border: 1px dashed #e8c8d9;
    border-radius: 18px;
    color: #a08393;
    font-size: 12px;
    qproperty-alignment: AlignCenter;
}

QLineEdit, QComboBox, QTextEdit, QListWidget, QTextBrowser {
    background: #ffffff;
    border: 1px solid #ead8e3;
    border-radius: 12px;
    padding: 8px;
    selection-background-color: #e88ab5;
}

QTextEdit, QTextBrowser, QListWidget {
    background: #fffdfd;
}

QCheckBox {
    color: #3a3037;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 6px;
    border: 1px solid #e1bfd1;
    background: #ffffff;
}

QCheckBox::indicator:checked {
    background: #e88ab5;
    border: 1px solid #e88ab5;
}

QPushButton {
    background: #e88ab5;
    color: white;
    border: none;
    border-radius: 13px;
    padding: 10px 14px;
    font-weight: 700;
}

QPushButton:hover {
    background: #dc6fa3;
}

QPushButton:pressed {
    background: #c95a8c;
}

QPushButton#SecondaryButton {
    background: #f3e4ed;
    color: #9b3f68;
}

QPushButton#SecondaryButton:hover {
    background: #ecd5e2;
}

QPushButton#DangerButton {
    background: #35313a;
    color: #ffffff;
}

QProgressBar {
    border: none;
    border-radius: 8px;
    background: #f2e5ed;
    height: 10px;
    text-align: center;
}

QProgressBar::chunk {
    border-radius: 8px;
    background: #e88ab5;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: #e3c9d7;
    border-radius: 5px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""

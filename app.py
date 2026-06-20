from __future__ import annotations

import base64
import html
import re
import tempfile
from pathlib import Path
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components

from epub_builder import build_epub, title_page_body, toc_page_body
from text_parser import (
    chapter_to_xhtml_body,
    compile_chapter_patterns,
    display_line_text,
    get_pattern_preset_candidates,
    merge_excluded_chapters,
    normalize_text,
    regex_from_example_line,
    regex_from_example_lines,
    sample_title_like_lines,
    split_chapters,
    strip_original_start_page,
    suggest_chapter_patterns,
    suspicious_chapter_indices,
)
from themes import FONT_PRESETS, THEMES, epub_css, get_theme


st.set_page_config(
    page_title="TXT → EPUB Studio v2.8",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)


APP_CSS = """
<style>
:root {
  --app-bg: #fbf7fb;
  --card-bg: rgba(255,255,255,.86);
  --line: rgba(220, 190, 210, .75);
  --shadow: 0 22px 60px rgba(105, 64, 91, .13);
  --text: #302933;
  --muted: #807181;
  --accent: #d96b9f;
  --accent-dark: #9b3f68;
  --soft: #fff2f7;
}

.stApp {
  background:
    radial-gradient(circle at 12% 8%, rgba(255, 214, 233, .8), transparent 30%),
    radial-gradient(circle at 82% 0%, rgba(222, 215, 255, .56), transparent 32%),
    linear-gradient(135deg, #fffafd 0%, #f7f1ff 46%, #fff8f0 100%);
  color: var(--text);
}

.block-container {
  padding-top: 2rem;
  padding-bottom: 3rem;
  max-width: 1320px;
}

.hero {
  padding: 1.5rem 1.65rem;
  border-radius: 28px;
  background: rgba(255,255,255,.7);
  border: 1px solid rgba(255,255,255,.72);
  box-shadow: var(--shadow);
  backdrop-filter: blur(14px);
  margin-bottom: 1.2rem;
}

.hero h1 {
  margin: 0;
  font-size: 2.1rem;
  letter-spacing: -0.04em;
  color: var(--accent-dark);
}

.hero p {
  margin: .55rem 0 0 0;
  color: var(--muted);
  line-height: 1.65;
}

[data-testid="stSidebar"] {
  background: rgba(255,255,255,.74);
  border-right: 1px solid rgba(220, 190, 210, .55);
}

[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
  color: var(--accent-dark);
}

.card {
  padding: 1.1rem 1.15rem;
  border-radius: 24px;
  background: var(--card-bg);
  border: 1px solid rgba(255,255,255,.84);
  box-shadow: 0 14px 45px rgba(105, 64, 91, .09);
  margin-bottom: 1rem;
}

.small-note {
  color: var(--muted);
  font-size: .9rem;
  line-height: 1.65;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: .35rem;
  padding: .32rem .62rem;
  border-radius: 999px;
  background: var(--soft);
  color: var(--accent-dark);
  border: 1px solid var(--line);
  font-weight: 700;
  font-size: .84rem;
}

div.stButton > button,
div.stDownloadButton > button {
  border-radius: 999px !important;
  border: 0 !important;
  background: linear-gradient(135deg, var(--accent), #ec9fc3) !important;
  color: white !important;
  font-weight: 800 !important;
  box-shadow: 0 12px 24px rgba(217, 107, 159, .22) !important;
}

div.stButton > button:hover,
div.stDownloadButton > button:hover {
  filter: brightness(.98);
  transform: translateY(-1px);
}

.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div {
  border-radius: 16px !important;
}

.preview-frame {
  border-radius: 24px;
  overflow: hidden;
  border: 1px solid var(--line);
  background: white;
}

hr {
  border: 0;
  border-top: 1px solid rgba(220,190,210,.7);
  margin: 1.4rem 0;
}
</style>
"""

st.markdown(APP_CSS, unsafe_allow_html=True)


DEFAULT_CHAPTER_HELP = """// 한 줄에 하나씩 추가하세요. #은 회차에 자주 쓰여서 주석으로 처리하지 않습니다.
// 예시:
// ^제\\s*\\d+\\s*장.*$
// ^#\\s*\\d+.*$
""".strip()

DEFAULT_SCENE_HELP = """// 한 줄에 하나씩 추가하세요. 문자 그대로 입력해도 됩니다.
// 예시:
// *
// ♧
// ※
""".strip()


@st.cache_data(show_spinner=False)
def decode_text(data: bytes) -> str:
    encodings = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]
    last_error: Optional[Exception] = None
    for enc in encodings:
        try:
            return data.decode(enc)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"텍스트 인코딩을 읽을 수 없습니다: {last_error}")


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name.strip())
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name or "book"


def title_from_uploaded_filename(filename: str) -> str:
    """TXT 파일명에서 EPUB 제목으로 쓰기 좋은 문자열을 만듭니다."""
    stem = Path(filename or "").stem
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .")

    # 흔한 정리: 끝에 붙은 txt/텍본/완결/본편 같은 작업 메모가 있으면 너무 과하게 지우지 않고
    # 괄호 안 확장자성 메모 정도만 정돈합니다. 작품 제목이 훼손될 수 있으므로 보수적으로 처리합니다.
    stem = re.sub(r"\s*[\[(（【]\s*(?:txt|텍본|text)\s*[\])）】]\s*$", "", stem, flags=re.I)
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    return stem or "제목 없음"


def preview_document(
    body: str,
    theme_key: str,
    height: int = 620,
    *,
    auto_indent: bool | None = None,
    font_key: str | None = None,
) -> None:
    if auto_indent is None:
        auto_indent = bool(globals().get("auto_indent", True))
    if font_key is None:
        font_key = globals().get("font_key", "serif")
    css = epub_css(theme_key, auto_indent=auto_indent, font_key=font_key)
    html_doc = f"""
    <!doctype html>
    <html>
    <head>
    <meta charset="utf-8" />
    <style>
    {css}
    body {{ max-width: 560px; margin: 0 auto; padding: 0 1.25rem 2.5rem 1.25rem; }}
    .cover-page {{ min-height: auto; padding: 1rem 0; }}
    .cover-image {{ max-height: 560px; width: auto; max-width: 100%; border-radius: 14px; box-shadow: 0 20px 50px rgba(0,0,0,.12); }}
    </style>
    </head>
    <body>{body}</body>
    </html>
    """
    components.html(html_doc, height=height, scrolling=True)


def cover_html_from_upload(uploaded_cover) -> str:
    if not uploaded_cover:
        return ""
    mime = uploaded_cover.type or "image/jpeg"
    encoded = base64.b64encode(uploaded_cover.getvalue()).decode("ascii")
    return f'<div class="cover-page"><img class="cover-image" src="data:{mime};base64,{encoded}" alt="cover" /></div>'


def analyze_chapters(
    raw_text: str,
    custom_regex_text: str,
    title: str,
    author: str,
    maker: str,
    include_title: bool,
    remove_start: bool,
    use_default_patterns: bool,
    remove_imported_toc: bool,
    remove_repeated_title_headers: bool,
    repeated_header_text: str,
):
    chapters = split_chapters(
        raw_text,
        custom_regex_text=custom_regex_text,
        fallback_title=title or "본문",
        use_default_patterns=use_default_patterns,
        remove_imported_toc=remove_imported_toc,
        remove_repeated_title_headers=remove_repeated_title_headers,
        repeated_header_text=repeated_header_text,
    )
    if include_title and remove_start:
        chapters = strip_original_start_page(chapters, title=title, author=author, maker=maker)
    return chapters


def chapter_option_label(chapter) -> str:
    nonblank_count = len([line for line in chapter.lines if display_line_text(line)])
    title = chapter.title.replace("\n", " ").strip()
    if len(title) > 76:
        title = title[:74] + "…"
    return f"{chapter.index:03d}. {title}  ·  {nonblank_count}문단"


def excluded_option_label(option) -> str:
    idx, label = option
    return label


# ---------- State ----------
st.session_state.setdefault("chapter_regex_text", DEFAULT_CHAPTER_HELP)
st.session_state.setdefault("use_default_chapter_patterns", True)


def apply_chapter_regex(regex: str, *, append: bool = False) -> None:
    current = st.session_state.get("chapter_regex_text", "")
    if append and current.strip():
        existing = [line.strip() for line in current.splitlines() if line.strip() and not line.strip().startswith("//")]
        new_lines = [line.strip() for line in regex.splitlines() if line.strip()]
        merged = current.rstrip()
        for line in new_lines:
            if line not in existing:
                merged += "\n" + line
        st.session_state["chapter_regex_text"] = merged
    else:
        st.session_state["chapter_regex_text"] = regex
    st.session_state["use_default_chapter_patterns"] = False


def apply_regex_bundle(regexes: list[str], *, append: bool = False) -> None:
    clean = []
    for regex in regexes:
        for line in regex.splitlines():
            line = line.strip()
            if line and line not in clean:
                clean.append(line)
    if clean:
        apply_chapter_regex("\n".join(clean), append=append)


PRESET_BUNDLES = {
    "연재 화수형": ["프롤로그/에필로그", "연재: 숫자화", "외전/번외/특별편"],
    "단행본 숫자제목형": ["프롤로그/에필로그", "단행본: 숫자. 제목", "외전/번외/특별편"],
    "001 번호형": ["단행본: 세자리 001. 제목", "프롤로그/에필로그", "외전/번외/특별편"],
    "단독 번호형": ["프롤로그/에필로그", "단독 번호: 1. 2. 3.", "단독 번호: 01. 02.", "단독 번호: 001. 002.", "외전/번외/특별편"],
    "해시 번호형": ["프롤로그/에필로그", "해시: #번호", "외전/번외/특별편"],
    "장/권/부 제목형": ["프롤로그/에필로그", "장 제목: 숫자장", "권/부: 숫자권·숫자부", "외전/번외/특별편"],
}


# ---------- Sidebar ----------
st.sidebar.markdown("## 📚 EPUB Studio")
st.sidebar.markdown('<span class="badge">TXT → EPUB 웹 제작기</span>', unsafe_allow_html=True)
st.sidebar.write("")

uploaded_txt = st.sidebar.file_uploader("TXT 파일", type=["txt"], help="텍스트 파일을 올리면 자동으로 회차를 분석합니다.")
uploaded_cover = st.sidebar.file_uploader("표지 이미지", type=["jpg", "jpeg", "png", "webp"], help="선택 사항입니다.")

raw_text = ""
chapters = []
error_message = ""
if uploaded_txt is not None:
    try:
        raw_text = decode_text(uploaded_txt.getvalue())
        normalized = normalize_text(raw_text)
        if normalized:
            raw_text = normalized
    except Exception as exc:  # noqa: BLE001
        error_message = str(exc)

st.sidebar.divider()
st.sidebar.markdown("### 책 정보")
auto_title_from_filename = st.sidebar.checkbox(
    "TXT 파일명으로 제목 자동 입력",
    value=True,
    help="TXT를 올리면 파일명에서 확장자를 뺀 이름을 제목 칸에 자동으로 넣습니다. 직접 제목을 쓰고 싶으면 끄거나 제목 칸을 수정하세요.",
)

if "book_title" not in st.session_state:
    st.session_state["book_title"] = ""

if uploaded_txt is not None:
    current_txt_name = uploaded_txt.name
    guessed_title = title_from_uploaded_filename(current_txt_name)
    previous_txt_name = st.session_state.get("_last_uploaded_txt_name")

    if previous_txt_name != current_txt_name:
        st.session_state["_last_uploaded_txt_name"] = current_txt_name
        if auto_title_from_filename and (
            not st.session_state.get("book_title", "").strip()
            or st.session_state.get("_title_was_auto_filled", False)
        ):
            st.session_state["book_title"] = guessed_title
            st.session_state["_title_was_auto_filled"] = True

book_title = st.sidebar.text_input("제목", key="book_title", placeholder="TXT 파일명에서 자동 입력 가능")
if uploaded_txt is not None and auto_title_from_filename:
    st.sidebar.caption(f"자동 제목 후보: {title_from_uploaded_filename(uploaded_txt.name)}")
book_author = st.sidebar.text_input("작가", value="")
book_maker = st.sidebar.text_input("EPUB 제작자", value="", placeholder="비워두면 표시하지 않음")

st.sidebar.divider()
st.sidebar.markdown("### 구성")
theme_labels = {theme.label: key for key, theme in THEMES.items()}
theme_label = st.sidebar.selectbox("테마", list(theme_labels.keys()), index=0)
theme_key = theme_labels[theme_label]
theme = get_theme(theme_key)
scene_mark = st.sidebar.text_input("전환마크를 바꿔 표시", value=theme.ornament)

with st.sidebar.expander("본문 스타일", expanded=False):
    auto_indent = st.checkbox(
        "본문 자동 들여쓰기 사용",
        value=True,
        help="끄면 본문 문단의 text-indent를 0으로 두어 자동 들여쓰기를 하지 않습니다.",
    )
    use_font_style = st.checkbox(
        "본문 글꼴 지정 사용",
        value=True,
        help="끄면 EPUB CSS에서 font-family를 지정하지 않아 리더앱의 기본 글꼴을 따릅니다.",
    )
    font_options = [key for key in FONT_PRESETS.keys() if key != "reader"]
    font_labels = {FONT_PRESETS[key][0]: key for key in font_options}
    font_label = st.selectbox(
        "본문 글꼴",
        list(font_labels.keys()),
        index=list(font_labels.values()).index("serif"),
        disabled=not use_font_style,
        help="외부 폰트 파일을 넣지 않는 글꼴은 리더/기기에 설치된 글꼴 후보를 CSS에 적는 방식입니다.",
    )
    font_key = font_labels[font_label] if use_font_style else "reader"
    custom_font_upload = None
    if use_font_style and font_key == "custom":
        custom_font_upload = st.file_uploader(
            "동봉할 폰트 파일",
            type=["ttf", "otf", "woff", "woff2"],
            help="폰트 파일을 EPUB 내부 Fonts 폴더에 넣고 @font-face로 연결합니다.",
        )
        st.warning(
            "외부 폰트를 동봉하면 EPUB 용량이 커지고, 일부 리더에서는 폰트가 무시되거나 오류가 날 수 있습니다. "
            "폰트 사용 권한/라이선스도 직접 확인해주세요.",
            icon="⚠️",
        )
    st.caption("기본값은 기존처럼 자동 들여쓰기 ON, 글꼴 지정 ON입니다. 불편하면 여기서 끄면 됩니다.")

include_title_page = st.sidebar.checkbox("새 표제지 넣기", value=True)
include_toc_page = st.sidebar.checkbox(
    "꾸민 목차 페이지 생성",
    value=True,
    help="끄면 EPUB 안의 별도 목차.xhtml 페이지는 만들지 않습니다. 단, 리더 앱의 내장 목차/nav는 그대로 생성됩니다.",
)
remove_original_start = st.sidebar.checkbox(
    "기존 제목만 있는 시작페이지 제거",
    value=True,
    disabled=not include_title_page,
    help="TXT 맨 앞에 제목/작가만 있는 페이지가 들어왔을 때 새 표제지와 중복되지 않게 제거합니다.",
)
remove_imported_toc = st.sidebar.checkbox(
    "TXT에 포함된 원본 목차 자동 제거",
    value=True,
    help="단행본 TXT 앞부분에 목차 페이지가 같이 들어와 회차가 두 번 잡힐 때, 내용이 거의 없는 중복 회차를 자동으로 제거합니다.",
)
remove_repeated_title_headers = st.sidebar.checkbox(
    "회차 위 반복 작품제목 제거",
    value=False,
    help="소설제목 → 빈 줄 → 1화처럼 각 회차 바로 위에 작품 제목이 반복될 때만 켜세요. 작품명과 같은 줄 바로 아래에 회차 제목이 있을 때만 제거합니다.",
)
repeated_header_text = st.sidebar.text_input(
    "제거할 반복 머리말",
    value="",
    placeholder="비우면 작품 제목 사용",
    disabled=not remove_repeated_title_headers,
    help="작품 제목과 다른 문구가 반복될 때 입력하세요. 예: 소설제목, 작품명, Copyright 등",
)
st.sidebar.divider()

with st.sidebar.expander("📌 목차 찾기 프리셋", expanded=True):
    if not raw_text:
        st.caption("TXT를 올리면 각 프리셋이 몇 개 잡히는지 같이 표시됩니다.")
        st.caption("정규식을 몰라도 작품 형식에 맞는 목록을 골라 적용할 수 있습니다.")
    else:
        presets = get_pattern_preset_candidates(raw_text)
        preset_by_name = {p.name: p for p in presets}

        st.caption("자동감지만 믿지 말고, 작품에 맞는 방식을 직접 골라볼 수 있습니다. 여러 개를 함께 선택해도 됩니다.")
        bundle_cols = st.columns(2)
        bundle_items = list(PRESET_BUNDLES.items())
        for i, (bundle_name, names) in enumerate(bundle_items):
            with bundle_cols[i % 2]:
                if st.button(bundle_name, key=f"bundle_{bundle_name}"):
                    regexes = [preset_by_name[name].regex for name in names if name in preset_by_name]
                    apply_regex_bundle(regexes, append=False)
                    st.rerun()

        labels = []
        label_to_regex = {}
        for p in presets:
            ex = " / ".join(p.examples[:2]) if p.examples else "예시 없음"
            label = f"{p.name} · {p.count}개 · {ex}"
            labels.append(label)
            label_to_regex[label] = p.regex

        selected_presets = st.multiselect(
            "직접 고를 패턴",
            options=labels,
            default=[label for label in labels if "개 ·" in label and not label.startswith("PART") and not "0개" in label][:3],
            help="예: Prologue와 1. 제목을 같이 잡아야 하면 두 패턴을 함께 선택하세요.",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("선택 프리셋만 사용", key="use_selected_presets", disabled=not selected_presets):
                apply_regex_bundle([label_to_regex[x] for x in selected_presets], append=False)
                st.rerun()
        with c2:
            if st.button("선택 프리셋 추가", key="add_selected_presets", disabled=not selected_presets):
                apply_regex_bundle([label_to_regex[x] for x in selected_presets], append=True)
                st.rerun()

        with st.expander("프리셋 상세 보기", expanded=False):
            for p in presets:
                st.markdown(f"**{p.name}** · `{p.count}`개")
                st.caption(p.description)
                if p.examples:
                    st.caption("예: " + " / ".join(p.examples[:5]))
                st.code(p.regex, language="regex")

with st.sidebar.expander("✨ 목차 패턴 자동감지", expanded=False):
    if not raw_text:
        st.caption("TXT를 올리면 회차 후보를 자동으로 보여드립니다.")
    else:
        candidates = suggest_chapter_patterns(raw_text)
        if candidates:
            st.caption("정규식을 몰라도 아래 후보 중 하나를 눌러 적용할 수 있습니다.")
            for i, candidate in enumerate(candidates[:6], start=1):
                st.markdown(f"**{candidate.name}** · `{candidate.count}`개")
                st.caption(candidate.description)
                st.caption("예: " + " / ".join(candidate.examples[:4]))
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("이 패턴만 사용", key=f"use_pattern_{i}"):
                        apply_chapter_regex(candidate.regex, append=False)
                        st.rerun()
                with c2:
                    if st.button("규칙에 추가", key=f"add_pattern_{i}"):
                        apply_chapter_regex(candidate.regex, append=True)
                        st.rerun()
        else:
            st.warning("자동 후보를 찾지 못했습니다. 아래에서 샘플 줄이나 직접 정규식을 사용해주세요.")

        samples = sample_title_like_lines(raw_text, limit=80)
        if samples:
            selected_sample = st.selectbox("샘플 줄을 골라 정규식 만들기", samples, index=0)
            generated = regex_from_example_line(selected_sample)
            st.code(generated, language="regex")
            if st.button("선택한 줄 기준으로 적용", key="apply_sample_regex"):
                apply_chapter_regex(generated, append=False)
                st.rerun()

with st.sidebar.expander("🧭 예시로 패턴 만들기", expanded=True):
    st.caption("정규식을 몰라도 목차가 되는 줄 몇 개를 그대로 붙여넣으면 자동으로 규칙을 만듭니다.")
    example_lines_text = st.text_area(
        "목차 예시 줄",
        value="",
        placeholder="예:\n1.\n2.\n3.\n\n또는\n01.\n02.\n03.",
        height=130,
    )
    generated_from_examples = regex_from_example_lines(example_lines_text) if example_lines_text.strip() else ""
    if generated_from_examples:
        st.caption("생성된 정규식")
        st.code(generated_from_examples, language="regex")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("예시 패턴만 사용", disabled=not bool(generated_from_examples)):
            apply_chapter_regex(generated_from_examples, append=False)
            st.rerun()
    with c2:
        if st.button("예시 패턴 추가", disabled=not bool(generated_from_examples)):
            apply_chapter_regex(generated_from_examples, append=True)
            st.rerun()
    st.caption("적용하면 기본 회차 규칙은 자동으로 꺼집니다. 필요하면 아래에서 다시 켤 수 있습니다.")

with st.sidebar.expander("회차 정규식 직접 추가", expanded=False):
    use_default_chapter_patterns = st.checkbox(
        "기본 회차 규칙도 같이 사용",
        key="use_default_chapter_patterns",
        help="끄면 아래에 직접 적은 정규식만 사용합니다. 예: 화$만 적용하고 싶을 때 끄세요.",
    )
    custom_chapter_regex = st.text_area("회차 감지 규칙", key="chapter_regex_text", height=190)
    st.caption("//로 시작하는 줄은 설명으로 무시됩니다. '~화$'가 아니라 '화$' 또는 '^\d+\s*화$'처럼 적어주세요.")

with st.sidebar.expander("전환마크 직접 추가", expanded=False):
    custom_scene_regex = st.text_area("전환마크 감지 규칙", value=DEFAULT_SCENE_HELP, height=145)
    st.caption("*, ***, ♧처럼 문자 그대로 적어도 됩니다.")

with st.sidebar.expander("특수 공백 처리", expanded=False):
    preserve_long_blanks = st.checkbox(
        "긴 빈 줄을 <br> 공백으로 보존",
        value=False,
        help="*** 대신 긴 엔터 공백으로 장면 전환을 넣은 TXT에서만 켜세요. 일반 작품에서는 꺼두는 것을 추천합니다.",
    )
    long_blank_threshold = st.number_input(
        "몇 줄 이상을 긴 공백으로 볼까요?",
        min_value=2,
        max_value=12,
        value=3,
        step=1,
        disabled=not preserve_long_blanks,
        help="예: 3으로 두면 빈 줄 3개 이상만 <br>로 보존하고, 빈 줄 1~2개는 일반 여백처럼 처리합니다.",
    )
    st.caption("기본값은 꺼짐입니다. 켜면 긴 빈 줄은 삭제하지 않고 EPUB 안에 빈 줄 수만큼 <br> 블록으로 넣습니다.")

# Remove helper comment lines before processing.
custom_chapter_regex_clean = "\n".join(
    line for line in custom_chapter_regex.splitlines() if line.strip() and not line.strip().startswith("//")
)
custom_scene_regex_clean = "\n".join(
    line for line in custom_scene_regex.splitlines() if line.strip() and not line.strip().startswith("//")
)

# ---------- Main ----------
st.markdown(
    """
    <div class="hero">
      <h1>TXT → EPUB Studio <span style="font-size:1rem; opacity:.65;">v2.8</span></h1>
      <p>텍스트를 올리면 회차를 자동 감지하고, 표지·표제지·선택형 목차·테마 CSS를 넣은 EPUB으로 만들어줍니다.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if uploaded_txt is not None and raw_text and not error_message:
    try:
        chapters = analyze_chapters(
            raw_text,
            custom_chapter_regex_clean,
            book_title,
            book_author,
            book_maker,
            include_title_page,
            remove_original_start,
            use_default_chapter_patterns,
            remove_imported_toc,
            remove_repeated_title_headers,
            repeated_header_text,
        )
    except Exception as exc:  # noqa: BLE001
        error_message = str(exc)

# 사용자가 잘못 잡힌 항목을 제외하면, EPUB/목차/본문 미리보기는 이 최종 목록을 사용합니다.
if chapters:
    _valid_exclude_options = {(chapter.index, chapter_option_label(chapter)) for chapter in chapters}
    excluded_ids_for_export = {
        idx
        for idx, label in st.session_state.get("manual_excluded_chapters", [])
        if (idx, label) in _valid_exclude_options
    }
else:
    excluded_ids_for_export = set()
export_chapters_global = merge_excluded_chapters(chapters, excluded_ids_for_export) if chapters else []

left, right = st.columns([.92, 1.08], gap="large")

with left:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("1. 업로드 / 표지")
    if uploaded_cover:
        st.image(uploaded_cover, caption="표지 미리보기", use_container_width=True)
    else:
        st.info("표지를 선택하면 여기에서 바로 미리볼 수 있습니다.")

    if uploaded_txt:
        st.success(f"TXT 업로드 완료: {uploaded_txt.name}")
        st.caption(f"본문 글자 수: {len(raw_text):,}자")
    else:
        st.warning("먼저 TXT 파일을 올려주세요.")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("2. 회차 분석 결과")
    if error_message:
        st.error(error_message)
    elif chapters:
        st.success(f"총 {len(chapters)}개 구간을 감지했습니다.")
        if custom_chapter_regex_clean.strip():
            st.caption("직접 입력한 회차 규칙: " + " / ".join(custom_chapter_regex_clean.splitlines()[:5]))
        st.caption("기본 회차 규칙 사용: " + ("켜짐 — 직접 입력 규칙과 기본 규칙을 함께 사용" if use_default_chapter_patterns else "꺼짐 — 직접 입력한 규칙만 사용"))
        st.caption("원본 목차 자동 제거: " + ("켜짐" if remove_imported_toc else "꺼짐"))
        st.caption("회차 위 반복 작품제목 제거: " + ("켜짐" if remove_repeated_title_headers else "꺼짐"))
        chapter_titles = [f"{chapter.index:03d}. {chapter.title}" for chapter in chapters[:300]]
        st.text_area("감지된 회차", value="\n".join(chapter_titles), height=180)
        if len(chapters) > 300:
            st.caption("300개까지만 미리보기로 표시했습니다. EPUB 생성에는 전체가 들어갑니다.")

        st.markdown("#### 잘못 잡힌 회차 제외")
        st.caption("본문 문장이 회차처럼 잡혔다면 여기서 선택하세요. 제외한 항목은 삭제하지 않고 바로 앞 회차 본문으로 되돌립니다.")
        suspect_ids = suspicious_chapter_indices(chapters)
        if suspect_ids:
            suspect_text = ", ".join(str(i).zfill(3) for i in suspect_ids[:20])
            st.warning(f"확인 추천 항목: {suspect_text}" + (" …" if len(suspect_ids) > 20 else ""))
        exclude_options = [(chapter.index, chapter_option_label(chapter)) for chapter in chapters]
        if st.button("의심 항목을 제외 목록에 넣기", disabled=not bool(suspect_ids), key="fill_suspects"):
            st.session_state["manual_excluded_chapters"] = [opt for opt in exclude_options if opt[0] in suspect_ids]
            st.rerun()
        if "manual_excluded_chapters" in st.session_state:
            st.session_state["manual_excluded_chapters"] = [
                opt for opt in st.session_state.get("manual_excluded_chapters", []) if opt in exclude_options
            ]
        manual_excluded = st.multiselect(
            "목차에서 제외할 항목",
            options=exclude_options,
            format_func=excluded_option_label,
            key="manual_excluded_chapters",
        )
        excluded_ids = {idx for idx, _label in manual_excluded}
        export_chapters = merge_excluded_chapters(chapters, excluded_ids)
        if excluded_ids:
            st.success(f"EPUB 생성 시 {len(excluded_ids)}개 항목을 목차에서 제외하고, 최종 {len(export_chapters)}개 구간으로 만듭니다.")
            with st.expander("제외 적용 후 목차 미리보기", expanded=False):
                st.text_area("최종 목차", value="\n".join(f"{c.index:03d}. {c.title}" for c in export_chapters[:300]), height=180)
    elif uploaded_txt:
        st.warning("회차를 감지하지 못했습니다. 그래도 본문 1개 구간으로 만들 수 있습니다.")
    else:
        st.caption("TXT를 올리면 회차가 표시됩니다.")
    st.markdown('</div>', unsafe_allow_html=True)

with right:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("3. 미리보기")

    tab_cover, tab_title, tab_toc, tab_body = st.tabs(["표지", "표제지", "목차", "본문"])

    with tab_cover:
        if uploaded_cover:
            preview_document(cover_html_from_upload(uploaded_cover), theme_key, height=620)
        else:
            st.info("표지 이미지가 없습니다.")

    with tab_title:
        if include_title_page:
            preview_document(title_page_body(book_title, book_author, book_maker, theme_key), theme_key, height=620)
        else:
            st.info("새 표제지 넣기가 꺼져 있습니다.")

    with tab_toc:
        if not include_toc_page:
            st.info("꾸민 목차 페이지 생성이 꺼져 있습니다. EPUB 내부 목차/nav는 유지되므로 리더기의 목차 버튼에서는 회차가 보입니다.")
        elif export_chapters_global:
            preview_document(
                toc_page_body(
                    book_title,
                    export_chapters_global[:80],
                    include_title_page=include_title_page,
                    include_cover_page=uploaded_cover is not None,
                    theme_key=theme_key,
                ),
                theme_key,
                height=620,
            )
            if len(export_chapters_global) > 80:
                st.caption("목차 미리보기는 80개까지만 표시됩니다. EPUB에는 전체 목차가 들어갑니다.")
        else:
            st.info("TXT를 올리면 목차 미리보기가 표시됩니다.")

    with tab_body:
        if export_chapters_global:
            sample = export_chapters_global[0]
            body = chapter_to_xhtml_body(
                sample,
                scene_mark=scene_mark or theme.ornament,
                custom_scene_regex_text=custom_scene_regex_clean,
                preserve_long_blanks=preserve_long_blanks,
                long_blank_threshold=int(long_blank_threshold),
            )
            preview_document(body, theme_key, height=620)
        else:
            st.info("TXT를 올리면 본문 미리보기가 표시됩니다.")
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("4. EPUB 만들기")

col_a, col_b, col_c = st.columns([1, 1, 2])
with col_a:
    output_basename = st.text_input("파일명", value=sanitize_filename(book_title or "book"))
with col_b:
    st.write("")
    st.write("")
    make_button = st.button("EPUB 생성", type="primary", use_container_width=True)

if make_button:
    if uploaded_txt is None:
        st.error("TXT 파일을 먼저 올려주세요.")
    elif font_key == "custom" and custom_font_upload is None:
        st.error("외부 폰트 파일 동봉을 선택했다면 폰트 파일을 먼저 올려주세요. 또는 본문 글꼴을 다른 항목으로 바꿔주세요.")
    else:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                txt_text = raw_text or decode_text(uploaded_txt.getvalue())

                cover_path: Optional[Path] = None
                if uploaded_cover is not None:
                    suffix = Path(uploaded_cover.name).suffix.lower() or ".jpg"
                    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                        suffix = ".jpg"
                    cover_path = tmpdir_path / f"cover{suffix}"
                    cover_path.write_bytes(uploaded_cover.getvalue())

                font_path: Optional[Path] = None
                if font_key == "custom" and custom_font_upload is not None:
                    suffix = Path(custom_font_upload.name).suffix.lower()
                    if suffix not in {".ttf", ".otf", ".woff", ".woff2"}:
                        suffix = ".ttf"
                    font_path = tmpdir_path / f"user_font{suffix}"
                    font_path.write_bytes(custom_font_upload.getvalue())

                output_path = tmpdir_path / f"{sanitize_filename(output_basename)}.epub"
                made_chapters = build_epub(
                    text=txt_text,
                    output_path=output_path,
                    title=book_title or sanitize_filename(Path(uploaded_txt.name).stem),
                    author=book_author,
                    maker=book_maker,
                    cover_path=cover_path,
                    theme_key=theme_key,
                    scene_mark=scene_mark or theme.ornament,
                    custom_regex_text=custom_chapter_regex_clean,
                    custom_scene_regex_text=custom_scene_regex_clean,
                    include_title_page=include_title_page,
                    include_toc_page=include_toc_page,
                    remove_original_start_page=bool(remove_original_start and include_title_page),
                    use_default_chapter_patterns=use_default_chapter_patterns,
                    remove_imported_toc=remove_imported_toc,
                    remove_repeated_title_headers=remove_repeated_title_headers,
                    repeated_header_text=repeated_header_text,
                    chapters_override=export_chapters_global if export_chapters_global else None,
                    preserve_long_blanks=preserve_long_blanks,
                    long_blank_threshold=int(long_blank_threshold),
                    auto_indent=auto_indent,
                    font_key=font_key,
                    custom_font_path=font_path,
                )
                epub_bytes = output_path.read_bytes()

            st.success(f"완료되었습니다. 감지된 본문 구간: {len(made_chapters)}개")
            st.download_button(
                "EPUB 다운로드",
                data=epub_bytes,
                file_name=f"{sanitize_filename(output_basename)}.epub",
                mime="application/epub+zip",
                use_container_width=True,
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"EPUB 생성 실패: {exc}")

st.markdown(
    '<p class="small-note">업로드한 TXT와 표지는 EPUB 생성에만 사용됩니다. 공개 서버에 배포하는 경우, 파일이 앱 서버를 거쳐 처리된다는 점은 안내해두는 편이 좋습니다.</p>',
    unsafe_allow_html=True,
)
st.markdown('</div>', unsafe_allow_html=True)

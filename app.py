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
    normalize_text,
    split_chapters,
    strip_original_start_page,
)
from themes import THEMES, epub_css, get_theme


st.set_page_config(
    page_title="TXT → EPUB Studio",
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


def preview_document(body: str, theme_key: str, height: int = 620) -> None:
    css = epub_css(theme_key)
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


def analyze_chapters(raw_text: str, custom_regex_text: str, title: str, author: str, maker: str, include_title: bool, remove_start: bool):
    chapters = split_chapters(raw_text, custom_regex_text=custom_regex_text, fallback_title=title or "본문")
    if include_title and remove_start:
        chapters = strip_original_start_page(chapters, title=title, author=author, maker=maker)
    return chapters


# ---------- Sidebar ----------
st.sidebar.markdown("## 📚 EPUB Studio")
st.sidebar.markdown('<span class="badge">TXT → EPUB 웹 제작기</span>', unsafe_allow_html=True)
st.sidebar.write("")

uploaded_txt = st.sidebar.file_uploader("TXT 파일", type=["txt"], help="텍스트 파일을 올리면 자동으로 회차를 분석합니다.")
uploaded_cover = st.sidebar.file_uploader("표지 이미지", type=["jpg", "jpeg", "png", "webp"], help="선택 사항입니다.")

st.sidebar.divider()
st.sidebar.markdown("### 책 정보")
book_title = st.sidebar.text_input("제목", value="")
book_author = st.sidebar.text_input("작가", value="")
book_maker = st.sidebar.text_input("EPUB 제작자", value="", placeholder="비워두면 표시하지 않음")

st.sidebar.divider()
st.sidebar.markdown("### 구성")
theme_labels = {theme.label: key for key, theme in THEMES.items()}
theme_label = st.sidebar.selectbox("테마", list(theme_labels.keys()), index=0)
theme_key = theme_labels[theme_label]
theme = get_theme(theme_key)
scene_mark = st.sidebar.text_input("전환마크를 바꿔 표시", value=theme.ornament)

include_title_page = st.sidebar.checkbox("새 표제지 넣기", value=True)
remove_original_start = st.sidebar.checkbox(
    "기존 제목만 있는 시작페이지 제거",
    value=True,
    disabled=not include_title_page,
    help="TXT 맨 앞에 제목/작가만 있는 페이지가 들어왔을 때 새 표제지와 중복되지 않게 제거합니다.",
)
st.sidebar.divider()
with st.sidebar.expander("회차 정규식 직접 추가", expanded=False):
    custom_chapter_regex = st.text_area("회차 감지 규칙", value=DEFAULT_CHAPTER_HELP, height=170)
    st.caption("//로 시작하는 줄은 설명으로 무시됩니다.")

with st.sidebar.expander("전환마크 직접 추가", expanded=False):
    custom_scene_regex = st.text_area("전환마크 감지 규칙", value=DEFAULT_SCENE_HELP, height=145)
    st.caption("*, ***, ♧처럼 문자 그대로 적어도 됩니다.")

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
      <h1>TXT → EPUB Studio</h1>
      <p>텍스트를 올리면 회차를 자동 감지하고, 표지·표제지·목차·테마 CSS를 넣은 EPUB으로 만들어줍니다.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

raw_text = ""
chapters = []
error_message = ""

if uploaded_txt is not None:
    try:
        raw_text = decode_text(uploaded_txt.getvalue())
        normalized = normalize_text(raw_text)
        if normalized:
            raw_text = normalized
        chapters = analyze_chapters(
            raw_text,
            custom_chapter_regex_clean,
            book_title,
            book_author,
            book_maker,
            include_title_page,
            remove_original_start,
        )
    except Exception as exc:  # noqa: BLE001
        error_message = str(exc)

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
        chapter_titles = [f"{chapter.index:03d}. {chapter.title}" for chapter in chapters[:300]]
        st.text_area("감지된 회차", value="\n".join(chapter_titles), height=280)
        if len(chapters) > 300:
            st.caption("300개까지만 미리보기로 표시했습니다. EPUB 생성에는 전체가 들어갑니다.")
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
        if chapters:
            preview_document(
                toc_page_body(
                    book_title,
                    chapters[:80],
                    include_title_page=include_title_page,
                    include_cover_page=uploaded_cover is not None,
                    theme_key=theme_key,
                ),
                theme_key,
                height=620,
            )
            if len(chapters) > 80:
                st.caption("목차 미리보기는 80개까지만 표시됩니다. EPUB에는 전체 목차가 들어갑니다.")
        else:
            st.info("TXT를 올리면 목차 미리보기가 표시됩니다.")

    with tab_body:
        if chapters:
            sample = chapters[0]
            body = chapter_to_xhtml_body(sample, scene_mark=scene_mark or theme.ornament, custom_scene_regex_text=custom_scene_regex_clean)
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
                    remove_original_start_page=bool(remove_original_start and include_title_page),
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

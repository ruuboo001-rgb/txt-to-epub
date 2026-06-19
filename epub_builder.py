from __future__ import annotations

import html
import uuid
from pathlib import Path
from typing import List, Optional

from ebooklib import epub

from text_parser import Chapter, chapter_to_xhtml_body, reindex_chapters, split_chapters, strip_original_start_page
from themes import epub_css, get_theme


def _guess_cover_name(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        return "Images/cover.jpg"
    # EPUB 내부 경로입니다. 한글/공백 파일명 대신 안정적인 이름을 씁니다.
    return "Images/cover" + suffix


def _relative_from_text(internal_path: str) -> str:
    # Text/*.xhtml에서 Images/cover.jpg를 바라보는 상대 경로입니다.
    return "../" + internal_path if not internal_path.startswith("../") else internal_path


def cover_page_body(cover_src: str) -> str:
    return f'''
<div class="cover-page">
  <img class="cover-image" src="{html.escape(cover_src)}" alt="cover" />
</div>
'''.strip()


def title_page_body(title: str, author: str, maker: str, theme_key: str) -> str:
    theme = get_theme(theme_key)
    title_line = html.escape(title.strip() or "무제")
    author_line = html.escape(author.strip()) if author.strip() else ""
    maker_line = html.escape(maker.strip()) if maker.strip() else ""

    author_html = f'<p class="book-author">{author_line}</p>' if author_line else ""
    maker_html = ""
    if maker_line:
        maker_html = f'''
        <p class="book-maker-label">EPUB 제작</p>
        <p class="book-maker">{maker_line}</p>
        '''.strip()

    return f'''
<div class="title-page">
  <div class="title-card">
    <p class="title-ornament">{html.escape(theme.ornament)}</p>
    <h1 class="book-title">{title_line}</h1>
    {author_html}
    <p class="title-ornament">{html.escape(theme.ornament)}</p>
    {maker_html}
  </div>
</div>
'''.strip()


def toc_page_body(
    title: str,
    chapters: List[Chapter],
    include_title_page: bool,
    include_cover_page: bool = False,
    theme_key: str = "rose",
) -> str:
    theme = get_theme(theme_key)
    title_line = html.escape(title.strip() or "무제")
    cover_link = '<li class="toc-item"><a href="cover.xhtml">표지</a></li>' if include_cover_page else ""
    title_link = '<li class="toc-item"><a href="title_page.xhtml">표제지</a></li>' if include_title_page else ""
    chapter_links = []
    for i, chapter in enumerate(chapters, start=1):
        chapter_links.append(
            f'<li class="toc-item"><a href="Section{i:04d}.xhtml">{html.escape(chapter.title)}</a></li>'
        )

    return f'''
<div class="toc-page">
  <div class="toc-card">
    <p class="toc-ornament">{html.escape(theme.ornament)}</p>
    <h1 class="toc-title">목차</h1>
    <p class="toc-book-title">{title_line}</p>
    <ol class="toc-list">
      {cover_link}
      {title_link}
      {''.join(chapter_links)}
    </ol>
  </div>
</div>
'''.strip()


def build_epub(
    *,
    text: str,
    output_path: str | Path,
    title: str,
    author: str = "",
    maker: str = "",
    cover_path: Optional[str | Path] = None,
    theme_key: str = "rose",
    scene_mark: Optional[str] = None,
    custom_regex_text: str = "",
    custom_scene_regex_text: str = "",
    include_title_page: bool = True,
    remove_original_start_page: bool = True,
    use_default_chapter_patterns: bool = True,
    remove_imported_toc: bool = False,
    chapters_override: Optional[List[Chapter]] = None,
    preserve_long_blanks: bool = False,
    long_blank_threshold: int = 3,
) -> List[Chapter]:
    """TXT 내용을 EPUB으로 저장하고, 생성된 챕터 목록을 반환합니다."""
    title = title.strip() or "무제"
    author = author.strip()
    maker = maker.strip()
    theme = get_theme(theme_key)
    scene_mark = scene_mark or theme.ornament

    if chapters_override is not None:
        chapters = reindex_chapters([Chapter(ch.title, ch.lines[:], ch.index) for ch in chapters_override])
    else:
        chapters = split_chapters(
            text,
            custom_regex_text=custom_regex_text,
            fallback_title=title,
            use_default_patterns=use_default_chapter_patterns,
            remove_imported_toc=remove_imported_toc,
        )
        if include_title_page and remove_original_start_page:
            chapters = strip_original_start_page(chapters, title=title, author=author, maker=maker)
    if not chapters:
        raise ValueError("TXT 본문이 비어 있습니다. TXT 파일 내용을 확인해주세요.")

    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(title)
    book.set_language("ko")
    if author:
        book.add_author(author)
    if maker:
        book.add_metadata("DC", "contributor", maker)

    style = epub.EpubItem(
        uid="style_nav",
        file_name="Styles/Style0001.css",
        media_type="text/css",
        content=epub_css(theme_key),
    )
    book.add_item(style)

    cover_page: Optional[epub.EpubHtml] = None
    if cover_path:
        cover_path = Path(cover_path)
        if cover_path.exists():
            cover_name = _guess_cover_name(cover_path)
            # 표지 이미지는 메타데이터 cover로 등록하고, 실제 첫 장에는 별도의 선형 cover.xhtml을 넣습니다.
            # 이렇게 해야 일부 리더에서 nav.xhtml이 먼저 열리는 문제를 줄일 수 있습니다.
            book.set_cover(cover_name, cover_path.read_bytes(), create_page=False)
            cover_page = epub.EpubHtml(uid="cover_page", title="표지", file_name="Text/cover.xhtml", lang="ko")
            cover_page.content = cover_page_body(_relative_from_text(cover_name))
            cover_page.add_link(href="../Styles/Style0001.css", rel="stylesheet", type="text/css")
            book.add_item(cover_page)
            book.guide.append({"type": "cover", "title": "표지", "href": "Text/cover.xhtml"})

    title_page: Optional[epub.EpubHtml] = None
    if include_title_page:
        title_page = epub.EpubHtml(uid="title_page", title="표제지", file_name="Text/title_page.xhtml", lang="ko")
        title_page.content = title_page_body(title, author, maker, theme_key)
        title_page.add_link(href="../Styles/Style0001.css", rel="stylesheet", type="text/css")
        book.add_item(title_page)

    toc_page = epub.EpubHtml(uid="toc_page", title="목차", file_name="Text/toc.xhtml", lang="ko")
    toc_page.content = toc_page_body(
        title,
        chapters,
        include_title_page=title_page is not None,
        include_cover_page=cover_page is not None,
        theme_key=theme_key,
    )
    toc_page.add_link(href="../Styles/Style0001.css", rel="stylesheet", type="text/css")
    book.add_item(toc_page)
    book.guide.append({"type": "toc", "title": "목차", "href": "Text/toc.xhtml"})

    chapter_items: List[epub.EpubHtml] = []
    for i, chapter in enumerate(chapters, start=1):
        item = epub.EpubHtml(
            uid=f"chapter_{i:04d}",
            title=chapter.title,
            file_name=f"Text/Section{i:04d}.xhtml",
            lang="ko",
        )
        item.content = chapter_to_xhtml_body(
            chapter,
            scene_mark=scene_mark,
            custom_scene_regex_text=custom_scene_regex_text,
            preserve_long_blanks=preserve_long_blanks,
            long_blank_threshold=long_blank_threshold,
        )
        item.add_link(href="../Styles/Style0001.css", rel="stylesheet", type="text/css")
        book.add_item(item)
        chapter_items.append(item)

    toc_items: List[object] = []
    if cover_page is not None:
        toc_items.append(epub.Link("Text/cover.xhtml", "표지", "cover_page"))
    if title_page is not None:
        toc_items.append(epub.Link("Text/title_page.xhtml", "표제지", "title_page"))
    toc_items.append(epub.Link("Text/toc.xhtml", "목차", "toc_page"))
    toc_items.extend(chapter_items)
    book.toc = tuple(toc_items)

    # 읽기 순서: 표지 → 표제지 → 꾸민 목차 → 본문.
    # nav.xhtml은 manifest에는 넣지만 spine 맨 앞에 두지 않아, EPUB을 열 때 표지부터 열리도록 합니다.
    spine: List[object] = []
    if cover_page is not None:
        spine.append(cover_page)
    if title_page is not None:
        spine.append(title_page)
    spine.append(toc_page)
    spine.extend(chapter_items)
    book.spine = tuple(spine)

    book.add_item(epub.EpubNcx())
    nav = epub.EpubNav(uid="nav", file_name="Text/nav.xhtml", title="목차")
    nav.add_link(href="../Styles/Style0001.css", rel="stylesheet", type="text/css")
    book.add_item(nav)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(output_path), book, {})
    return chapters

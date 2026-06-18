from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Pattern


@dataclass
class Chapter:
    title: str
    lines: List[str]
    index: int


# 기본 회차 감지 패턴입니다.
# 사용자가 직접 정규식을 추가하면 이 기본 패턴보다 먼저 검사됩니다.
DEFAULT_CHAPTER_REGEXES = [
    r"^(?:프롤로그|프롤로그\.|prologue)(?:\s*[:：.\-–—]?\s*.*)?$",
    r"^(?:에필로그|에필로그\.|epilogue)(?:\s*[:：.\-–—]?\s*.*)?$",
    r"^(?:외전|특별편|후일담)(?:\s*[:：.\-–—]?\s*.*)?$",
    r"^(?:제\s*)?\d{1,4}\s*화(?:\s*[:：.\-–—]?\s*.*)?$",
    r"^#\s*\d{1,4}\s*(?:화|장)?(?:\s*[:：.\-–—.]?\s*.*)?$",
    r"^(?:제\s*)?\d{1,4}\s*장(?:\s*[:：.\-–—.]?\s*.*)?$",
    r"^(?![12]\d{3}\.\s*\d{1,2}\.\s*\d{1,2}\.?$)(?:0?[1-9]|[1-9]\d{1,3})\s*[.)]\s*(?!\d)(?=.{1,80}$)\S.*$",  # 01.제목 / 01. 제목 / 1) 제목. 날짜·0.1초 같은 본문 오탐 방지
    r"^(?:episode|ep)\s*\d{1,4}(?:\s*[:：.\-–—]?\s*.*)?$",
]

# 전환마크 자동 감지입니다. 한 줄짜리 * 도 전환마크로 잡습니다.
DEFAULT_SCENE_BREAK_RE = re.compile(
    r"^(?:"
    r"(?:[*＊]\s*){1,}|"              # *, ***, * * *
    r"(?:[-─—]\s*){3,}|"             # ---, ───
    r"(?:[.·]\s*){3,}|"              # ..., ···
    r"(?:[✦❖◆◇♧♣♡♥※☆★]\s*){1,5}"
    r")$"
)


_SIMPLE_P_RE = re.compile(r"^\s*<p(?:\s+[^>]*)?>\s*(.*?)\s*</p>\s*$", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def display_line_text(line: str) -> str:
    """
    일반 TXT뿐 아니라, 사용자가 실수로 <p>...</p>가 들어간 텍스트를 넣어도
    회차/전환마크 감지가 되도록 한 줄의 표시 텍스트만 뽑습니다.
    """
    raw = line.strip()
    m = _SIMPLE_P_RE.match(raw)
    if m:
        raw = m.group(1).strip()
    raw = _TAG_RE.sub("", raw)
    raw = html.unescape(raw)
    return raw.strip()


def read_text_file(path: str | Path) -> str:
    """한국 웹소설 TXT에서 자주 보이는 인코딩을 순서대로 시도합니다."""
    path = Path(path)
    encodings = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]
    last_error: Optional[Exception] = None
    for enc in encodings:
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise UnicodeDecodeError(
        "unknown",
        b"",
        0,
        1,
        f"텍스트 인코딩을 읽을 수 없습니다. 마지막 오류: {last_error}",
    )


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\ufeff", "")
    text = text.replace("\t", " ")
    text = re.sub(r"[ \u00a0]{2,}", " ", text)
    text = re.sub(r"\n{5,}", "\n\n\n\n", text)
    return text.strip()


def compile_chapter_patterns(custom_regex_text: str = "", use_default_patterns: bool = True) -> List[Pattern[str]]:
    patterns: List[str] = []
    for line_no, raw in enumerate(custom_regex_text.splitlines(), start=1):
        raw = raw.strip()
        # #로 시작하는 회차가 많으므로 #은 주석으로 보지 않습니다. 주석은 // 로만 처리합니다.
        if not raw or raw.startswith("//"):
            continue
        try:
            re.compile(raw, re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"직접 추가한 회차 정규식 {line_no}번째 줄 오류: {exc}\n\n{raw}") from exc
        patterns.append(raw)

    if use_default_patterns:
        patterns.extend(DEFAULT_CHAPTER_REGEXES)

    if not patterns:
        patterns.extend(DEFAULT_CHAPTER_REGEXES)

    return [re.compile(pattern, re.IGNORECASE) for pattern in patterns]


def compile_scene_patterns(custom_scene_regex_text: str = "") -> List[Pattern[str]]:
    """
    전환마크 감지 패턴을 만듭니다.
    사용자가 '*'처럼 정규식으로는 오류가 나는 문자를 적어도 자동으로 문자 그대로 처리합니다.
    """
    patterns: List[Pattern[str]] = []

    for line_no, raw in enumerate(custom_scene_regex_text.splitlines(), start=1):
        raw = raw.strip()
        if not raw or raw.startswith("//"):
            continue

        # 사용자가 ^...$ 형태로 넣으면 그대로 정규식으로 사용합니다.
        if raw.startswith("^") or raw.endswith("$"):
            try:
                patterns.append(re.compile(raw))
                continue
            except re.error as exc:
                raise ValueError(f"직접 추가한 전환마크 정규식 {line_no}번째 줄 오류: {exc}\n\n{raw}") from exc

        # 일반 입력은 한 줄 전체가 그 문자/패턴과 일치할 때만 잡도록 감쌉니다.
        try:
            patterns.append(re.compile(r"^\s*(?:" + raw + r")\s*$"))
        except re.error:
            # *, ***, ??? 같은 입력은 문자 그대로 처리합니다.
            patterns.append(re.compile(r"^\s*" + re.escape(raw) + r"\s*$"))

    patterns.append(DEFAULT_SCENE_BREAK_RE)
    return patterns


def is_probable_chapter_title(line: str, patterns: Iterable[Pattern[str]]) -> bool:
    s = display_line_text(line)
    if not s:
        return False
    # 너무 긴 줄은 본문일 가능성이 커서 회차 제목으로 보지 않습니다.
    if len(s) > 100:
        return False
    return any(p.match(s) for p in patterns)


def split_chapters(text: str, custom_regex_text: str = "", fallback_title: str = "본문", use_default_patterns: bool = True) -> List[Chapter]:
    text = normalize_text(text)
    if not text:
        return []

    lines = text.split("\n")
    patterns = compile_chapter_patterns(custom_regex_text, use_default_patterns=use_default_patterns)

    chapters: List[Chapter] = []
    current_title: Optional[str] = None
    current_lines: List[str] = []
    preface_lines: List[str] = []

    def flush_current() -> None:
        nonlocal current_title, current_lines
        if current_title is None:
            return
        chapters.append(Chapter(current_title, current_lines[:], len(chapters) + 1))
        current_lines = []

    for line in lines:
        stripped_for_title = display_line_text(line)
        if is_probable_chapter_title(line, patterns):
            if current_title is None:
                if preface_lines and any(display_line_text(x) for x in preface_lines):
                    chapters.append(Chapter("시작", preface_lines[:], len(chapters) + 1))
                    preface_lines = []
            else:
                flush_current()
            current_title = stripped_for_title
            current_lines = []
        else:
            if current_title is None:
                preface_lines.append(line)
            else:
                current_lines.append(line)

    if current_title is not None:
        flush_current()
    elif preface_lines:
        chapters.append(Chapter(fallback_title or "본문", preface_lines, 1))

    return reindex_chapters(chapters)


def reindex_chapters(chapters: List[Chapter]) -> List[Chapter]:
    for i, chapter in enumerate(chapters, start=1):
        chapter.index = i
    return chapters


def _norm_title_like(text: str) -> str:
    text = display_line_text(text)
    text = re.sub(r"[\s_\-·・:：.,，。'\"“”‘’『』「」《》\[\]()]", "", text)
    return text.lower()


def strip_original_start_page(
    chapters: List[Chapter],
    *,
    title: str = "",
    author: str = "",
    maker: str = "",
) -> List[Chapter]:
    """
    표제지를 새로 만들 때 TXT 맨 앞에 남아 있던 제목만 있는 시작 페이지를 제거합니다.
    실제 프롤로그/본문이 들어 있는 긴 시작 구간은 되도록 건드리지 않습니다.
    """
    if len(chapters) <= 1:
        return chapters

    first = chapters[0]
    first_title_norm = _norm_title_like(first.title)
    known_norms = [_norm_title_like(x) for x in [title, author, maker] if x.strip()]
    known_norms = [x for x in known_norms if x]
    nonblank = [display_line_text(line) for line in first.lines if display_line_text(line)]
    nonblank_norms = [_norm_title_like(x) for x in nonblank]

    def matches_known(value: str) -> bool:
        if not value:
            return True
        return any(value == known or value in known or known in value for known in known_norms)

    # TXT 앞부분이 회차가 아니라 표제지로 들어온 일반적인 경우: Chapter(title="시작", lines=[제목, 작가...])
    if first.title == "시작":
        if not nonblank:
            return reindex_chapters(chapters[1:])
        if len(nonblank) <= 8:
            unknown = [line for line, norm in zip(nonblank, nonblank_norms) if not matches_known(norm)]
            # "장편소설", "완결", "EPUB 제작" 같은 표제지성 문구는 제거 대상에 포함합니다.
            unknown = [
                line for line in unknown
                if not re.search(r"(장편소설|완결|외전\s*포함|epub|이펍|펍\s*제작|제작|newtoki)", line, re.I)
            ]
            if len(unknown) <= 1 and (known_norms or len(nonblank) <= 3):
                return reindex_chapters(chapters[1:])

    # 첫 챕터 제목 자체가 작품 제목이고 내용이 거의 없으면 기존 제목 페이지로 봅니다.
    if known_norms and first_title_norm and matches_known(first_title_norm) and len(nonblank) <= 4:
        return reindex_chapters(chapters[1:])

    return chapters


def safe_id(text: str, index: int = 0) -> str:
    slug = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", text.strip())
    slug = slug.strip("-")[:42]
    if index:
        return f"chapter-{index:04d}-{slug or 'body'}"
    return slug or "chapter"


def _protect_soft_quotes(escaped: str) -> str:
    """HTML escape가 끝난 텍스트 안에서 짧은 괄호/인용 표현에 부드러운 스타일을 겁니다."""

    def wrap(match: re.Match[str]) -> str:
        return f'<span class="soft-quote">{match.group(0)}</span>'

    escaped = re.sub(r"\[[^\[\]\n]{1,180}\]", wrap, escaped)
    escaped = re.sub(r"「[^」\n]{1,180}」", wrap, escaped)
    escaped = re.sub(r"『[^』\n]{1,180}』", wrap, escaped)
    escaped = re.sub(r"‘[^’\n]{1,140}’", wrap, escaped)
    escaped = re.sub(r"(?<![A-Za-z0-9])'[^'\n]{2,120}'(?![A-Za-z0-9])", wrap, escaped)
    return escaped


def is_scene_break(line: str, scene_patterns: Iterable[Pattern[str]]) -> bool:
    stripped = display_line_text(line)
    if not stripped:
        return False
    return any(pattern.match(stripped) for pattern in scene_patterns)


def line_to_xhtml(
    line: str,
    scene_mark: str = "✦ ✦ ✦",
    scene_patterns: Optional[List[Pattern[str]]] = None,
) -> str:
    stripped = display_line_text(line)
    if not stripped:
        return ""

    scene_patterns = scene_patterns or compile_scene_patterns()
    if is_scene_break(stripped, scene_patterns):
        return f'<p class="scene-break">{html.escape(scene_mark)}</p>'

    escaped = _protect_soft_quotes(html.escape(stripped, quote=False))

    if stripped.startswith("[") and stripped.endswith("]") and len(stripped) <= 200:
        return f'<p class="system-line">{escaped}</p>'

    return f"<p>{escaped}</p>"


def chapter_to_xhtml_body(
    chapter: Chapter,
    scene_mark: str = "✦ ✦ ✦",
    custom_scene_regex_text: str = "",
) -> str:
    scene_patterns = compile_scene_patterns(custom_scene_regex_text)
    parts = [
        f'<section id="{safe_id(chapter.title, chapter.index)}">',
        f'<h1 class="chapter-title">{html.escape(chapter.title)}</h1>',
    ]
    previous_blank = False
    for line in chapter.lines:
        if not display_line_text(line):
            previous_blank = True
            continue
        block = line_to_xhtml(line, scene_mark, scene_patterns)
        if block:
            if previous_blank and len(parts) > 2:
                parts.append('<div class="soft-space"></div>')
            parts.append(block)
        previous_blank = False
    parts.append("</section>")
    return "\n".join(parts)

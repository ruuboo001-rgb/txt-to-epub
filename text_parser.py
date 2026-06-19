from __future__ import annotations

from collections import Counter
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


@dataclass
class PatternCandidate:
    name: str
    regex: str
    count: int
    examples: List[str]
    description: str = ""


# 기본 회차 감지 패턴입니다.
# 사용자가 직접 정규식을 추가하면 이 기본 패턴보다 먼저 검사됩니다.
DEFAULT_CHAPTER_REGEXES = [
    r"^(?:프롤로그|프롤로그\.|prologue)(?:\s*[:：.\-–—]?\s*.*)?$",
    r"^(?:에필로그|에필로그\.|epilogue)(?:\s*[:：.\-–—]?\s*.*)?$",
    r"^(?:외전|특별편|후일담)(?:\s*[:：.\-–—]?\s*.*)?$",
    r"^[<＜〈《【]\s*(?:제\s*)?\d{1,4}\s*화\s*[>＞〉》】](?:\s*$|\s+\S.*$|\s*[:：.\-–—]\s*\S.*$)",  # <1화>, 〈1화〉 같은 꺾쇠 화수
    r"^\s*(?:제\s*)?\d{1,4}\s*화\.?(?:\s*$|\s+\S.*$|\s*[:：\-–—]\s*\S.*$)",  # 1화/1화. 감지, 3화부터/3화의 같은 본문 오탐 방지
    r"^#\s*\d{1,4}\s*(?:화|장)?(?:\s*$|\s+\S.*$|\s*[:：.\-–—.]\s*\S.*$)",
    r"^(?:제\s*)?\d{1,4}\s*장(?:\s*$|\s+\S.*$|\s*[:：.\-–—.]\s*\S.*$)",  # 20장이 족히... 같은 본문 오탐 방지
    r"^(?![12]\d{3}\.\s*\d{1,2}\.\s*\d{1,2}\.?$)(?:0?[1-9]|[1-9]\d{1,3})\s*[.)]\s*(?!\d)(?=.{1,80}$)\S.*$",  # 01.제목 / 01. 제목 / 1) 제목. 날짜·0.1초 같은 본문 오탐 방지
    r"^(?!(?:19|20)\d{2}\s*[.)]\s*$)\d{1,4}\s*[.)]\s*$",  # 1. / 01. / 001. 처럼 번호만 있는 단독 회차
    r"^(?:episode|ep)\s*\d{1,4}(?:\s*$|\s+\S.*$|\s*[:：.\-–—]\s*\S.*$)",
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
_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")  # <1화> 같은 회차 표기는 HTML 태그로 지우지 않습니다.


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


def split_chapters(
    text: str,
    custom_regex_text: str = "",
    fallback_title: str = "본문",
    use_default_patterns: bool = True,
    remove_imported_toc: bool = False,
) -> List[Chapter]:
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

    chapters = reindex_chapters(chapters)
    if remove_imported_toc:
        chapters = strip_imported_toc_chapters(chapters)
    return reindex_chapters(chapters)


def reindex_chapters(chapters: List[Chapter]) -> List[Chapter]:
    for i, chapter in enumerate(chapters, start=1):
        chapter.index = i
    return chapters


def merge_excluded_chapters(chapters: List[Chapter], exclude_indices: Iterable[int]) -> List[Chapter]:
    """
    사용자가 잘못 잡힌 회차를 제외했을 때, 그 내용을 삭제하지 않고 이전 챕터 본문으로 되돌립니다.

    예: 본문 문장 "3화부터 공기화되는..."가 회차로 잡혔다면 체크 해제 시
    그 문장과 뒤따르는 문단을 바로 앞 회차의 일반 본문으로 합칩니다.
    """
    excluded = {int(x) for x in exclude_indices}
    if not excluded:
        return reindex_chapters([Chapter(ch.title, ch.lines[:], ch.index) for ch in chapters])

    kept: List[Chapter] = []
    pending_front: List[str] = []

    for chapter in chapters:
        title_line = display_line_text(chapter.title)
        restored_lines = ([title_line] if title_line else []) + chapter.lines[:]
        if chapter.index in excluded:
            if kept:
                if kept[-1].lines and display_line_text(kept[-1].lines[-1]):
                    kept[-1].lines.append("")
                kept[-1].lines.extend(restored_lines)
            else:
                pending_front.extend(restored_lines)
                pending_front.append("")
            continue

        new_chapter = Chapter(chapter.title, chapter.lines[:], chapter.index)
        if pending_front:
            new_chapter.lines = pending_front[:] + new_chapter.lines
            pending_front = []
        kept.append(new_chapter)

    if not kept:
        kept = [Chapter("본문", pending_front, 1)]

    return reindex_chapters(kept)


def is_suspicious_chapter_title(title: str) -> bool:
    """자동감지된 회차 중 사용자가 확인하면 좋은 오탐 후보를 표시합니다."""
    s = display_line_text(title)
    if not s:
        return False

    # 3화부터, 3화의, 20장이, 1장에서처럼 회차 단어 뒤에 조사/어미가 바로 붙으면 본문일 확률이 큽니다.
    if re.search(r"\d{1,4}\s*화(?:부터|까지|의|은|는|이|가|을|를|로|으로|에서|에도|라면|였|이었다|인|같|쯤)", s):
        return True
    if re.search(r"\d{1,4}\s*장(?:이|은|는|을|를|으로|에서|까지|부터|도|만|쯤)", s):
        return True

    # 너무 문장 같은 제목은 확인 대상으로 표시합니다. 단, 숫자. 제목형 단행본 제목은 길 수 있으니 과하게 막지는 않습니다.
    sentence_like_endings = ("다", "요", "까", "까?", "죠", "죠?", "네요", "했다", "였다", "입니다")
    if len(s) >= 38 and any(s.endswith(x) for x in sentence_like_endings):
        return True
    if len(s) >= 55:
        return True
    return False


def suspicious_chapter_indices(chapters: List[Chapter]) -> List[int]:
    return [chapter.index for chapter in chapters if is_suspicious_chapter_title(chapter.title)]


def _norm_title_like(text: str) -> str:
    text = display_line_text(text)
    text = re.sub(r"[\s_\-·・:：.,，。'\"“”‘’『』「」《》\[\]()]", "", text)
    return text.lower()


def _chapter_content_size(chapter: Chapter) -> tuple[int, int]:
    nonblank = [display_line_text(line) for line in chapter.lines if display_line_text(line)]
    return sum(len(line) for line in nonblank), len(nonblank)


def strip_imported_toc_chapters(chapters: List[Chapter], *, scan_limit: int = 160) -> List[Chapter]:
    """
    단행본 TXT 앞부분에 같이 붙어 온 원본 목차 때문에 같은 회차명이 두 번 잡히는 경우를 줄입니다.

    원리:
    - 앞부분에서 내용이 거의 없는 챕터를 원본 목차 후보로 봅니다.
    - 그 제목이 뒤쪽에 다시 등장하면, 앞쪽의 내용 없는 항목을 목차 항목으로 보고 제거합니다.
    - 실제 본문이 들어 있는 챕터는 제거하지 않습니다.
    """
    if len(chapters) < 4:
        return chapters

    norms = [_norm_title_like(chapter.title) for chapter in chapters]
    later_counts = Counter(norm for norm in norms if norm)
    kept: List[Chapter] = []
    dropped = 0

    for i, chapter in enumerate(chapters):
        norm = norms[i]
        if norm:
            later_counts[norm] -= 1

        chars, line_count = _chapter_content_size(chapter)
        low_content = chars <= 140 and line_count <= 5
        is_near_front = i < scan_limit
        repeated_later = bool(norm and later_counts[norm] > 0)

        # 앞부분에 있고, 본문이 거의 없고, 같은 제목이 뒤에 다시 나오면 원본 목차 항목일 가능성이 높습니다.
        if is_near_front and low_content and repeated_later and norm not in {"시작", "본문"}:
            dropped += 1
            continue

        kept.append(chapter)

    # 원본 목차 제목줄만 "시작" 구간에 남은 경우 같이 제거합니다.
    if dropped and len(kept) > 1 and kept[0].title == "시작":
        chars, line_count = _chapter_content_size(kept[0])
        joined = " ".join(display_line_text(line) for line in kept[0].lines if display_line_text(line))
        looks_like_toc_label = bool(re.search(r"(목차|차례|contents|table\s*of\s*contents)", joined, re.I))
        if (chars <= 120 and line_count <= 5) or looks_like_toc_label:
            kept = kept[1:]

    return reindex_chapters(kept)


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


_PATTERN_DEFS: list[tuple[str, str, str]] = [
    (
        "프롤로그/에필로그",
        r"^(?:프롤로그|프롤로그\.|prologue|prologue\.|에필로그|에필로그\.|epilogue|epilogue\.)(?:\s*[:：.\-–—]?\s*.*)?$",
        "예: Prologue., Prologue #1. 김현승, 프롤로그, Epilogue. 한 달 후",
    ),
    (
        "단행본: 숫자. 제목",
        r"^(?![12]\d{3}\.\s*\d{1,2}\.\s*\d{1,2}\.?$)(?:0?[1-9]|[1-9]\d{1,3})\s*[.)]\s*(?!\d)(?=.{1,90}$)\S.*$",
        "예: 1. 제목, 01. 제목, 2) 제목, 12. 어느 날",
    ),
    (
        "단독 번호: 1. 2. 3.",
        r"^(?!(?:19|20)\d{2}\s*[.)]\s*$)\d{1,4}\s*[.)]\s*$",
        "예: 1., 2., 3. 처럼 제목 없이 번호만 있는 회차",
    ),
    (
        "단독 번호: 01. 02.",
        r"^\d{2}\s*[.)]\s*$",
        "예: 01., 02., 03. 처럼 두 자리 번호만 있는 회차",
    ),
    (
        "단독 번호: 001. 002.",
        r"^\d{3}\s*[.)]\s*$",
        "예: 001., 002., 003. 처럼 세 자리 번호만 있는 회차",
    ),
    (
        "단행본: 세자리 001. 제목",
        r"^\d{3}\s*[.)]\s*(?!\d)(?=.{1,90}$)\S.*$",
        "예: 001. 시작, 002. Prologue., 014. 5. 레티샤",
    ),
    (
        "꺾쇠: <1화>",
        r"^[<＜〈《【]\s*(?:제\s*)?\d{1,4}\s*화\s*[>＞〉》】](?:\s*$|\s+\S.*$|\s*[:：.\-–—]\s*\S.*$)",
        "예: <1화>, <2화>, 〈3화〉, 《4화》",
    ),
    (
        "연재: 숫자화",
        r"^\s*(?:제\s*)?\d{1,4}\s*화\.?(?:\s*$|\s+\S.*$|\s*[:：\-–—]\s*\S.*$)",
        "예: 1화, 1화., 12화, 100화, 1화. 시작",
    ),
    (
        "장 제목: 숫자장",
        r"^(?:제\s*)?\d{1,4}\s*장(?:\s*$|\s+\S.*$|\s*[:：.\-–—.]\s*\S.*$)",
        "예: 1장, 제 2장. 제목, 3장. 별과 인연",
    ),
    (
        "해시: #번호",
        r"^#\s*\d{1,4}\s*(?:화|장)?(?:\s*$|\s+\S.*$|\s*[:：.\-–—.]\s*\S.*$)",
        "예: #1, #01. 제목, #1화, #12 제목",
    ),
    (
        "권/부: 숫자권·숫자부",
        r"^(?:제\s*)?\d{1,4}\s*(?:권|부)(?:\s*$|\s+\S.*$|\s*[:：.\-–—.]\s*\S.*$)",
        "예: 1권, 2부. 제목, 제3부 새로운 시작",
    ),
    (
        "외전/번외/특별편",
        r"^(?:외전|번외|특별편|후일담|番外|外傳)(?:\s*[:：.\-–—]?\s*.*)?$",
        "예: 외전, 번외 1, 특별편, 후일담",
    ),
    (
        "Episode/EP",
        r"^(?:episode|ep)\s*\d{1,4}(?:\s*$|\s+\S.*$|\s*[:：.\-–—]\s*\S.*$)",
        "예: Episode 1, EP 02, episode 3. title",
    ),
    (
        "PART/CHAPTER 영문",
        r"^(?:part|chapter|ch)\s*\d{1,4}(?:\s*$|\s+\S.*$|\s*[:：.\-–—.]\s*\S.*$)",
        "예: Chapter 1, CH 02, Part 3. Title",
    ),
]

def _unique_examples(lines: Iterable[str], limit: int = 7) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for line in lines:
        s = display_line_text(line)
        if not s or s in seen:
            continue
        seen.add(s)
        result.append(s)
        if len(result) >= limit:
            break
    return result


def suggest_chapter_patterns(text: str, *, min_count: int = 1) -> List[PatternCandidate]:
    """TXT를 훑어서 사용자가 고를 수 있는 회차 패턴 후보를 반환합니다."""
    text = normalize_text(text)
    if not text:
        return []

    display_lines = [display_line_text(line) for line in text.split("\n")]
    candidates: List[PatternCandidate] = []
    for name, regex, desc in _PATTERN_DEFS:
        pattern = re.compile(regex, re.IGNORECASE)
        matches = [line for line in display_lines if line and len(line) <= 100 and pattern.match(line)]
        examples = _unique_examples(matches)
        if len(matches) >= min_count and examples:
            candidates.append(PatternCandidate(name=name, regex=regex, count=len(matches), examples=examples, description=desc))

    # 많이 잡힌 후보를 먼저 보여주되, 프롤로그처럼 1~2개짜리 후보도 사라지지 않게 둡니다.
    candidates.sort(key=lambda c: (-c.count, c.name))
    return candidates


def get_pattern_preset_candidates(text: str) -> List[PatternCandidate]:
    """모든 기본 프리셋을 매칭 수와 예시와 함께 반환합니다.

    자동 후보에 뜨지 않는 형식도 사용자가 직접 고를 수 있게 하기 위한 목록입니다.
    """
    text = normalize_text(text)
    display_lines = [display_line_text(line) for line in text.split("\n")] if text else []
    candidates: List[PatternCandidate] = []
    for name, regex, desc in _PATTERN_DEFS:
        pattern = re.compile(regex, re.IGNORECASE)
        matches = [line for line in display_lines if line and len(line) <= 120 and pattern.match(line)]
        examples = _unique_examples(matches)
        candidates.append(PatternCandidate(name=name, regex=regex, count=len(matches), examples=examples, description=desc))
    candidates.sort(key=lambda c: (c.count == 0, -c.count, c.name))
    return candidates


def sample_title_like_lines(text: str, *, limit: int = 80) -> List[str]:
    """정규식을 모르는 사용자가 샘플 줄을 고를 수 있도록 회차처럼 보이는 줄을 모읍니다."""
    text = normalize_text(text)
    if not text:
        return []
    compiled = [re.compile(regex, re.IGNORECASE) for _, regex, _ in _PATTERN_DEFS]
    result: List[str] = []
    seen: set[str] = set()
    for raw in text.split("\n"):
        line = display_line_text(raw)
        if not line or line in seen or len(line) > 100:
            continue
        if any(pattern.match(line) for pattern in compiled):
            seen.add(line)
            result.append(line)
            if len(result) >= limit:
                break
    return result


def regex_from_example_line(line: str) -> str:
    """사용자가 고른 한 줄을 기준으로 실전용 회차 정규식을 만들어줍니다."""
    s = display_line_text(line)
    if not s:
        return r"^.+$"

    if re.match(r"^\d{3}\s*[.)]\s*$", s):
        return r"^\d{3}\s*[.)]\s*$"
    if re.match(r"^\d{2}\s*[.)]\s*$", s):
        return r"^\d{2}\s*[.)]\s*$"
    if re.match(r"^(?!(?:19|20)\d{2}\s*[.)]\s*$)\d{1,4}\s*[.)]\s*$", s):
        return r"^(?!(?:19|20)\d{2}\s*[.)]\s*$)\d{1,4}\s*[.)]\s*$"
    if re.match(r"^[<＜〈《【]\s*(?:제\s*)?\d{1,4}\s*화\s*[>＞〉》】](?:\s*$|\s+\S.*$|\s*[:：.\-–—]\s*\S.*$)", s):
        return r"^[<＜〈《【]\s*(?:제\s*)?\d{1,4}\s*화\s*[>＞〉》】](?:\s*$|\s+\S.*$|\s*[:：.\-–—]\s*\S.*$)"
    if re.match(r"^\s*(?:제\s*)?\d{1,4}\s*화\.?\s*$", s):
        return r"^\s*(?:제\s*)?\d{1,4}\s*화\.?\s*$"
    if re.match(r"^\s*(?:제\s*)?\d{1,4}\s*화\.?(?:\s+\S.*$|\s*[:：\-–—]\s*\S.*$)", s):
        return r"^\s*(?:제\s*)?\d{1,4}\s*화\.?(?:\s*$|\s+\S.*$|\s*[:：\-–—]\s*\S.*$)"
    if re.match(r"^(?:제\s*)?\d{1,4}\s*장", s):
        return r"^(?:제\s*)?\d{1,4}\s*장(?:\s*$|\s+\S.*$|\s*[:：.\-–—.]\s*\S.*$)"
    if re.match(r"^#\s*\d{1,4}", s):
        return r"^#\s*\d{1,4}\s*(?:화|장)?(?:\s*$|\s+\S.*$|\s*[:：.\-–—.]\s*\S.*$)"
    if re.match(r"^(?:프롤로그|프롤로그\.|prologue)", s, re.I):
        return r"^(?:프롤로그|프롤로그\.|prologue)(?:\s*[:：.\-–—]?\s*.*)?$"
    if re.match(r"^(?:에필로그|에필로그\.|epilogue)", s, re.I):
        return r"^(?:에필로그|에필로그\.|epilogue)(?:\s*[:：.\-–—]?\s*.*)?$"
    if re.match(r"^(?:외전|번외|특별편|후일담)", s, re.I):
        return r"^(?:외전|번외|특별편|후일담)(?:\s*[:：.\-–—]?\s*.*)?$"
    if re.match(r"^(?:episode|ep)\s*\d{1,4}", s, re.I):
        return r"^(?:episode|ep)\s*\d{1,4}(?:\s*$|\s+\S.*$|\s*[:：.\-–—]\s*\S.*$)"
    if re.match(r"^(?![12]\d{3}\.\s*\d{1,2}\.\s*\d{1,2}\.?$)(?:0?[1-9]|[1-9]\d{1,3})\s*[.)]\s*(?!\d)\S.*$", s):
        return r"^(?![12]\d{3}\.\s*\d{1,2}\.\s*\d{1,2}\.?$)(?:0?[1-9]|[1-9]\d{1,3})\s*[.)]\s*(?!\d)(?=.{1,80}$)\S.*$"

    # 그 외에는 첫 단어/키워드로 시작하는 줄을 잡는 규칙을 만듭니다.
    keyword = re.split(r"\s+|[:：.\-–—]", s, maxsplit=1)[0]
    keyword = keyword.strip()
    if keyword:
        return r"^" + re.escape(keyword) + r"(?:\s*[:：.\-–—]?\s*.*)?$"
    return r"^" + re.escape(s) + r"$"



def split_example_inputs(example_text: str) -> list[str]:
    """사용자가 붙여넣은 예시를 줄/슬래시/쉼표 단위로 나눕니다.

    예시 입력은 실제 본문이 아니라 '목차가 되는 모양'을 알려주는 칸이라서
    <1화>/<2화>/<3화>처럼 한 줄에 붙여 써도 각각의 예시로 해석합니다.
    """
    result: list[str] = []
    seen: set[str] = set()
    for raw_line in example_text.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        pieces = re.split(r"\s*(?:/|／|,|，|\||｜)\s*", raw_line)
        for piece in pieces:
            item = display_line_text(piece).strip()
            if not item:
                continue
            # 사용자가 '예: <1화>'처럼 붙여넣은 경우를 정리합니다.
            item = re.sub(r"^(?:예시?|sample)\s*[:：]\s*", "", item, flags=re.I).strip()
            # 앞에 붙은 목록 번호는 제거하되, '01.' 자체가 예시인 경우는 건드리지 않습니다.
            if not re.match(r"^\d{1,4}\s*[.)]\s*$", item):
                item = re.sub(r"^\s*\d{1,3}\s*[.)]\s+(?=\S)", "", item).strip()
            if item and item not in seen:
                seen.add(item)
                result.append(item)
    return result


def regex_from_example_lines(example_text: str) -> str:
    """여러 개의 예시 줄을 보고 가장 알맞은 회차 정규식을 만듭니다.

    예:
    - 1. / 2. / 3.  -> 번호만 있는 단독 회차
    - 01. / 02.     -> 두 자리 단독 번호
    - 1. 제목 / 2. 제목 -> 단행본 숫자 제목형
    - Prologue #1. 이름 + Epilogue. ... -> 프롤로그/에필로그형
    """
    examples = split_example_inputs(example_text)
    if not examples:
        return ""

    # 같은 종류가 여러 줄이면 그 종류를 우선합니다.
    if all(re.match(r"^\d{3}\s*[.)]\s*$", x) for x in examples):
        return r"^\d{3}\s*[.)]\s*$"
    if all(re.match(r"^\d{2}\s*[.)]\s*$", x) for x in examples):
        return r"^\d{2}\s*[.)]\s*$"
    if all(re.match(r"^(?!(?:19|20)\d{2}\s*[.)]\s*$)\d{1,4}\s*[.)]\s*$", x) for x in examples):
        return r"^(?!(?:19|20)\d{2}\s*[.)]\s*$)\d{1,4}\s*[.)]\s*$"
    if all(re.match(r"^(?![12]\d{3}\.\s*\d{1,2}\.\s*\d{1,2}\.?$)(?:0?[1-9]|[1-9]\d{1,3})\s*[.)]\s*(?!\d)(?=.{1,90}$)\S.*$", x) for x in examples):
        return r"^(?![12]\d{3}\.\s*\d{1,2}\.\s*\d{1,2}\.?$)(?:0?[1-9]|[1-9]\d{1,3})\s*[.)]\s*(?!\d)(?=.{1,90}$)\S.*$"
    if all(re.match(r"^#\s*\d{1,4}", x) for x in examples):
        return r"^#\s*\d{1,4}\s*(?:화|장)?(?:\s*$|\s+\S.*$|\s*[:：.\-–—.]\s*\S.*$)"
    if all(re.match(r"^[<＜〈《【]\s*(?:제\s*)?\d{1,4}\s*화\s*[>＞〉》】]", x) for x in examples):
        return r"^[<＜〈《【]\s*(?:제\s*)?\d{1,4}\s*화\s*[>＞〉》】](?:\s*$|\s+\S.*$|\s*[:：.\-–—]\s*\S.*$)"
    if all(re.match(r"^\s*(?:제\s*)?\d{1,4}\s*화\.?\s*$", x) for x in examples):
        return r"^\s*(?:제\s*)?\d{1,4}\s*화\.?\s*$"
    if all(re.match(r"^\s*(?:제\s*)?\d{1,4}\s*화\.?(?:\s*$|\s+\S.*$|\s*[:：\-–—]\s*\S.*$)", x) for x in examples):
        return r"^\s*(?:제\s*)?\d{1,4}\s*화\.?(?:\s*$|\s+\S.*$|\s*[:：\-–—]\s*\S.*$)"
    if all(re.match(r"^(?:제\s*)?\d{1,4}\s*장", x) for x in examples):
        return r"^(?:제\s*)?\d{1,4}\s*장(?:\s*$|\s+\S.*$|\s*[:：.\-–—.]\s*\S.*$)"

    # 섞여 있으면 각 예시별 규칙을 합쳐서 씁니다. 중복은 제거합니다.
    regexes: list[str] = []
    for line in examples:
        regex = regex_from_example_line(line)
        if regex and regex not in regexes:
            regexes.append(regex)
    return "\n".join(regexes)

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

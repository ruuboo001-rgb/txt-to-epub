# TXT → EPUB Studio Web v1.9

Streamlit으로 만든 TXT → EPUB 웹 제작기입니다.

## v1.9 변경점

- `1화.`, `2화.`, `3화.`처럼 마침표로 끝나는 화수 단독 제목 감지 수정
- 예시 입력칸에 `1화. / 2화. / 3화.`를 넣으면 제목 없는 화수 전용 정규식을 생성합니다.
- 생성 정규식이 너무 넓게 만들어져 본문/제목을 이상하게 잡던 문제를 완화했습니다.
- 제목 없는 화수형은 기본적으로 아래처럼 생성됩니다.

```regex
^\s*(?:제\s*)?\d{1,4}\s*화\.?\s*$
```

- `1화부터`, `3화의`, `10화쯤` 같은 본문 문장은 잡지 않도록 했습니다.
- `1화. 제목`처럼 제목이 붙은 예시를 넣은 경우에만 제목 포함형 정규식을 생성합니다.

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud 배포

GitHub 저장소에 파일을 올린 뒤 Main file path를 `app.py`로 지정하세요.

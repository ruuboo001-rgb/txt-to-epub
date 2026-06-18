# TXT → EPUB Studio Web v1.7

Streamlit으로 만든 TXT → EPUB 웹 제작기입니다.

## v1.7 변경점

- `1.`, `2.`, `3.`처럼 제목 없이 번호만 있는 단독 회차 감지 추가
- `01.`, `02.`처럼 두 자리 번호만 있는 회차 감지 추가
- `001.`, `002.`처럼 세 자리 번호만 있는 회차 감지 추가
- `Prologue #1. 이름` + `1.` + `2.` + `Epilogue. ...` 조합 대응
- 정규식을 몰라도 예시 줄을 직접 붙여넣어 패턴을 자동 생성하는 기능 추가
- 목차 찾기 프리셋에 단독 번호형 추가
- 기본 회차 규칙을 켰을 때도 직접 입력 규칙과 함께 적용되도록 안내 문구 개선

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud 배포

GitHub 저장소에 파일을 올린 뒤 Main file path를 `app.py`로 지정하세요.

# TXT → EPUB Studio Web v1.3

Streamlit으로 만든 TXT → EPUB 웹 제작기입니다.

## 변경사항 v1.3

- 회차 직접 정규식을 입력해도 기본 규칙 때문에 결과가 안 바뀌던 문제 보완
- `기본 회차 규칙도 같이 사용` 체크박스 추가
  - 끄면 직접 입력한 정규식만 사용합니다.
  - 예: `^\d+\s*화$` 또는 `화$`
- `01. 제목` 기본 감지의 오탐 완화
  - `2003. 05. 22.` 같은 날짜
  - `0.1초 사이...` 같은 본문 문장
- 분석 결과에 직접 입력한 규칙과 기본 규칙 사용 여부 표시

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud 배포

1. 이 폴더의 파일들을 GitHub 저장소에 올립니다.
2. Streamlit Community Cloud에서 Create app을 누릅니다.
3. 저장소와 브랜치를 선택합니다.
4. Main file path를 `app.py`로 지정합니다.
5. Deploy를 누릅니다.

# TXT → EPUB Studio Web

Streamlit으로 만든 TXT → EPUB 웹 제작기입니다.

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud 배포

1. 이 폴더의 파일들을 GitHub 저장소에 올립니다.
2. Streamlit Community Cloud에서 **Create app**을 누릅니다.
3. 저장소와 브랜치를 선택합니다.
4. Main file path를 `app.py`로 지정합니다.
5. Deploy를 누릅니다.

## 주요 기능

- TXT 업로드
- 표지 이미지 업로드 및 미리보기
- 제목/작가/EPUB 제작자 입력
- 표제지 자동 생성
- 기존 제목만 있는 시작 페이지 제거 옵션
- 테마 선택
- 회차 자동 감지 및 직접 정규식 추가
- 전환마크 자동 감지 및 직접 추가
- 목차/본문/표제지 미리보기
- EPUB 다운로드

## 참고

공개 앱으로 배포하면 사용자가 업로드한 파일은 EPUB 생성을 위해 앱 서버에서 처리됩니다. 개인정보나 민감한 파일을 올리지 않도록 안내문을 남기는 것을 권장합니다.

# Pixel Art Production

게임마다 클론해서 쓰는 32×32 픽셀 아트 제작 도구다. ChatGPT Work, Codex 또는 Claude Code에서 이 폴더를 열고 “32×32 마법사 스프라이트를 만들어줘”라고 요청하면 [첫 요청 인터뷰](docs/pipeline.md#첫-요청-인터뷰)부터 시작한다. 자동으로 지침을 읽지 않는 환경에서는 `AGENTS.md`를 먼저 읽으라고 요청한다.

이미지 생성 도구와 Python으로 PNG를 만든다. Unity 자동 분할이 필요할 때는 [Unity 임포터](docs/unity-import.md)를 게임 프로젝트에 추가할 수 있다.

아래는 Python 환경과 게임 작업 폴더를 터미널에서 직접 준비할 때 쓰는 명령이다.

```powershell
py -3 -m venv .venv
$py = './.venv/Scripts/python.exe'
& $py -m pip install -r tools/pixel-art/requirements.txt
& $py tools/pixel-art/pixel_art.py init project/game
```

Python 3.10 이상이 필요하다. macOS/Linux에서는 `python3 -m venv .venv`와 `./.venv/bin/python`을 사용한다.

- [첫 인터뷰부터 PNG 완성까지](docs/pipeline.md)
- [AI 작업 지침](AGENTS.md)
- [클론 운영과 공용 도구 업데이트](docs/git-workflow.md)

| 경로 | 내용 |
| --- | --- |
| `tools/pixel-art/` | 초기화, 색상 견본, 분리·정규화·검수·조립 CLI |
| `unity/Assets/Editor/` | 선택 사항인 Unity 시트 임포터 |
| `project/game/` | 이 클론의 아트 방향, 레퍼런스, 원본, 팔레트와 결과물 |

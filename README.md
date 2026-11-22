# Pixel Art Production

게임별 아트 방향과 팔레트를 적용해 픽셀 아트 PNG를 제작하고 검수하는 Codex 플러그인이다. 에이전트는 사용자가 지정한 위치나 작업 중인 게임의 파일 구조에 맞춰 게임 아트 작업 폴더를 정한다.

## Codex에서 사용하기

1. 이 저장소를 신뢰된 프로젝트로 연다. 로컬 마켓플레이스는 `.agents/plugins/marketplace.json`에 있고 프로젝트 설정에서 `pixel-art-production@pixel-art-local`을 활성화한다.
2. Codex에서 플러그인을 새로 읽은 뒤 **Pixel Art Production**을 선택하고 요청한다. 스킬 이름으로 작업을 지정할 수도 있다.

| 스킬 | 요청 예시 |
| --- | --- |
| `character-sprites` | 승인된 마법사 오른쪽 포즈로 이동 애니메이션을 만들어줘 |
| `environment-art` | 초원 타일맵과 패럴랙스 배경을 만들어줘 |
| `pixel-ui` | 기본 전투 화면에 맞는 양피지 주문 카드를 만들어줘 |
| `spell-effects` | 메테오 충돌을 주문별 투명 PNG 시트와 GIF로 만들어줘 |
| `color-style` | 슬라임의 초록 명암을 보라색 팔레트로 옮겨줘 |

다른 저장소에서 쓰려면 `plugins/pixel-art-production/` 폴더 전체를 로컬 마켓플레이스에 등록한다. 설치 후 게임이나 에셋 작업 공간에서 스킬을 호출한다. 스킬은 설치된 플러그인의 스크립트와 문서를 사용하고, 선택한 게임 아트 작업 폴더에 결과를 기록한다. 이미지 생성에는 세션에서 제공하는 이미지 생성 도구가 필요하다.

## Python CLI

게임 작업 공간에서 실행한다. 아래의 `$plugin`과 `$game`을 실제 경로로 바꾼다. 새 아트 작업 폴더를 만들 때 `init`을 실행한다.

```powershell
py -3 -m venv .venv
$py = './.venv/Scripts/python.exe'
$plugin = 'C:/path/to/installed/pixel-art-production'
$game = 'C:/path/to/game/pixel-art'
& $py -m pip install -r "$plugin/scripts/pixel-art/requirements.txt"
& $py "$plugin/scripts/pixel-art/pixel_art.py" --help
& $py "$plugin/scripts/pixel-art/pixel_art.py" init "$game"
```

Python 3.10 이상이 필요하다. macOS/Linux에서는 `python3 -m venv .venv`와 `./.venv/bin/python`을 사용한다. 기존 `tools/pixel-art/pixel_art.py`와 의존성 경로도 사용할 수 있다. 플러그인을 지원하지 않는 환경에서는 `AGENTS.md`와 아래 제작 절차를 사용한다.

- [첫 인터뷰부터 PNG 검수까지](plugins/pixel-art-production/references/pipeline.md)
- [캐릭터 동작 제작과 재생 검수](plugins/pixel-art-production/references/character-motion.md)
- [PNG 레퍼런스로 색감 정리하기](plugins/pixel-art-production/references/color-style.md)
- [Unity 임포터](docs/unity-import.md)
- [플러그인과 게임 아트 관리](docs/git-workflow.md)
- [Codex 로컬 플러그인 공식 문서](https://developers.openai.com/plugins/build/plugins)

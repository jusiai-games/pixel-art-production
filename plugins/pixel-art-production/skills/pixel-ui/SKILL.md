---
name: pixel-ui
description: 게임용 픽셀 아트 카드, 버튼, 대화창, HUD, 명판, 아이콘과 9슬라이스 UI를 만들거나 수정할 때 사용한다.
---

# pixel-ui

플러그인 루트는 이 `SKILL.md`에서 두 단계 위다. 루트의 `scripts/pixel-art/pixel_art.py`를 절대 경로로 실행한다. 작업 디렉터리는 사용자 게임 저장소로 두고, 게임 데이터는 그 저장소의 `project/game/` 또는 요청에 명시된 게임 폴더에 저장한다. Python 3.10 이상과 `scripts/pixel-art/requirements.txt`의 의존성을 사용한다.

[제작 절차](../../references/pipeline.md)에서 첫 요청 인터뷰와 이미지 생성·검수 절차를 읽는다. 게임의 `art-direction.md`가 없거나 초안이면 이미 받은 답을 바탕으로 인터뷰하고, 합의한 뒤 CLI로 게임 폴더를 초기화하거나 기존 설정을 이어서 채운다. 제작 전에 아트 방향, 팔레트, 작업 명세와 승인 레퍼런스를 확인한다. 작업 명세는 `jobs/`에 작성한다. 세션의 이미지 생성 도구로 새 그림이나 편집 후보를 만들고 `sources/<asset>/<attempt>/`에 원본과 프롬프트를 보관한다. 검수본은 `work/`, 승인 PNG는 `approved/`, 조립한 시트는 `exports/`에 둔다. 도구가 없으면 명세와 프롬프트를 작성하고 가져온 PNG부터 이어간다.

1. [UI 실루엣과 화면 배율 검수](../../references/pipeline.md#ui-실루엣과-화면-배율-검수)에 따라 레퍼런스에서 가져갈 형태, 클릭 가능 여부, 기본 화면 크기와 글자 영역을 명세한다.
2. 확대 후보는 `inspect-grid`로 확인한다. 개별 PNG에는 `validate --size W H --palette <palette.json>`로 치수, 알파와 허용색을 검사한다. 타일 매니페스트가 있는 시트는 프레임을 분리한 뒤 `review`로 검수한다.
3. 9슬라이스는 좁은 폭부터 긴 텍스트 폭까지 가장자리와 모서리를 확인한다. 카드나 HUD는 버튼, 배경 및 실제 문구와 함께 기본 표시 크기에서 확인하고 PNG와 검수 결과를 저장한다.

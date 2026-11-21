---
name: character-sprites
description: 픽셀 아트 캐릭터, 몬스터, NPC, 이동·피격·시전 등 캐릭터 스프라이트와 애니메이션을 만들거나 수정할 때 사용한다.
---

# character-sprites

플러그인 루트는 이 `SKILL.md`에서 두 단계 위다. 루트의 `scripts/pixel-art/pixel_art.py`를 절대 경로로 실행한다. 작업 디렉터리는 사용자 게임 저장소로 두고, 게임 데이터는 그 저장소의 `project/game/` 또는 요청에 명시된 게임 폴더에 저장한다. Python 3.10 이상과 `scripts/pixel-art/requirements.txt`의 의존성을 사용한다.

[제작 절차](../../references/pipeline.md)에서 첫 요청 인터뷰와 이미지 생성·검수 절차를 읽는다. 게임의 `art-direction.md`가 없거나 초안이면 이미 받은 답을 바탕으로 인터뷰하고, 합의한 뒤 CLI로 게임 폴더를 초기화하거나 기존 설정을 이어서 채운다. 제작 전에 아트 방향, 팔레트, 작업 명세와 승인 레퍼런스를 확인한다. 작업 명세는 `jobs/`에 작성한다. 세션의 이미지 생성 도구로 새 그림이나 편집 후보를 만들고 `sources/<asset>/<attempt>/`에 원본과 프롬프트를 보관한다. 검수본은 `work/`, 승인 PNG는 `approved/`, 조립한 시트는 `exports/`에 둔다. 도구가 없으면 명세와 프롬프트를 작성하고 가져온 PNG부터 이어간다.

1. 첫 인터뷰에서 프레임과 발 피벗을 정하고 `lock-character-frame`으로 저장한다. 기존 잠금 값을 명세, 프롬프트와 검수에 사용한다.
2. 같은 방향의 승인 포즈와 팔레트 견본, 허용 HEX를 첨부한다. 색감 프로파일이 있으면 [색감 가이드](../../references/color-style.md)를 적용한다.
3. 후보 형태에 따라 `inspect-grid`, `split` 또는 `normalize`를 실행하고 `review`로 검수한다. 색감 프로파일이 있으면 `--color-profile`을 지정한다.
4. 애니메이션은 실제 경계 프레임을 상태 전환 맵에 기록하고 `review-transitions`를 실행한다. 게임 배율에서 확인한 뒤 승인 PNG를 두고, 필요하면 `assemble`로 시트를 만든다.

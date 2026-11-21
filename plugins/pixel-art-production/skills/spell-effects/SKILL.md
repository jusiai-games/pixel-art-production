---
name: spell-effects
description: 파이어볼, 메테오, 보호막, 충돌과 폭발 등 픽셀 아트 주문 이펙트 및 전투 VFX를 만들거나 수정할 때 사용한다.
---

# spell-effects

플러그인 루트는 이 `SKILL.md`에서 두 단계 위다. 루트의 `scripts/pixel-art/pixel_art.py`를 절대 경로로 실행한다. 작업 디렉터리는 사용자 게임 저장소로 두고, 게임 데이터는 그 저장소의 `project/game/` 또는 요청에 명시된 게임 폴더에 저장한다. Python 3.10 이상과 `scripts/pixel-art/requirements.txt`의 의존성을 사용한다.

[제작 절차](../../references/pipeline.md)에서 첫 요청 인터뷰와 이미지 생성·검수 절차를 읽는다. 게임의 `art-direction.md`가 없거나 초안이면 이미 받은 답을 바탕으로 인터뷰하고, 합의한 뒤 CLI로 게임 폴더를 초기화하거나 기존 설정을 이어서 채운다. 제작 전에 아트 방향, 팔레트, 작업 명세와 승인 레퍼런스를 확인한다. 작업 명세는 `jobs/`에 작성한다. 세션의 이미지 생성 도구로 새 그림이나 편집 후보를 만들고 `sources/<asset>/<attempt>/`에 원본과 프롬프트를 보관한다. 검수본은 `work/`, 승인 PNG는 `approved/`, 조립한 시트는 `exports/`에 둔다. 도구가 없으면 명세와 프롬프트를 작성하고 가져온 PNG부터 이어간다.

1. 준비·발동·잔상 등 실제 필요한 단계와 타이밍, 진행 방향, 중심점과 잔상 범위를 명세한다. 여러 주문을 요청받으면 주문별 후보와 최종 PNG를 구분한다.
2. 프레임마다 같은 셀과 중심을 사용한다. 확대 후보는 `inspect-grid`로 확인하고, 16px·32px 중앙 피벗 시트는 해당 타일 매니페스트로 `split`, `review`, `assemble`을 사용한다. 다른 셀 크기는 개별 PNG에 `validate --size W H --palette <palette.json>`을 실행한 뒤 격자와 중심 위치를 확인한다.
3. 게임 배경에서 실제 배율과 속도로 발동과 페이드 타이밍을 확인한다. 주문별 투명 PNG를 저장하고 GIF가 요청되면 같은 프레임 순서와 타이밍으로 미리보기를 추가한다.

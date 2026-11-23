---
name: character-sprites
description: 픽셀 아트 캐릭터, 몬스터, NPC, 이동·피격·시전 등 캐릭터 스프라이트와 애니메이션을 만들거나 수정할 때 사용한다.
---

# character-sprites

[공통 제작 절차](../../references/pipeline.md)에 따라 게임 설정, 이미지 생성과 검수를 진행한다.

1. 첫 인터뷰에서 프레임과 발 피벗을 정하고 `lock-character-frame`으로 저장한다. 기존 잠금 값을 명세, 프롬프트와 검수에 사용한다.
2. 같은 방향의 승인 포즈와 팔레트 견본, 허용 HEX를 첨부한다. 색감 프로파일이 있으면 [색감 가이드](../../references/color-style.md)를 적용한다.
3. 후보 형태에 따라 `inspect-grid`, `split` 또는 `normalize`를 실행하고 `review`로 검수한다. 색감 프로파일이 있으면 `--color-profile`을 지정한다.
4. 애니메이션은 실제 경계 프레임을 상태 전환 맵에 기록하고 `review-transitions`를 실행한다. 게임 배율에서 확인한 뒤 승인 PNG를 두고, 필요하면 `assemble`로 시트를 만든다.

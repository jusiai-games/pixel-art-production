---
name: color-style
description: 픽셀 아트 레퍼런스 PNG에서 팔레트와 OKLCH 색감 프로파일을 추출하거나 다른 색조에 재질 명암을 옮길 때 사용한다.
---

# color-style

[CLI 실행](../../references/pipeline.md#cli-실행)과 [색감 작업 절차](../../references/color-style.md)를 읽는다. 게임의 아트 방향, 팔레트와 기존 색감 프로파일을 확인한다.

1. 레퍼런스에서 사용할 영역과 재질별 그림자·기본색·하이라이트를 고른다. `color-scan`으로 후보를 추출하고 `color-build`로 프로파일과 생성 가이드를 만든다.
2. 다른 기본색의 후보가 필요하면 `color-ramp`로 재질의 명암 관계를 옮기고 견본을 확인한다.
3. 생성 전에 명암과 채도 기준을 작업 명세에 기록하고, 생성 후 `review --color-profile` 결과를 확인한다. 게임 팔레트에 새 색을 채택할 때는 [아트 방향 변경](../../references/pipeline.md#아트-방향-변경) 절차를 따른다.

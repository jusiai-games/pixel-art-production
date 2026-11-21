# PNG 레퍼런스 색감 선정

## 참고할 색 고르기

1. 마음에 드는 PNG를 `project/game/references/`에 두고 출처와 참고할 부분을 기록한다. 예를 들어 슬라임 몸체의 광택이나 마법사 로브의 명암을 고른다. 캐릭터가 분리돼 있으면 전체 프레임을, 시트나 장면이라면 `--crop X Y W H`로 원하는 영역을 선택한다.
2. `color-scan`이 만든 `selection.png`와 `swatches.png`를 함께 본다. `report.json`에서 불투명 HEX별 빈도와 OKLCH 값을 확인한다. 픽셀 수가 적어도 의도한 하이라이트는 명암색으로 선택한다. 배경이나 효과를 빼려면 영역을 다시 잡거나 몸체와 겹치지 않는 HEX를 `ignoreColors`에 적는다.
3. 서로 다른 캐릭터와 색조에서 대표 포즈 한 장씩을 골라 `color-sources.json`에 등록한다. 같은 재질의 그림자부터 하이라이트까지 밝기 순서로 3색 이상을 `ramps`에 적는다. 가운데 색을 기준색으로 사용하며, 짝수 개면 가운데 두 색 중 밝은 쪽을 사용한다.

```powershell
$tool = '<플러그인 루트>/scripts/pixel-art/pixel_art.py'
$game = 'project/game'
& $py $tool color-scan "$game/references/reference.png" "$game/work/reference-scan" --crop 0 0 32 32
& $py $tool color-build "$game/references/color-sources.json" "$game/styles/reference-colors-v1"
```

```json
{
  "references": [
    {
      "id": "sample_slime",
      "role": "character",
      "png": "reference.png",
      "crop": [0, 0, 32, 32],
      "ignoreColors": [],
      "ramps": {
        "gel": ["#48643C", "#638752", "#86A866", "#BEDD90"]
      }
    }
  ]
}
```

PNG는 sRGB로 내보낸다. PNG 경로는 설정 파일 기준이다. `crop`, `ignoreColors`, `ramps`는 선택 항목이다. `color-build`는 역할별 프로파일, 견본 PNG와 생성 가이드를 만든다. 수정안을 만들 때는 새 출력 디렉터리를 지정한다.

완전 투명 픽셀은 색 분석에서 제외하고 반투명 픽셀은 알파 통계에 집계한다. 에셋별 픽셀 빈도로 명도·채도 분위수를 구한 뒤 각 에셋에 같은 비중을 준다. 명도 대비는 P90−P10으로 비교한다. 등록한 재질에서 명암 단계와 그림자 색조 이동을 계산하며, 채도가 낮은 색의 색조 이동은 생략한다. 역할은 `character`, `environment`, `effect`를 지원한다. 역할별 레퍼런스가 한 장 이하면 `insufficient`, 두 장에서 네 장이면 `limited`로 표시한다.

## 캐릭터 생성에 적용

1. `character-prompt.md`와 게임 아트 방향을 읽고 새 캐릭터의 고유 색조와 재질을 정한다. 기존 캐릭터의 신규 동작에는 해당 캐릭터의 승인 팔레트와 재질별 명암을 적용한다.
2. 새 색조가 필요하면 비슷한 재질의 명암 램프를 선택하고 `color-ramp`에 기본색을 넣는다. 아래 예시는 초록 슬라임 몸체의 명암 관계를 보라색에 옮긴 HEX 후보와 견본을 만든다. 새 색을 채택할 때는 [아트 방향 변경 절차](pipeline.md#아트-방향-변경)에 따라 허용 팔레트에 기록한다.
3. 생성 프롬프트에 확정한 기본색, 재질별 어두운 색부터 밝은 색까지의 HEX, 명도 대비와 채도 목표를 넣는다. 승인 포즈, 작업에 적용할 팔레트 견본, 참고할 재질이 보이는 PNG를 생성 도구에 첨부한다. 게임 아트 방향의 광원과 캐릭터 프레임·발 피벗도 지정한다.

```powershell
$profile = "$game/styles/reference-colors-v1/profile.json"
& $py $tool color-ramp $profile "$game/work/purple-slime-ramp" `
  --reference meadow_slime --material gel --base '#916EAD'
```

## 후보 비교와 보정

```powershell
& $py $tool color-check "$game/work/slime/slime_00.png" --profile $profile `
  --role character --out "$game/work/slime-color-check"
& $py $tool color-suggest "$game/work/slime/slime_00.png" "$game/work/slime/slime_01.png" `
  --profile $profile --role character --out "$game/work/slime-color-suggestion"
```

- 리포트의 `direction`으로 기준보다 높거나 낮은 값을 확인한다. 그림자 색조를 비교하려면 `--ramps`에 위의 `ramps`와 같은 형태의 JSON을 넘긴다. 효과 전용 HEX는 `--ignore-color '#HEX'`로 제외한다.
- 종합 점수는 관찰 범위에 들어오는 정도를 보여주는 휴리스틱이다. 측정한 항목의 가중치 합을 `evaluatedWeight`에 기록한다. 적은 색을 의도적으로 사용한 에셋은 작업 목적에 맞춰 팔레트 크기 편차를 해석한다. 픽셀 클러스터, 외곽선, 형태, 게임 장면 가독성은 따로 확인한다.
- 보정은 명도·채도 차이를 줄이는 매핑을 찾고, sRGB 범위에 맞추면서 유채색의 색조 변화, 명도 역전과 색상 합침을 검사한다. 여러 프레임을 함께 넘기면 같은 매핑을 쓴다. `preview.png`에는 첫 프레임의 원본·후보가 나란히 표시된다. 개선 후보가 없으면 `no_improvement`를 기록한다.
- 보정 후보를 원본 크기와 게임 배경 위에서 확인한 뒤, 채택한 PNG를 기존 격자·알파·피벗·허용색 검수에 넣는다. `review --color-profile`은 허용색 검사를 통과한 캐릭터 프레임의 편차를 기록한다.

색 공간 변환은 [Björn Ottosson의 Oklab 계산식](https://bottosson.github.io/posts/oklab/)을 사용한다.

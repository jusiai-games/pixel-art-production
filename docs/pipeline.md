# 픽셀 아트 제작 절차

## 첫 요청 인터뷰

AI는 아트 방향 파일이 없거나 상태가 `초안`인 게임의 첫 이미지 요청에서 인터뷰를 시작한다. 요청과 기존 초안에 이미 적힌 답은 사용하고, 필요한 질문을 2~3개씩 묻는다.

1. 프로젝트 이름, 게임 콘셉트와 장르, 핵심 플레이를 묻는다. 첫 이미지가 캐릭터·타일·효과 중 무엇인지와 게임에서 어떻게 쓰이는지 확인한다.
2. 카메라 각도와 필요한 방향, 원하는 분위기와 피할 표현, 실루엣이나 캐릭터의 특징을 묻는다. 레퍼런스가 있으면 이미지나 경로를 받고 어떤 요소를 참고할지 확인한다. 레퍼런스가 없으면 지금까지 들은 내용을 바탕으로 톤과 색 후보를 제시한다.
3. 들은 내용을 짧게 요약하고, 대표 장면에서 쓸 배경·캐릭터·위험·효과의 대비와 재질별 HEX 팔레트를 제안한다. 사용자가 방향을 정하면 설정을 저장하고 원래 요청한 첫 에셋을 이어서 제작한다. 대표 장면이나 전 방향 포즈가 아직 없으면 첫 이미지부터 기준 후보를 만든다.

### 인터뷰 결과 저장

1. `project/game/`이 없으면 AI가 [README](../README.md)의 Python 환경과 `init project/game`을 준비한다. 기존 폴더가 있으면 내용을 이어서 채운다. 프로젝트 이름은 `art-direction.md`에 기록한다.
2. `art-direction.md`에 콘셉트, 카메라, 톤, 조명, 대비, 역할별 색을 기록하고 합의된 상태를 `확정`으로 표시한다. 인터뷰 중 확정되지 않은 항목은 기록해 두고 제작에 필요할 때 확인한다.
3. 합의한 HEX로 `palettes/project.json`의 예시 색을 교체한다. 재질별 색 램프와 검사 가능한 조명·외곽선 기준은 `styles/default.json`에 기록한다. 역할별 색 제한이 필요하면 팔레트 파일을 추가하고 해당 매니페스트에 연결한다.
4. 첨부된 레퍼런스를 `references/`에 저장하고 출처와 참고할 요소를 기록한다. 팔레트 견본을 만든다. 첫 제작에서 승인한 포즈와 대표 장면은 이후 작업의 기준 레퍼런스로 추가한다.

```powershell
$tool = 'tools/pixel-art/pixel_art.py'
$game = 'project/game'
& $py $tool swatch "$game/palettes/project.json" "$game/references/palette-v1.png"
```

## AI 이미지 생성과 편집

1. `jobs/_template.md`를 복사해 작업별로 채운다. 예를 들어 대기부터 만든 뒤 걷기나 공격으로 확장한다. 각 동작의 방향, 프레임 순서와 지속 시간(ms), 반복 여부, 접지 또는 발동 시점을 기록한다.
2. 새 포즈에는 승인한 같은 방향의 기준 이미지, 팔레트 견본과 실제 HEX를 첨부한다. 다음 문장을 작업 명세에 맞춰 바꿔 쓴다.

   > 첨부 기준 포즈에서 [동작과 방향] 한 프레임을 만든다. [카메라 각도]와 [실루엣·비율·비대칭 요소]를 유지하고 [바꿀 요소]만 바꾼다. 조명은 [방향], 재질별 허용 색은 [HEX]다. 32×32 논리 격자, 투명 배경, 불투명한 픽셀 경계. 기준 발 위치는 좌상단에서 (16, 28)이다.

3. 생성 원본과 프롬프트를 `sources/<asset>/<attempt>/`에 보관한다. AI 후보에서 픽셀 블록이나 배경이 불규칙하면 픽셀 편집기로 32×32 격자와 투명도를 맞춘 뒤 내보낸다. 규칙 격자가 확인된 시트는 `split`으로 분리할 수 있다. 확대본은 블록이 정확히 일정할 때 `normalize --scale N`으로 축소한다.
4. 후보를 원본 크기, 최근접 4배 확대와 게임 장면에서 비교한다. 연속 프레임에서 발 기준점, 보폭, 표정, 손과 광원이 튀는지 확인하고 승인본을 `approved/<asset>/`에 둔다.

## 검수와 시트 조립

예시는 `sources/hero_idle/01/hero_idle_down_00.png`에 32×32 후보가 있는 상태에서 실행한다. 각 출력 경로는 처음 쓰는 경로를 지정한다. 단일 PNG 후보는 `normalize`, 규칙 격자 시트는 `split`을 호출한다. AI는 팔레트와 스타일 설정을 읽고 `review`를 실행한 뒤 결과와 경고를 확인한다.

```powershell
$manifest = "$game/manifests/hero_idle.json"
$run = "$game/work/hero_idle-01"
$frame = 'hero_idle_down_00.png'
& $py $tool normalize "$game/sources/hero_idle/01/$frame" "$run/frames/$frame" --kind character
& $py $tool review $manifest "$game/styles/default.json" "$run/frames" "$run/review"
```

- `review`는 `preview-01.png`, `report.json`, 보정 후보 `frames/`를 만든다. 기본 스타일은 팔레트와 프레임 규격을 검사한다. 재질별 보정이 필요하면 스타일 JSON에 `ramps`(어두운 색부터 밝은 색), `source_materials`(팔레트 밖 HEX → 재질 이름)를 명시한다. 대상 색은 매니페스트 팔레트 안에 있어야 한다. 재질이 불명확한 색은 이미지 편집기에서 확인한다.
- 선택적으로 `outline`의 `colors`, `replace`, `minimum_coverage`와 `light`의 `direction`(예: `upper_left`), `tolerance`, `ignore_colors`를 설정한다. 윤곽선과 광원 경고는 눈으로 확인한다.
- 시트 입력은 `split <manifest> <png> <out>`을 쓴다. `--scale`, `--margin`, `--gap`은 원본 격자에 맞춘다. 팔레트 보정을 검수 단계에서 할 때는 `--defer-palette`를 쓴다. 필요하면 분리 후 각 프레임을 정규화한다. 캐릭터 발 위치를 직접 읽었다면 `normalize --anchor X Y`로 맞춘다.

팔레트 검사에 실패하면 해당 색이 어느 재질에 쓰였는지 확인한다. 기존 색으로 맞출 수 있으면 재질 매핑이나 원본 후보를 수정한 뒤 검수를 다시 실행한다. 새 색이 디자인에 필요하면 사용자와 색을 정하고 [아트 방향 변경](#아트-방향-변경) 절차를 적용한다. 같은 후보 PNG와 검수 설정으로 검수·보정·조립을 반복할 수 있다.

단일 스프라이트는 승인한 프레임 PNG가 최종 산출물이다. 시트가 필요하면 미리보기를 승인한 뒤 다음처럼 조립한다. 조립 결과에서 PNG를 바로 사용할 수 있다.

```powershell
Copy-Item "$run/review/frames" "$game/approved/hero_idle"
& $py $tool assemble $manifest "$game/approved/hero_idle" "$game/exports/hero_idle-v1"
```

| 매니페스트 | 셀 / 피벗 | 배치 |
| --- | --- | --- |
| `character` | 32×32 / (16, 28) | `frames_per_direction`, `directions`는 down/left/right/up 순의 부분집합. 파일명은 `<name>_<direction>_<index:02>.png` |
| `tile32` | 32×32 / (16, 16) | `tiles` ID 배열과 `columns`. 파일명은 `<name>_<id>.png`. 중앙 피벗 소품·효과도 같은 규격 사용 가능 |
| `tile` | 16×16 / (8, 8) | 기존 소형 타일과 효과용. `tile32`와 같은 배열 |

피벗 표기는 좌상단 원점 픽셀 경계 좌표다. 모든 프로필은 32 PPU다. 캐릭터의 `columns`는 방향당 프레임 수의 약수로 지정하며 기본값은 방향당 프레임 수다. 팔레트 경로는 매니페스트 기준이다. CLI 옵션은 `--help`와 각 명령의 `--help`에서 볼 수 있다.

## 아트 방향 변경

- **개별 에셋 수정**은 해당 작업 명세와 마지막 승인 PNG를 기준으로 시작한다. 게임 전체 설정을 유지하고 새 후보를 별도 시도로 저장한다. 사용자가 수정 결과를 채택하면 작업 명세와 최종 PNG 경로를 갱신한다.
- **게임 전체 변경**은 바꿀 톤·색·광원과 영향받는 역할을 먼저 기록한다. 변경된 팔레트와 스타일은 새 버전으로 저장하고 견본 PNG를 다시 만든다. `art-direction.md`에는 현재 적용하는 버전과 변경 이유를 기록한다.
- 영향을 받는 매니페스트와 작업 명세를 새 버전으로 연결한다. 기존 승인 프레임을 새 기준으로 검수하고, 재보정이나 재생성이 필요한 결과만 갱신한다. 새 결과가 승인되면 기준 레퍼런스와 최종 PNG 경로를 바꾼다.

완성된 PNG는 이미지 뷰어나 픽셀 편집기에서 바로 열 수 있다. Unity에서 자동 분할이 필요한 경우 [Unity 임포터 사용법](unity-import.md)을 참고한다.

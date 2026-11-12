# Unity에서 스프라이트 시트 가져오기

이 절차는 PNG를 완성한 뒤 Unity에서 자동으로 스프라이트를 분할하고 싶을 때 사용한다. 이미지 생성, 검수, PNG 조립은 Python으로 실행된다.

1. Unity 6 게임 프로젝트에 2D Sprite 패키지를 설치한다. 이 저장소의 `unity/Assets/Editor/PixelArtImporter.cs`와 옆의 `.meta`를 게임 프로젝트의 `Assets/Editor/`에 복사한다. 이 C# 스크립트는 Unity 에디터가 텍스처를 가져올 때 실행한다. [Unity Sprite Editor Data Provider API](https://docs.unity.cn/6000.2/Documentation/Manual/sprite/sprite-editor/sprite-editor-data-provider-api.html)
2. 에디터를 닫거나 자동 새로고침을 잠시 끈 상태에서, 같은 조립 결과의 PNG와 `.sprite.json`을 게임 프로젝트의 `Assets/Art/PixelArt/`에 함께 복사한다. PNG 갱신 시 이름과 기존 PNG의 `.meta`를 보존한다.
3. Unity에서 Sprite Editor의 분할 순서와 피벗, 32 PPU, Point 필터, 압축 없음, Mip Maps Off를 확인한다. 32px 타일의 Grid Cell Size는 1×1, 16px 타일은 0.5×0.5다. 필요하면 작업 명세의 순서와 지속 시간으로 Animation Clip을 구성한다.

PNG를 Unity에 일반 이미지로 가져오거나 직접 슬라이스할 때는 PNG만 복사하면 된다. `.sprite.json`은 위 임포터가 읽는 자동 분할 정보다.

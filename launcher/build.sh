#!/bin/bash
# NaverMap.app 런처 빌드 (macOS 전용)
#   - launcher/NaverMap.applescript 를 저장소 경로 주입 후 컴파일
#   - 아이콘 생성 → icns → 번들 적용 + 커스텀 아이콘 주입
# 사용: bash launcher/build.sh   (결과: 저장소 루트의 NaverMap.app)
set -e

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$REPO/NaverMap.app"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "▶ applescript 컴파일"
sed "s#__APP_DIR__#$REPO#g" "$REPO/launcher/NaverMap.applescript" > "$TMP/app.applescript"
rm -rf "$APP"
osacompile -o "$APP" "$TMP/app.applescript"

echo "▶ 아이콘 생성 + icns 변환"
python3 "$REPO/launcher/make_icon.py" "$TMP/icon.png" >/dev/null
ICONSET="$TMP/icon.iconset"; mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z "$s" "$s"         "$TMP/icon.png" --out "$ICONSET/icon_${s}x${s}.png"     >/dev/null
  sips -z $((s*2)) $((s*2)) "$TMP/icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png"  >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/applet.icns"

echo "▶ 커스텀 아이콘 주입 (Finder/Dock 캐시 무시)"
swift "$REPO/launcher/seticon.swift" "$TMP/icon.png" "$APP" || true

echo ""
echo "✓ 빌드 완료: $APP"
echo "  Finder에서 NaverMap 더블클릭 → 서버 토글 (켜짐 ↔ 꺼짐)"
echo "  Dock 고정: NaverMap.app 을 Dock(구분선 왼쪽)으로 드래그"

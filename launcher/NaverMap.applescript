-- NaverMap 런처 (토글) — 더블클릭하면 서버 켜짐 ↔ 꺼짐
-- __APP_DIR__ 은 launcher/build.sh 가 빌드 시 실제 저장소 경로로 치환한다.
on run
	set isUp to false
	try
		do shell script "lsof -ti:8000 -sTCP:LISTEN >/dev/null 2>&1"
		set isUp to true
	end try
	if isUp then
		-- 끄기: 서버 tty 확보 → kill → 그 Terminal 창 닫기
		set theTTY to ""
		try
			set theTTY to "/dev/" & (do shell script "ps -o tty= -p $(lsof -ti:8000 -sTCP:LISTEN | head -1) | tr -d ' '")
		end try
		do shell script "kill $(lsof -ti:8000 -sTCP:LISTEN) 2>/dev/null || true"
		if theTTY is not "/dev/" then
			tell application "Terminal"
				set target to missing value
				repeat with w in windows
					try
						repeat with tb in tabs of w
							if (tty of tb) is theTTY then
								set target to w
								exit repeat
							end if
						end repeat
					end try
					if target is not missing value then exit repeat
				end repeat
				if target is not missing value then close target saving no
			end tell
		end if
		display notification "서버 꺼짐" with title "navermap-converter"
	else
		-- 켜기: Terminal 창에서 서버 실행(로그 보임) + 브라우저
		tell application "Terminal"
			activate
			do script "cd __APP_DIR__ && /usr/bin/python3 main.py"
		end tell
		delay 1
		do shell script "open http://localhost:8000"
		display notification "켜짐 · localhost:8000 (Terminal 창 = 서버 살아있음)" with title "navermap-converter"
	end if
end run

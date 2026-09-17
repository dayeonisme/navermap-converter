-- NaverMap 런처 (토글) — 더블클릭하면 서버 켜짐 ↔ 꺼짐
-- __APP_DIR__ 은 launcher/build.sh 가 빌드 시 실제 저장소 경로로 치환한다.
on run
	set isUp to false
	try
		do shell script "lsof -ti:8000 -sTCP:LISTEN >/dev/null 2>&1"
		set isUp to true
	end try
	if isUp then
		-- 끄기: 서버 tty 확보 → kill → 해당 iTerm2/Terminal 세션 닫기
		set theTTY to ""
		try
			set theTTY to "/dev/" & (do shell script "ps -o tty= -p $(lsof -ti:8000 -sTCP:LISTEN | head -1) | tr -d ' '")
		end try
		do shell script "kill $(lsof -ti:8000 -sTCP:LISTEN) 2>/dev/null || true"
		if theTTY is not "/dev/" then
			set itermSessionClosed to false
			try
				tell application id "com.googlecode.iterm2"
					set targetSession to missing value
					repeat with w in windows
						try
							repeat with s in sessions of w
								if (tty of s) is theTTY then
									set targetSession to s
									exit repeat
								end if
							end repeat
						end try
						if targetSession is not missing value then exit repeat
					end repeat
					if targetSession is not missing value then
						close targetSession
						set itermSessionClosed to true
					end if
				end tell
			end try
			if not itermSessionClosed then
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
		end if
		display notification "서버 꺼짐" with title "navermap-converter"
	else
		-- 켜기: iTerm2를 우선 사용하고, 없거나 실패하면 Terminal로 대체
		set launchedIn to "Terminal"
		try
			tell application id "com.googlecode.iterm2"
				activate
				set newWindow to (create window with default profile)
				tell current session of newWindow
					write text "cd __APP_DIR__ && uv run main.py"
				end tell
			end tell
			set launchedIn to "iTerm2"
		on error
			tell application "Terminal"
				activate
				do script "cd __APP_DIR__ && uv run main.py"
			end tell
		end try
		delay 1
		do shell script "open http://localhost:8000"
		display notification "켜짐 · localhost:8000 (" & launchedIn & " 창 = 서버 살아있음)" with title "navermap-converter"
	end if
end run

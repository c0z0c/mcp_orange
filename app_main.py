"""mcp_orange.exe / `python app_main.py` 진입 스크립트 (PyInstaller 가 이 파일을 시작점으로 쓴다)."""
import sys

from mcp_orange_app.main import main

if __name__ == "__main__":
    sys.exit(main())

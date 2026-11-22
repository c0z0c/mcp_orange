"""Orange MCP 서버 등록/해지 진입점.  python manage.py --help"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcp_manage.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

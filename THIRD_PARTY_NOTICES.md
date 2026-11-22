# 제3자 구성요소 (배포 exe 에 포함)

`mcp_orange.exe` 는 아래 오픈소스 구성요소를 포함합니다. 저작권과 라이선스는 각 저작권자에게 있으며,
정확한 전문은 각 프로젝트의 배포본/저장소를 보세요. 이 목록은 `build/gen_third_party.py` 가 빌드 환경의
패키지 메타데이터로 생성했습니다.

| 패키지 | 버전 | 라이선스(메타데이터 기준) | 홈 |
|---|---|---|---|
| annotated-types | 0.8.0 | MIT | https://github.com/annotated-types/annotated-types |
| anyio | 4.16.0 | MIT | https://anyio.readthedocs.io/en/latest/ |
| attrs | 26.1.0 | MIT | https://www.attrs.org/ |
| certifi | 2026.11.20 | Mozilla Public License 2.0 (MPL 2.0) | https://github.com/certifi/python-certifi |
| click | 8.5.1 | BSD-3-Clause | https://click.palletsprojects.com/page/changes/ |
| h11 | 0.16.0 | MIT License | https://github.com/python-hyper/h11 |
| httpcore | 1.0.9 | BSD-3-Clause | https://www.encode.io/httpcore |
| httpx | 0.28.1 | BSD License | https://github.com/encode/httpx/blob/master/CHANGELOG.md |
| httpx-sse | 0.4.3 | MIT | https://github.com/florimondmanca/httpx-sse |
| idna | 3.20 | BSD-3-Clause | https://github.com/kjd/idna/blob/master/HISTORY.md |
| jsonschema | 4.26.0 | MIT | https://github.com/python-jsonschema/jsonschema |
| jsonschema-specifications | 2025.9.1 | MIT | https://jsonschema-specifications.readthedocs.io/ |
| mcp | 1.30.0 | MIT License | https://modelcontextprotocol.io |
| pydantic | 2.14.4 | MIT | https://github.com/pydantic/pydantic |
| pydantic_core | 2.50.5 | MIT | https://github.com/pydantic/pydantic |
| pydantic-settings | 2.16.3 | MIT | https://github.com/pydantic/pydantic-settings |
| PyJWT | 2.15.1 | MIT | https://github.com/jpadilla/pyjwt |
| python-dotenv | 1.2.4 | BSD-3-Clause | https://github.com/theskumar/python-dotenv |
| python-multipart | 0.0.34 | Apache-2.0 | https://github.com/Kludex/python-multipart |
| pywin32 | 312 | Python Software Foundation License | https://github.com/mhammond/pywin32 |
| referencing | 0.37.0 | MIT | https://referencing.readthedocs.io/ |
| rpds-py | 2026.9.1 | MIT | https://rpds.readthedocs.io/ |
| sse-starlette | 3.7.0 | BSD-3-Clause | https://github.com/sysid/sse-starlette |
| starlette | 1.10.0 | BSD-3-Clause | https://github.com/Kludex/starlette |
| typing_extensions | 4.16.0 | PSF-2.0 | https://github.com/python/typing_extensions/issues |
| typing-inspection | 0.4.5 | MIT | https://github.com/pydantic/typing-inspection |
| uvicorn | 0.54.0 | BSD-3-Clause | https://uvicorn.dev/release-notes |

이 밖에 exe 에는 다음이 들어 있습니다.

* **Python** (PSF License) 인터프리터와 표준 라이브러리, **Tcl/Tk**(tkinter, BSD 계열), **OpenSSL**(Apache-2.0)
* **PyInstaller 부트로더** (GPL-2.0 + 부트로더 예외 — 이 예외로 결과물의 라이선스는 제한되지 않음)

mcp_orange 자체는 GPL-3.0-or-later 입니다 ([LICENSE](LICENSE), [NOTICE.md](NOTICE.md)).

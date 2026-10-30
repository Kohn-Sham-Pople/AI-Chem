# Step 1–2 HPC 이전 안내

이 Archive는 기존 T01–T12 구현을 보존한 **source handoff**입니다.
이번 작업에서 기존 source/tests/tools/schemas/fixtures/requirements/문서는
수정하지 않았습니다. 추가한 파일은 이 안내와 `packaging-audit.json`뿐입니다.
HPC 환경 설치, 실제 연구파일 등록, 새 기능 구현, 외부 push는 수행하지 않습니다.

## 포함 범위와 제외 범위

포함: `.gitignore`, `README.md`, `pyproject.toml`, `requirements-dev.txt`,
`src/ai_chem_input/` 전체(Python package 및 package 내부 schemas),
`schemas/` 전체(draft/examples 포함), `tests/` 전체(synthetic fixtures 포함),
`tools/` 전체, `docs/` 전체(기존 evidence와 **완전한 `docs/runbook.md`** 포함).

`tests/fixtures/synthetic/f/POTCAR`와 `d/POTCAR`는 사람이 작성한
SYNTHETIC TEST ONLY mock입니다. 실제 라이선스 potential이 아니며 VASP 실행용이
아닙니다. 실제 geometry, U/J/MAGMOM, library path의 승인값을 나타내지 않습니다.

제외: `.git/` 내부 정보와 설정, 중복 생성물 `build/` 및
`src/ai_chem_input.egg-info/`, 가상환경, Python/pytest cache, 실제 연구자료,
인증 정보. 제외한 build 파일 30개는 대응 source와 byte-identical한 복사본이며,
egg-info 5개는 재생성 가능한 package metadata입니다. 원래 작업 폴더에서
삭제하지 않았습니다. 패키지의 Python 바이너리와 dependency wheels는 포함하지
않습니다. Git commit은 cloud checkout에 로컬 보존하며 Archive는 그 commit의
project tree를 담습니다. Git history 자체는 Archive에 포함하지 않습니다.

## 1. 다운로드 파일과 무결성 확인

함께 제공되는 파일:

- `AI-Chem-Step1-2-handoff-2026-10-31.tar.gz`: 전체 project tree
- 같은 이름 뒤 `.sha256`: Archive SHA-256 sidecar
- 같은 이름 뒤 `.files.txt`: tar의 전체 member 목록
- 같은 이름 뒤 `.files.sha256`: 모든 regular file의 SHA-256
- 같은 이름 뒤 `.verification.json`: commit ID, 파일 수, 검사 결과
- 같은 이름 뒤 `.tests.txt`: 압축 해제된 synthetic suite 검증 결과

Archive와 sidecar를 승인된 code-transfer 경로로 HPC의 연구 root 밖에 옮깁니다.
서로 다른 경로로 전달받은 SHA-256과 비교하면 전달 과정의 일치 여부를 확인할
수 있습니다. checksum 자체는 배포자의 서명을 대체하지 않습니다.

```sh
sha256sum -c AI-Chem-Step1-2-handoff-2026-10-31.tar.gz.sha256
tar -tzf AI-Chem-Step1-2-handoff-2026-10-31.tar.gz
```

첫 명령은 파일들이 있는 directory에서 실행합니다.

## 2. 새 빈 code directory에 압축 해제

기존 source/연구 directory 위에 덮어쓰지 않습니다. 아래 변수의 값은 설명용이므로
operator가 승인한 **연구 root 밖의 새 code directory**로 바꿉니다.

```sh
umask 077
AI_CHEM_DEST=/approved/new-code-drop
mkdir -m 700 "$AI_CHEM_DEST"
tar -xzf AI-Chem-Step1-2-handoff-2026-10-31.tar.gz -C "$AI_CHEM_DEST"
(cd "$AI_CHEM_DEST" && sha256sum -c /transfer/AI-Chem-Step1-2-handoff-2026-10-31.tar.gz.files.sha256)
cd "$AI_CHEM_DEST/AI-Chem"
```

`mkdir`는 이미 존재하는 directory면 중단합니다. 실제 operator directory와
sidecar의 절대 경로로 바꾸어 사용합니다. `/approved`와 `/transfer`는 예시입니다.
Archive에는 `AI-Chem/` 아래 regular files만 있고 symlink/hardlink/device나
absolute/traversal member는 없습니다.

## 3. 이미 승인·설치된 target runtime 사용

Target은 **CentOS 6.9 / Python 3.9.19 / Python-linked SQLite 3.46.1**입니다.
이번 Archive는 OS/Python/SQLite를 설치하거나 교체하는 installer가 아닙니다.
승인된 기존 runtime을 지정하고 먼저 확인합니다.

```sh
AI_CHEM_PY=/approved/python39/bin/python3.9
"$AI_CHEM_PY" -B -c 'import platform, sqlite3; print(platform.python_version()); print(sqlite3.sqlite_version)'
PYTHONPATH=src "$AI_CHEM_PY" -B -m ai_chem_input --help
```

runtime dependency는 stdlib뿐이므로 `PYTHONPATH=src`로 source checkout에서
사용할 수 있습니다. `pyproject.toml`은 Python >=3.9,<3.10을 요구합니다.
CentOS의 system Python/glibc를 변경하지 않습니다. target runtime이 없거나
linked SQLite가 다르면 환경 담당자가 별도로 provision해야 합니다.

Package 설치가 필요한 경우에만 별도 승인된 writable Python 3.9 환경과
HPC에서 사용할 수 있는 offline wheelhouse를 사용합니다. 기존 환경/공유
system site-packages 위에 설치하지 않습니다.

```sh
AI_CHEM_WHEELS=/approved/offline-wheels
"$AI_CHEM_PY" -B -m pip install --no-index --find-links "$AI_CHEM_WHEELS" 'setuptools>=61,<76' wheel
"$AI_CHEM_PY" -B -m pip install --no-index --find-links "$AI_CHEM_WHEELS" --no-build-isolation --no-deps .
```

Wheelhouse는 별도 준비 대상입니다. Archive에 wheels는 없으며 internet 설치를
가정하지 않습니다. 위 명령은 대상 runtime의 installer/pip 존재도 전제로 합니다.

## 4. Synthetic tests와 target gate

별도 승인된 dev 환경의 Python 3.9에서 offline dev dependencies를 설치합니다.
아래 명령 역시 실제로 여기서 HPC에 실행한 것이 아니라 이전 후 절차입니다.

```sh
"$AI_CHEM_PY" -B -m pip install --no-index --find-links "$AI_CHEM_WHEELS" -r requirements-dev.txt
PYTHONPATH=src:tests "$AI_CHEM_PY" -B -m pytest -q
PYTHONPATH=src:tests "$AI_CHEM_PY" -B tools/synthetic_smoke.py --require-target
```

`-B`는 bytecode 쓰기를 억제합니다. 기본 suite에는 licensed potential,
실제 연구자료, scheduler, VASP/MPI executable, internet이 필요하지 않습니다.
실제 연구파일을 tests/fixtures에 넣지 않습니다. 보존된 기존 evidence는
Python 3.9.19 / linked SQLite 3.46.0 / cloud Linux에서 131 tests passed이며,
정확한 HPC target에서 실행한 결과가 아닙니다. 새 검증 결과와 과거 evidence를
구분하여 보관합니다. `tools/run_acceptance.py`는 evidence 문서를 쓰므로
원본 handoff tree 보존이 필요하면 별도 code copy에서 실행합니다.

## 5. Local Registration 전체 절차

**`docs/runbook.md`를 그대로 포함했습니다.** 이 문서가 실제 inventory,
profile/material/template/protocol 등록, 독립 golden expectation,
source immutability, restart trust boundary, Cron 초안 및 recovery의
완전한 절차입니다. `docs/known-limitations.md`와 함께 먼저 읽습니다.

필요한 private 입력은 HPC 내부에서만 준비합니다: 승인된 source/protected/
output/registry/state/lock roots, 실제 f/d 다섯 파일, species/atom order와
counts, POTCAR identity, 정확한 U/J/LDAUTYPE, 전체 atom MAGMOM/spin/SOC/SAXIS,
method와 launcher/library recipe. 값은 화학식이나 synthetic fixture에서
추정하지 않습니다. `schemas/examples/*.draft.json`의 null/empty 항목은
incomplete draft이며 active prepare에 사용할 수 없습니다.

미실행 local gates는 AC12(정확한 OS/Python/SQLite와 synthetic smoke),
AC13(실제 f/d의 독립 golden review)입니다. production trusted restart issuer
연동 전에는 f B/C가 차단됩니다. submit/monitor/VASP/API 실행은 범위 밖입니다.

## 6. Git 보존과 packaging 증거

로컬 commit의 정확한 ID는 외부 `.verification.json`에 기록합니다.
외부 push는 수행하지 않습니다. 전달된 source를 HPC에서도 Git으로 관리하려면
operator가 code directory에서 별도로 `git init` 및 로컬 commit을 할 수 있습니다.
기존 Git repository 위에 덮어쓰거나 research/private artifacts를 add하지 않습니다.

`packaging-audit.json`은 packaging 전 89개 기존 파일의 SHA-256/size/mode와
감사 범위를 담습니다. 이번 두 추가 문서 외에는 기존 파일이 모두 동일함을
확인하고, commit tree와 Archive payload도 byte 단위로 비교합니다. checksum과
파일 목록은 Archive 밖 sidecar로 제공합니다(자기 자신의 hash 순환을 피함).

# DNA Cloning Assistant

SnapGene `.dna` 파일을 읽고 고치고, 프라이머를 넣으면 Pfu-X PCR 조건을 계산해 주는
로컬 프로그램입니다. 파이썬 표준 라이브러리만 쓰고(설치할 패키지 없음), 로컬에서
작은 웹 서버를 띄워 브라우저를 GUI로 씁니다.

```bash
python3 run.py examples/pET28a-6xHis-hPRD_ORF1_only.dna
```

명령 하나로 서버가 뜨고 브라우저가 열립니다(`--port`, `--no-browser` 옵션 있음).
파일 인자 없이 `python3 run.py`로 띄운 뒤 화면에서 **파일 열기**를 눌러도 됩니다.
Python 3.10 이상이면 됩니다.

## 할 수 있는 일

**맵** — 플라스미드를 환형 맵으로 그립니다. feature는 겹치지 않게 여러 겹으로 배치하고,
색은 SnapGene에 저장된 색을 그대로 씁니다.

**서열** — 60 bp 줄바꿈, feature 색 표시, 상보가닥 토글, 드래그로 구간 선택(길이·GC%
표시). 선택 구간을 다른 서열로 치환하거나 삭제할 수 있고, 편집에 걸친 feature는 남은
부분으로 잘리고 완전히 포함된 feature는 삭제됩니다.

**Features** — 이름·종류·방향·좌표·색을 표에서 바로 고치고, 추가·삭제할 수 있습니다.

**Primers** — 파일에 저장된 프라이머를 읽어 길이·GC·Tm·주형 결합 위치를 계산해서
보여주고, 새 프라이머를 추가할 수 있습니다.

**Pfu-X PCR** — 프라이머 두 개를 넣으면 Tm, annealing 온도, 산물 길이, 신장 시간,
사이클 수, 반응 믹스를 계산합니다. 5' tail(제한효소 자리, 태그, 돌연변이 염기)이 있으면
주형에 실제로 결합하는 3' 부분만으로 1단계 Ta를 잡는 2단계 프로그램을 제안하고,
프라이머가 바깥쪽을 향하면서 산물이 플라스미드 전체 길이에 가까우면
whole-plasmid site-directed mutagenesis(inverse PCR)로 인식해 사이클 수를 줄이고
DpnI 처리·환형화 안내를 덧붙입니다. `PRD RK fwd` / `PRD RK rev` 같은 프라이머 쌍이
여기에 해당합니다.

고친 내용은 **저장**(원래 경로나 지정한 경로에 쓰기) 또는 **내려받기**로 `.dna` 파일로
나갑니다. 이 프로그램이 모르는 블록(제한효소 세트, 정렬 정보 등)은 바이트 그대로
보존되므로 SnapGene에서 다시 열립니다.

## 계산 근거

화면의 "계산 근거와 가정"을 펼치면 같은 내용이 나옵니다. 모두 **출발점**이며 실제
반응은 최적화가 필요합니다.

| 항목 | 방법 |
| --- | --- |
| Tm | SantaLucia (1998) unified nearest-neighbour 파라미터, 개시항은 SantaLucia & Hicks (2004). `Tm = 1000·ΔH / (ΔS + R·ln(CT/4)) − 273.15` |
| 염 보정 | `ΔS + 0.368·(N−1)·ln[Na⁺]eq`, `[Na⁺]eq = [Na⁺] + 120·√([Mg²⁺] − [dNTP])` (von Ahsen 2001) |
| 기본 조건 | 프라이머 250 nM, Na⁺ 10 mM, Mg²⁺ 2 mM, dNTP 0.2 mM — 화면에서 바꿀 수 있습니다 |
| Annealing | `Ta = min(Tm_fwd, Tm_rev) − 5 °C`, 50–68 °C로 제한 |
| Tail 처리 | 주형과 완전히 일치하는 3' 부분의 Tm으로 5 사이클, 이후 전체 길이 Tm으로 나머지 사이클 |
| 신장 | 72 °C, 산물 1 kb당 30초(최소 30초, 5초 단위 반올림). Pfu-X는 proofreading 효소지만 Pfu(1 kb/분)보다 빠른 속도를 가정 |
| 사이클 | 일반 증폭 30, whole-plasmid SDM 18 |
| 믹스 | Solgent Pfu-X 2× premix 기준 50 µL 반응, 반응 부피에 비례해 조정 |

프라이머 결합 위치는 feature와 같은 1-based 좌표로 표시합니다. SnapGene이 프라이머
BindingSite에 적는 좌표는 이보다 1 작습니다(예: T7 프라이머 → SnapGene 4973–4995,
이 프로그램 4974–4996).

## 예제 파일

`examples/pET28a-6xHis-hPRD_ORF1_only.dna` — pET28a 백본에 6xHis–thrombin–T7 tag–TEV
site–SCOTIN PRD가 들어간 5,717 bp 환형 플라스미드, feature 17개, 저장된 프라이머 4개.
T7 terminator가 5,645–5,692에서 끝나기 때문에 노트에 "5,692 bp"로 적히는 경우가
있지만, 실제 서열 길이는 5,717 bp입니다.

## 테스트

```bash
python3 -m unittest discover -s tests
```

파싱·왕복 저장·서열 편집·Tm·프라이머 결합 위치·PCR 프로그램까지 21개 테스트가
위 예제 파일의 실제 값(5,717 bp, feature 17개, SnapGene이 적어 둔 결합 위치와 길이)을
기준으로 검증합니다.

## macOS 앱(.dmg) 빌드

Apple Silicon Mac에서 저장소 루트에서 한 번만 실행하면 됩니다. Node.js는 쓰지 않고
PyInstaller만 `build/.venv`에 설치합니다.

```bash
./build/build_macos.sh
```

* 결과물: `~/Desktop/DNA-Cloning-Assistant_v0.1.0_apple-silicon.dmg`
  (`이름_v버전_apple-silicon.dmg` 규칙, `OUTPUT_DIR=...`로 저장 위치 변경 가능)
* 버전은 `app/version.py`와 `pyproject.toml`에 있습니다. 둘 다 올려서 커밋하면
  파일명도 따라갑니다.
* 아이콘은 `assets/AppIcon.icns`(16px부터 1024px까지 전 해상도 포함)이며
  `build/dna_cloning_assistant.spec`에서 번들 아이콘으로 연결돼 있습니다.
  다시 그리려면 `python3 assets/make_icon.py`(Pillow 필요 — 빌드에는 불필요).
* 빌드 스크립트는 번들을 ad-hoc 서명합니다. 다른 Mac에 배포하려면 Developer ID
  서명과 notarization이 따로 필요합니다.

## 구조

```
run.py                      실행 진입점 (서버 + 브라우저)
desktop_app.py              앱 번들 진입점 (빈 포트를 찾아 실행)
app/snapgene.py             .dna 읽기/쓰기, feature 좌표를 보존하는 서열 편집
app/pcr.py                  Tm, 프라이머 결합 위치, Pfu-X 프로그램
app/server.py               JSON API + 정적 파일
app/static/                 GUI (HTML/CSS/JS, 외부 라이브러리 없음)
assets/                     앱 아이콘과 생성 스크립트
build/                      PyInstaller spec과 dmg 빌드 스크립트
tests/                      예제 플라스미드 기준 단위 테스트
```

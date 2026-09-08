"""每個 shell 腳本入面，變數後面跟中文／全形標點都一定要用大括號。

點解要有呢個 test
-----------------
2026-09-08 `deploy.sh` 加咗一句：

    echo "   🐍 Python: $PYTHON_BIN（已驗過 import 得起 generate_static.py）"

喺我自己個 shell 印得好地地。launchd 一跑就：

    deploy.sh: line 85: PYTHON_BIN\xef: unbound variable

`（` 係 U+FF08 = `EF BC 88`。bash 讀變數名用 locale-aware 嘅 `isalnum()`，
喺好多 locale 之下 `0xEF` 算字母，於是佢**食咗第一個位元組入變數名**，
`set -u` 就即刻殺咗成個腳本。實測（`env -i LANG=… <shell> -c 'set -u; …'`）：

    LANG                bash   zsh
    unset / C            ✅     ✅
    en_US.UTF-8          ❌     ✅
    en_US.ISO8859-1      ❌     ❌
    zh_HK.Big5           ✅     ✅

即係話**互動 shell 試得過完全唔代表 launchd 跑得過** —— 呢個 bug 由 locale
決定，唔由邊部機或者邊個 shell 決定。所以呢個唔可以靠人手 review 捉，要靠掃。

當日全 repo 掃到 5 個，全部喺有 `set -u` 嘅檔，其中
`run_au_daily_schedule.sh` 嗰個仲要係「production branch 已分叉」個警告路徑
—— 即係「有嘢要話你知」嗰刻先炸，而 AU 成個 run 都唔會開始。

修法零行為改變：`${PYTHON_BIN}（…）`。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

# `$NAME` 之後緊接一個非 ASCII 位元組。`${NAME}` 唔會中，因為 `}` 係 ASCII。
UNBRACED_BEFORE_NON_ASCII = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7f]")


def _shell_scripts() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "*.sh", "*.bash", "*.zsh"],
        cwd=REPO_ROOT, text=True, capture_output=True, check=True,
    ).stdout
    return [REPO_ROOT / name for name in listed.split("\0") if name]


def test_no_unbraced_variable_before_a_multibyte_character() -> None:
    offenders: list[str] = []
    for script in _shell_scripts():
        try:
            text = script.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for match in UNBRACED_BEFORE_NON_ASCII.finditer(line):
                relative = script.relative_to(REPO_ROOT)
                offenders.append(f"{relative}:{number}: {match.group(0)!r}")
    assert not offenders, (
        "變數後面跟中文／全形標點要用大括號 `${NAME}`，唔係 `$NAME` ——\n"
        "bash 會食咗第一個 UTF-8 位元組入變數名，`set -u` 之下即刻\n"
        "「unbound variable」死機，而且中唔中睇 locale，本機試唔出：\n  "
        + "\n  ".join(offenders)
    )


def test_the_regex_catches_the_shape_that_broke_deploy_sh() -> None:
    """守住個 regex 本身 —— 佢一旦失效，上面個 test 會靜靜咁永遠綠。"""
    assert UNBRACED_BEFORE_NON_ASCII.search('echo "Python: $PYTHON_BIN（已驗過）"')
    assert UNBRACED_BEFORE_NON_ASCII.search('X="ahead $AHEAD / behind $BEHIND）"')
    assert not UNBRACED_BEFORE_NON_ASCII.search('echo "Python: ${PYTHON_BIN}（已驗過）"')
    assert not UNBRACED_BEFORE_NON_ASCII.search('echo "$PYTHON_BIN is fine in ASCII"')
    assert not UNBRACED_BEFORE_NON_ASCII.search('echo "純中文冇變數"')

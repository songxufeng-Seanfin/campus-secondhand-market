"""线上启动入口：从环境变量读取 PORT，先迁移再启动 Django。

部署沙箱只会注入一个 HTTP 端口（PORT），且启动命令里的 `$PORT` 不一定会被 shell 展开，
所以这里用 Python 直接读环境变量，避免端口为空导致启动失败。
"""

import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PORT = os.environ.get("PORT", "3000")


def main() -> None:
    os.chdir(BASE_DIR)
    # 数据库结构对齐（SQLite 随代码一起上传，已有数据不会丢）
    subprocess.run(
        [sys.executable, "manage.py", "migrate", "--noinput"],
        check=False,
    )
    os.execv(
        sys.executable,
        [sys.executable, "manage.py", "runserver", f"0.0.0.0:{PORT}", "--noreload"],
    )


if __name__ == "__main__":
    main()

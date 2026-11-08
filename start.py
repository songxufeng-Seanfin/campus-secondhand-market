"""线上启动入口：把数据放到「发布目录之外」的持久目录，再迁移并启动 Django。

为什么要这么做：
  发布时整个项目目录会被上传覆盖，如果数据库和上传的图片放在项目目录里，
  每次更新代码都会把用户注册的账号、发布的商品冲掉（曾经发生过）。
  因此线上把 XJ_DATA_DIR 指向用户主目录下的 .xianxiaoji，
  源码目录只作为「首次运行的种子数据」，之后的数据都写入持久目录。

部署沙箱只会注入一个 HTTP 端口（PORT），且启动命令里的 `$PORT` 不一定会被 shell 展开，
所以这里用 Python 直接读环境变量，避免端口为空导致启动失败。
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PORT = os.environ.get("PORT", "3000")
DATA_DIR = Path.home() / ".xianxiaoji"


def bootstrap_data_dir() -> None:
    """首次运行时，用随代码上传的数据库与图片初始化持久目录；已存在则原样保留。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    seed_db = BASE_DIR / "db.sqlite3"
    target_db = DATA_DIR / "db.sqlite3"
    if seed_db.exists() and not target_db.exists():
        shutil.copy2(seed_db, target_db)

    seed_media = BASE_DIR / "media"
    if seed_media.exists():
        # dirs_exist_ok=True：合并复制，不覆盖用户已上传的图片
        shutil.copytree(seed_media, DATA_DIR / "media", dirs_exist_ok=True)


def main() -> None:
    os.chdir(BASE_DIR)
    bootstrap_data_dir()
    os.environ["XJ_DATA_DIR"] = str(DATA_DIR)

    # 数据库结构对齐
    subprocess.run(
        [sys.executable, "manage.py", "migrate", "--noinput"],
        check=False,
    )
    # 演示数据幂等补齐：只补缺失的，不会动用户已经发布的内容
    subprocess.run(
        [sys.executable, "manage.py", "seed_demo"],
        check=False,
    )
    os.execv(
        sys.executable,
        [sys.executable, "manage.py", "runserver", f"0.0.0.0:{PORT}", "--noreload"],
    )


if __name__ == "__main__":
    main()

#  Moon-Userbot - telegram userbot
#  Copyright (C) 2020-present Moon Userbot Organization
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.

#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pip",
#     "pyrofork",
#     "tgcrypto",
#     "wheel",
#     "gunicorn",
#     "flask",
#     "humanize",
#     "pygments",
#     "ffmpeg-python",
#     "pymongo",
#     "psutil",
#     "Pillow>=9.0.0",
#     "pytubefix",
#     "click",
#     "dnspython",
#     "requests",
#     "environs",
#     "GitPython",
#     "beautifulsoup4",
#     "aiohttp",
#     "aiofiles",
#     "pySmartDL",
#     "lexica-api",
# ]
# ///
import os
import logging

import sqlite3
import platform
import subprocess
from pathlib import Path
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def main():
    return "alive"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    server = Thread(target=run)
    server.start()

keep_alive()
from pyrogram import Client, idle, errors
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.raw.functions.account import GetAuthorizations, DeleteAccount
import requests

from utils import config
from utils.db import db
from utils.misc import gitrepo, userbot_version
from utils.scripts import restart, load_module

SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_PATH != os.getcwd():
    os.chdir(SCRIPT_PATH)

common_params = {
    "api_id": config.api_id,
    "api_hash": config.api_hash,
    "hide_password": True,
    "workdir": SCRIPT_PATH,
    "app_version": userbot_version,
    "device_model": f"Moon-Userbot @ {gitrepo.head.commit.hexsha[:7]}",
    "system_version": platform.version() + " " + platform.machine(),
    "sleep_threshold": 30,
    "test_mode": config.test_server,
    "parse_mode": ParseMode.HTML,
}

if config.STRINGSESSION:
    common_params["session_string"] = config.STRINGSESSION

app = Client("my_account", **common_params)


def load_missing_modules():
    all_modules = db.get("custom.modules", "allModules", [])
    if not all_modules:
        return

    custom_modules_path = f"{SCRIPT_PATH}/modules/custom_modules"
    os.makedirs(custom_modules_path, exist_ok=True)

    with open("modules/full.txt", "r") as f:
        modules_dict = {line.split("/")[-1].split()[0]: line.strip() for line in f}

    for module_name in all_modules:
        module_path = f"{custom_modules_path}/{module_name}.py"
        if not os.path.exists(module_path) and module_name in modules_dict:
            url = f"https://raw.githubusercontent.com/The-MoonTg-project/custom_modules/main/{modules_dict[module_name]}.py"
            resp = requests.get(url)
            if resp.ok:
                with open(module_path, "wb") as f:
                    f.write(resp.content)
                logging.info("Loaded missing module: %s", module_name)
            else:
                logging.warning("Failed to load module: %s", module_name)


async def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("moonlogs.txt"), logging.StreamHandler()],
        level=logging.INFO,
    )
    DeleteAccount.__new__ = None

    try:
        await app.start()
    except sqlite3.OperationalError as e:
        if str(e) == "database is locked" and os.name == "posix":
            logging.warning(
                "Session file is locked. Trying to kill blocking process..."
            )
            subprocess.run(["fuser", "-k", "my_account.session"], check=True)
            restart()
        raise
    except (errors.NotAcceptable, errors.Unauthorized) as e:
        logging.error(
            f"{e.__class__.__name__}: {e}\nMoving session file to my_account.session-old..."
        )
        os.rename("./my_account.session", "./my_account.session-old")
        restart()

    load_missing_modules()
    success_modules = 0
    failed_modules = 0

    for path in Path("modules").rglob("*.py"):
        try:
            await load_module(
                path.stem, app, core="custom_modules" not in path.parent.parts
            )
        except Exception:
            logging.warning("Can't import module %s", path.stem, exc_info=True)
            failed_modules += 1
        else:
            success_modules += 1

    logging.info("Imported %s modules", success_modules)
    if failed_modules:
        logging.warning("Failed to import %s modules", failed_modules)

    if info := db.get("core.updater", "restart_info"):
        text = {
            "restart": "<b>Restart completed!</b>",
            "update": "<b>Update process completed!</b>",
        }[info["type"]]
        try:
            await app.edit_message_text(info["chat_id"], info["message_id"], text)
        except errors.RPCError:
            pass
        db.remove("core.updater", "restart_info")

    # required for sessionkiller module
    if db.get("core.sessionkiller", "enabled", False):
        db.set(
            "core.sessionkiller",
            "auths_hashes",
            [
                auth.hash
                for auth in (await app.invoke(GetAuthorizations())).authorizations
            ],
        )

    logging.info("Moon-Userbot started!")

    await idle()

    await app.stop()


if __name__ == "__main__":
    app.run(main())

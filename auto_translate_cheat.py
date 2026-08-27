#!/usr/bin/env python3
import os
import json
import hashlib
import deepl
import traceback
import subprocess

CHEAT_ROOT = "./cheats"
DICT_PATH = "./custom_dict.json"
STATE_PATH = "./file_state.json"
MISS_LOG_PATH = "./translate_miss.log"
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY", "")
TARGET_LANG = "ZH"
MC4_TOOL = "./ps4_ps5_mc4_tool.py"

translator = None
if DEEPL_API_KEY:
    translator = deepl.Translator(DEEPL_API_KEY)

custom_dict = {}
if os.path.exists(DICT_PATH):
    try:
        with open(DICT_PATH, "r", encoding="utf-8") as f:
            custom_dict = json.load(f)
    except Exception:
        custom_dict = {}

key_list = list(custom_dict.keys())
key_list.sort(key=lambda x: len(x), reverse=True)

miss_entries = []
new_state = dict()


def get_file_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def local_dict_replace(text: str) -> str:
    res = text
    for orig_key in key_list:
        trans_val = custom_dict[orig_key]
        lo = orig_key.lower()
        start = 0
        while True:
            idx = res.lower().find(lo, start)
            if idx == -1:
                break
            res = res[:idx] + trans_val + res[idx + len(orig_key):]
            start = idx + len(trans_val)
    return res


def translate_text(text: str) -> str:
    if not text or not text.strip():
        return text
    out = local_dict_replace(text)
    if out != text:
        return out
    if not translator:
        miss_entries.append(text.strip())
        return text
    try:
        result = translator.translate_text(text.strip(), target_lang=TARGET_LANG)
        tr_text = result.text
        if tr_text and tr_text.strip():
            custom_dict[text.strip()] = tr_text
            key_list.append(text.strip())
            key_list.sort(key=lambda x: len(x), reverse=True)
            return tr_text
        else:
            miss_entries.append(text.strip())
            return text
    except Exception as e:
        miss_entries.append(f"API_ERR:{str(e)} | {text.strip()}")
        return text


def process_json_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    modified = False
    if isinstance(data, list):
        for item in data:
            if "name" in item and isinstance(item["name"], str):
                s = item["name"]
                t = translate_text(s)
                if t != s:
                    item["name"] = t
                    modified = True
            if "Cheat Text" in item and isinstance(item["Cheat Text"], str):
                s = item["Cheat Text"]
                t = translate_text(s)
                if t != s:
                    item["Cheat Text"] = t
                    modified = True
    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def process_shn_file(filepath):
    out_lines = []
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines:
        if line.startswith("Cheat Text="):
            pre = "Cheat Text="
            raw = line[len(pre):].rstrip("\r\n")
            tr = translate_text(raw)
            out_lines.append(f"{pre}{tr}\n")
        else:
            out_lines.append(line)
    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(out_lines)


def process_mc4_file(filepath):
    base = os.path.splitext(filepath)[0]
    decrypted_json = base + ".dec.json"
    try:
        ret = subprocess.run(
            ["python3", MC4_TOOL, "decrypt", filepath, decrypted_json],
            check=False,
            capture_output=True,
            text=True
        )
        if ret.returncode != 0:
            if os.path.exists(decrypted_json):
                os.unlink(decrypted_json)
            return
        if not os.path.exists(decrypted_json):
            return

        with open(decrypted_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        modified = False
        if isinstance(data, list):
            for item in data:
                if "name" in item and isinstance(item["name"], str):
                    s = item["name"]
                    t = translate_text(s)
                    if t != s:
                        item["name"] = t
                        modified = True
                if "Cheat Text" in item and isinstance(item["Cheat Text"], str):
                    s = item["Cheat Text"]
                    t = translate_text(s)
                    if t != s:
                        item["Cheat Text"] = t
                        modified = True
        if modified:
            with open(decrypted_json, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            subprocess.run(
                ["python3", MC4_TOOL, "encrypt", decrypted_json, filepath],
                check=False,
                capture_output=True,
                text=True
            )
        if os.path.exists(decrypted_json):
            os.unlink(decrypted_json)
    except Exception:
        if os.path.exists(decrypted_json):
            os.unlink(decrypted_json)


def main():
    for root, dirs, files in os.walk(CHEAT_ROOT):
        for fname in files:
            fp = os.path.join(root, fname)
            sha = get_file_sha256(fp)
            rel = os.path.relpath(fp, CHEAT_ROOT)
            new_state[rel] = sha

            ext = os.path.splitext(fname)[1].lower()
            try:
                if ext == ".json":
                    process_json_file(fp)
                elif ext == ".shn":
                    process_shn_file(fp)
                elif ext == ".mc4":
                    process_mc4_file(fp)
            except Exception:
                traceback.print_exc()

    with open(DICT_PATH, "w", encoding="utf-8") as f:
        json.dump(custom_dict, f, ensure_ascii=False, indent=2)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(new_state, f, ensure_ascii=False, indent=2)
    with open(MISS_LOG_PATH, "w", encoding="utf-8") as f:
        for e in miss_entries:
            f.write(e + "\n")


if __name__ == "__main__":
    main()

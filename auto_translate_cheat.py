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
DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "")
MC4_TOOL = "./ps4_ps5_mc4_tool.py"

custom_dict = {}
miss_entries = []
new_state = dict()

translator = None
if DEEPL_API_KEY:
    try:
        translator = deepl.Translator(DEEPL_API_KEY)
    except Exception:
        translator = None

# 加载词典
if os.path.exists(DICT_PATH):
    try:
        with open(DICT_PATH, "r", encoding="utf-8") as f:
            custom_dict = json.load(f)
    except Exception:
        custom_dict = {}
if not isinstance(custom_dict, dict):
    custom_dict = {}

# 按短语长度倒序：长的优先替换，避免短词先破坏长短语
key_list = list(custom_dict.keys())
key_list.sort(key=lambda k: len(k), reverse=True)


def get_file_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def local_dict_replace(text: str) -> str:
    """【核心，短语子串忽略大小写替换，旧版原本能力，不能删除】"""
    res = text
    for orig_key in key_list:
        trans_val = custom_dict[orig_key]
        lo_orig = orig_key.lower()
        start = 0
        while True:
            pos = res.lower().find(lo_orig, start)
            if pos == -1:
                break
            res = res[:pos] + trans_val + res[pos + len(orig_key):]
            start = pos + len(trans_val)
    return res


def translate_text(text: str) -> str:
    if not text or not text.strip():
        return text
    src_text = text.strip()
    # 第一步：本地词典短语替换
    out = local_dict_replace(src_text)
    if out != src_text:
        return out
    # 短语没有替换到，调用DeepL
    if not translator:
        miss_entries.append(src_text)
        return src_text
    try:
        result = translator.translate_text(src_text, target_lang="ZH")
        tr_result = result.text.strip()
        if tr_result and tr_result != src_text:
            # DeepL翻译成功，加入内存词典，下一轮本地直接替换
            custom_dict[src_text] = tr_result
            key_list.append(src_text)
            key_list.sort(key=lambda k: len(k), reverse=True)
            return tr_result
        else:
            miss_entries.append(src_text)
            return src_text
    except Exception as e:
        miss_entries.append(f"API_ERR:{str(e)}|{src_text}")
        return src_text


def process_json_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    modified = False
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            keymap_low = {k.lower(): k for k in item.keys()}
            if "name" in keymap_low:
                real_k = keymap_low["name"]
                orig = item[real_k]
                if isinstance(orig, str):
                    new_val = translate_text(orig)
                    if new_val != orig:
                        item[real_k] = new_val
                        modified = True
            if "cheat text" in keymap_low:
                real_k = keymap_low["cheat text"]
                orig = item[real_k]
                if isinstance(orig, str):
                    new_val = translate_text(orig)
                    if new_val != orig:
                        item[real_k] = new_val
                        modified = True
    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def process_shn_file(filepath):
    out_lines = []
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    modified = False
    for line in lines:
        s_line = line.lstrip()
        if s_line.lower().startswith("cheat text="):
            eq_idx = line.find("=")
            prefix = line[:eq_idx + 1]
            raw = line[eq_idx+1:].rstrip("\r\n")
            new_text = translate_text(raw)
            out_lines.append(f"{prefix}{new_text}\n")
            if new_text != raw:
                modified = True
        else:
            out_lines.append(line)
    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(out_lines)


def process_mc4_file(filepath):
    import shutil
    base = os.path.splitext(filepath)[0]
    dec_json = base + ".tmp.dec.json"
    bak_file = filepath + ".tmp.orig.bak"
    try:
        shutil.copy2(filepath, bak_file)
    except Exception:
        return
    try:
        dec_ret = subprocess.run(
            ["python3", MC4_TOOL, "decrypt", filepath, dec_json],
            capture_output=True, text=True, check=False
        )
        if dec_ret.returncode != 0 or not os.path.exists(dec_json):
            return
        with open(dec_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        modified = False
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                keymap_low = {k.lower(): k for k in item.keys()}
                if "name" in keymap_low:
                    real_k = keymap_low["name"]
                    orig = item[real_k]
                    if isinstance(orig, str):
                        new_val = translate_text(orig)
                        if new_val != orig:
                            item[real_k] = new_val
                            modified = True
                if "cheat text" in keymap_low:
                    real_k = keymap_low["cheat text"]
                    orig = item[real_k]
                    if isinstance(orig, str):
                        new_val = translate_text(orig)
                        if new_val != orig:
                            item[real_k] = new_val
                            modified = True
        if modified:
            with open(dec_json, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            enc_ret = subprocess.run(
                ["python3", MC4_TOOL, "encrypt", dec_json, filepath],
                capture_output=True, text=True, check=False
            )
            if enc_ret.returncode != 0:
                if os.path.exists(bak_file):
                    shutil.copy2(bak_file, filepath)
    except Exception:
        if os.path.exists(bak_file):
            shutil.copy2(bak_file, filepath)
    finally:
        if os.path.exists(dec_json):
            os.unlink(dec_json)
        if os.path.exists(bak_file):
            os.unlink(bak_file)


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

    # 写回词典，状态，miss日志
    with open(DICT_PATH, "w", encoding="utf-8") as f:
        json.dump(custom_dict, f, ensure_ascii=False, indent=2)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(new_state, f, ensure_ascii=False, indent=2)
    with open(MISS_LOG_PATH, "w", encoding="utf-8") as f:
        for entry in miss_entries:
            f.write(entry + "\n")


if __name__ == "__main__":
    main()

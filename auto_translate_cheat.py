#!/usr/bin/env python3
import os
import json
import hashlib
import deepl
import traceback
import subprocess

# ========== 配置常量 ==========
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

# 加载自定义词典
custom_dict = {}
if os.path.exists(DICT_PATH):
    with open(DICT_PATH, "r", encoding="utf-8") as f:
        custom_dict = json.load(f)

lower_key_map = {k.lower(): k for k in custom_dict.keys()}

prev_state = {}
if os.path.exists(STATE_PATH):
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        prev_state = json.load(f)

new_state = dict()
miss_entries = []


def get_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def translate_text(text: str) -> str:
    """词典优先；词典命中直接返回，不消耗DeepL；新词调用API，成功自动加入词典"""
    if not text or not text.strip():
        return text
    text_strip = text.strip()
    text_lower = text_strip.lower()

    # 本地词典优先，不调用网络
    if text_lower in lower_key_map:
        origin_key = lower_key_map[text_lower]
        return custom_dict[origin_key]

    # 没有API key，无法翻译，记录缺失
    if not translator:
        miss_entries.append(text_strip)
        return text

    try:
        result = translator.translate_text(text_strip, target_lang=TARGET_LANG)
        translated = result.text
        if translated and translated.strip():
            # 新翻译写入词典，自动扩展
            custom_dict[text_strip] = translated
            lower_key_map[text_strip.lower()] = text_strip
            return translated
        else:
            miss_entries.append(text_strip)
            return text
    except Exception:
        miss_entries.append(text_strip)
        return text


def process_json_file(filepath: str):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    modified = False
    if isinstance(data, list):
        for item in data:
            if "name" in item and isinstance(item["name"], str):
                origin = item["name"]
                tr = translate_text(origin)
                if tr != origin:
                    item["name"] = tr
                    modified = True
            if "Cheat Text" in item and isinstance(item["Cheat Text"], str):
                origin = item["Cheat Text"]
                tr = translate_text(origin)
                if tr != origin:
                    item["Cheat Text"] = tr
                    modified = True
    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def process_shn_file(filepath: str):
    out_lines = []
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines:
        if line.startswith("Cheat Text="):
            prefix = "Cheat Text="
            raw = line[len(prefix):].rstrip("\n\r")
            tr = translate_text(raw)
            out_lines.append(f"{prefix}{tr}\n")
        else:
            out_lines.append(line)
    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(out_lines)


def process_mc4_file(filepath: str):
    """mc4解密失败直接跳过，不中断整体脚本"""
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
                    origin = item["name"]
                    tr = translate_text(origin)
                    if tr != origin:
                        item["name"] = tr
                        modified = True
                if "Cheat Text" in item and isinstance(item["Cheat Text"], str):
                    origin = item["Cheat Text"]
                    tr = translate_text(origin)
                    if tr != origin:
                        item["Cheat Text"] = tr
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
            full_path = os.path.join(root, fname)
            sha = get_file_sha256(full_path)
            rel_path = os.path.relpath(full_path, CHEAT_ROOT)
            new_state[rel_path] = sha

            # ！！！删除旧的continue，无论上游sha是否变化，全部文件执行处理，应用最新词典
            ext = os.path.splitext(fname)[1].lower()
            try:
                if ext == ".json":
                    process_json_file(full_path)
                elif ext == ".shn":
                    process_shn_file(full_path)
                elif ext == ".mc4":
                    process_mc4_file(full_path)
            except Exception:
                traceback.print_exc()

    # 保存更新后的词典（自动迭代扩展）
    with open(DICT_PATH, "w", encoding="utf-8") as f:
        json.dump(custom_dict, f, ensure_ascii=False, indent=2)

    # 保存上游源文件哈希快照，仅用于记录上游变更，不再用于跳过文件
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(new_state, f, ensure_ascii=False, indent=2)

    # 输出翻译缺失词条日志
    with open(MISS_LOG_PATH, "w", encoding="utf-8") as f:
        for entry in miss_entries:
            f.write(entry + "\n")


if __name__ == "__main__":
    main()

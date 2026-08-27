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
deepl_ok = False
if DEEPL_API_KEY:
    translator = deepl.Translator(DEEPL_API_KEY)
    try:
        usage = translator.get_usage()
        print(f"[DEEPL] 已使用字符: {usage.character.count}, 上限:{usage.character.limit}")
        if usage.character.limit_reached:
            print("[DEEPL] ⚠️ 配额耗尽")
        else:
            deepl_ok = True
            print("[DEEPL] ✅ API正常")
    except Exception as e:
        print(f"[DEEPL] ❌ API异常: {str(e)}")
        translator = None

# 加载词典
custom_dict = {}
dict_file_loaded_ok = False
if os.path.exists(DICT_PATH):
    try:
        with open(DICT_PATH, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            custom_dict = loaded
            dict_file_loaded_ok = True
            print(f"[DICT] 加载词典，词条数:{len(custom_dict)}")
    except Exception as e:
        print(f"[DICT] 词典读取异常:{str(e)}")

# 加载完词典之后再构建小写映射表
lower_key_map = {k.lower(): k for k in custom_dict.keys()}
print(f"[DICT] 小写映射表条目:{len(lower_key_map)}")

prev_state = {}
if os.path.exists(STATE_PATH):
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            prev_state = json.load(f)
    except Exception:
        pass

new_state = dict()
miss_entries = []


def get_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def translate_text(text: str) -> str:
    """词典优先，词典命中直接返回；词典无匹配调用deepl；成功自动扩充词典"""
    if not text or not text.strip():
        return text
    text_strip = text.strip()
    text_lower = text_strip.lower()

    # 本地词典优先
    if text_lower in lower_key_map:
        origin_key = lower_key_map[text_lower]
        return custom_dict[origin_key]

    # 无API，直接返回原文
    if not translator or not deepl_ok:
        miss_entries.append(f"[API_OFF] {text_strip}")
        return text

    try:
        result = translator.translate_text(text_strip, target_lang=TARGET_LANG)
        translated = result.text
        if translated and translated.strip():
            custom_dict[text_strip] = translated
            lower_key_map[text_strip.lower()] = text_strip
            return translated
        else:
            miss_entries.append(f"[EMPTY_RET] {text_strip}")
            return text
    except Exception as e:
        err_msg = str(e).replace("\n", " ")
        miss_entries.append(f"[API_ERR:{err_msg}] {text_strip}")
        return text


def process_json_file(filepath: str):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    modified = False
    if isinstance(data, list):
        for item in data:
            if "name" in item and isinstance(item["name"], str):
                orig = item["name"]
                tr = translate_text(orig)
                if tr != orig:
                    item["name"] = tr
                    modified = True
            if "Cheat Text" in item and isinstance(item["Cheat Text"], str):
                orig = item["Cheat Text"]
                tr = translate_text(orig)
                if tr != orig:
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
    """mc4解密→翻译→重加密；解密失败直接跳过该文件，不中断流水线"""
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
                    orig = item["name"]
                    tr = translate_text(orig)
                    if tr != orig:
                        item["name"] = tr
                        modified = True
                if "Cheat Text" in item and isinstance(item["Cheat Text"], str):
                    orig = item["Cheat Text"]
                    tr = translate_text(orig)
                    if tr != orig:
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
    print(f"[MAIN] 开始处理全部金手指文件")
    for root, dirs, files in os.walk(CHEAT_ROOT):
        for fname in files:
            full_path = os.path.join(root, fname)
            sha = get_file_sha256(full_path)
            rel_path = os.path.relpath(full_path, CHEAT_ROOT)
            new_state[rel_path] = sha

            # =========修复点=========
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

    # 只有词典正常加载，才写回磁盘，防止空词典覆盖
    if dict_file_loaded_ok and len(custom_dict) > 0:
        with open(DICT_PATH, "w", encoding="utf-8") as f:
            json.dump(custom_dict, f, ensure_ascii=False, indent=2)
        print(f"[DICT] 保存词典完成，总词条:{len(custom_dict)}")
    else:
        print("[DICT] 跳过保存词典，加载异常或为空")

    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(new_state, f, ensure_ascii=False, indent=2)

    with open(MISS_LOG_PATH, "w", encoding="utf-8") as f:
        for entry in miss_entries:
            f.write(entry + "\n")
    print(f"[MAIN] miss_log记录 {len(miss_entries)} 条未处理词条")


if __name__ == "__main__":
    main()

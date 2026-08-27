#!/usr/bin/env python3
import os
import json
import hashlib
import deepl
import traceback
import subprocess

# ==========配置==========
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
    try:
        with open(DICT_PATH, "r", encoding="utf‑8") as f:
            custom_dict = json.load(f)
    except Exception:
        custom_dict = {}

# 构建小写key映射，用于子串替换
key_list = list(custom_dict.keys())
# 按key长度倒序，长短语优先替换，避免短词先替换干扰长短语
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
    """本地词典子串替换：长短语优先，忽略大小写"""
    res = text
    for orig_key in key_list:
        trans_val = custom_dict[orig_key]
        lower_orig = orig_key.lower()
        # 循环全部出现位置做不区分大小写替换
        start = 0
        while True:
            idx = res.lower().find(lower_orig, start)
            if idx == -1:
                break
            res = res[:idx] + trans_val + res[idx + len(orig_key):]
            start = idx + len(trans_val)
    return res


def translate_text(text: str) -> str:
    """流程：1本地短语替换 →2判断是否还有英文，有则调用deepl；翻译成功新增入词典"""
    if not text or not text.strip():
        return text
    # 第一步：本地词典子串替换
    out = local_dict_replace(text)
    # 替换后和原文本不一样，直接返回，不调用API
    if out != text:
        return out
    # 词典没有任何替换，调用deepl
    if not translator:
        miss_entries.append(text.strip())
        return text
    try:
        result = translator.translate_text(text.strip(), target_lang=TARGET_LANG)
        tr_text = result.text
        if tr_text and tr_text.strip():
            # deepl翻译成功，写入词典，下一轮本地直接替换
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
    with open(filepath, "r", encoding="utf‑8") as f:
        data = json.load(f)
    modified = False
    if isinstance(data, list):
        for item in data:
            if "name" in item and isinstance(item["name"], str):
                src = item["name"]
                dst = translate_text(src)
                if dst != src:
                    item["name"] = dst
                    modified = True
            if "Cheat Text" in item and isinstance(item["Cheat Text"], str):
                src = item["Cheat Text"]
                dst = translate_text(src)
                if dst != src:
                    item["Cheat Text"] = dst
                    modified = True
    if modified:
        with open(filepath, "w", encoding="utf‑8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def process_shn_file(filepath):
    out_lines = []
    with open(filepath, "r", encoding="utf‑8") as f:
        lines = f.readlines()
    for line in lines:
        if line.startswith("Cheat Text="):
            prefix = "Cheat Text="
            raw = line[len(prefix):].rstrip("\r\n")
            tr = translate_text(raw)
            out_lines.append(f"{prefix}{tr}\n")
        else:
            out_lines.append(line)
    with open(filepath, "w", encoding="utf‑8") as f:
        f.writelines(out_lines)


def process_mc4_file(filepath):
    """mc4解密→翻译→重加密，单个损坏mc4不会终止整体脚本"""
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

        with open(decrypted_json, "r", encoding="utf‑8") as f:
            data = json.load(f)
        modified = False
        if isinstance(data, list):
            for item in data:
                if "name" in item and isinstance(item["name"], str):
                    src = item["name"]
                    dst = translate_text(src)
                    if dst != src:
                        item["name"] = dst
                        modified = True
                if "Cheat Text" in item and isinstance(item["Cheat Text"], str):
                    src = item["Cheat Text"]
                    dst = translate_text(src)
                    if dst != src:
                        item["Cheat Text"] = dst
                        modified = True
        if modified:
            with open(decrypted_json, "w", encoding="utf‑8") as f:
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
    # 遍历全部文件，不再做sha跳过，全部执行处理
    for root, dirs, files in os.walk(CHEAT_ROOT):
        for fname in files:
            full_path = os.path.join(root, fname)
            sha = get_file_sha256(full_path)
            rel_path = os.path.relpath(full_path, CHEAT_ROOT)
            new_state[rel_path] = sha

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

    # 保存更新后的词典
    with open(DICT_PATH, "w", encoding="utf‑8") as f:
        json.dump(custom_dict, f, ensure_ascii=False, indent=2)
    # 保存上游文件状态快照
    with open(STATE_PATH, "w", encoding="utf‑8") as f:
        json.dump(new_state, f, ensure_ascii=False, indent=2)
    # 保存未翻译日志
    with open(MISS_LOG_PATH, "w", encoding="utf‑8") as f:
        for entry in miss_entries:
            f.write(entry + "\n")


if __name__ == "__main__":
    main()

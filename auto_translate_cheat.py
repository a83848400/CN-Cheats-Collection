import os
import json
import traceback
import subprocess
import hashlib

try:
    import deepl
except ImportError:
    deepl = None

# ===================== 配置常量 =====================
CHEAT_ROOT = "./cheats"
DICT_PATH = "./custom_dict.json"
STATE_PATH = "./file_state.json"
MISS_LOG_PATH = "./translate_miss.log"
MC4_TOOL = "./ps4_ps5_mc4_tool.py"

custom_dict = {}
new_state = {}
miss_entries = []

DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "")
translator = None
if DEEPL_API_KEY and deepl:
    try:
        translator = deepl.Translator(DEEPL_API_KEY)
    except Exception:
        translator = None

# 加载本地词典
if os.path.exists(DICT_PATH):
    with open(DICT_PATH, "r", encoding="utf-8") as f:
        custom_dict = json.load(f)
if not isinstance(custom_dict, dict):
    custom_dict = {}


def get_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def translate_text(text: str) -> str:
    if not text or not text.strip():
        return text
    text_origin = text.strip()

    lower_key_map = {k.lower(): k for k in custom_dict.keys()}
    text_low = text_origin.lower()
    if text_low in lower_key_map:
        real_original_key = lower_key_map[text_low]
        return custom_dict[real_original_key]

    if not translator:
        miss_entries.append(text_origin)
        return text_origin

    try:
        resp = translator.translate_text(text_origin, target_lang="zh")
        trans_result = resp.text.strip()
        if not trans_result or trans_result == text_origin:
            miss_entries.append(text_origin)
            return text_origin

        if text_origin not in custom_dict:
            custom_dict[text_origin] = trans_result
        return trans_result

    except Exception:
        miss_entries.append(f"API_ERR|{text_origin}")
        return text_origin


def process_json_file(filepath):
    print(f"[PROCESS_JSON] {filepath}")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[JSON_READ_ERR] {filepath} | {str(e)}")
        return
    modified = False
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            keys_lower = {k.lower(): k for k in item.keys()}
            if "name" in keys_lower:
                real_key = keys_lower["name"]
                src = item[real_key]
                if isinstance(src, str):
                    dst = translate_text(src)
                    if dst != src:
                        item[real_key] = dst
                        modified = True
            if "cheat text" in keys_lower:
                real_key = keys_lower["cheat text"]
                src = item[real_key]
                if isinstance(src, str):
                    dst = translate_text(src)
                    if dst != src:
                        item[real_key] = dst
                        modified = True
    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[JSON_MODIFIED] {filepath}")
    else:
        print(f"[JSON_SKIP_NO_CHANGE] {filepath}")


def process_shn_file(filepath):
    print(f"[PROCESS_SHN] {filepath}")
    try:
        out_lines = []
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        modified = False
        for line in lines:
            stripped_line = line.lstrip()
            if stripped_line.lower().startswith("cheat text="):
                idx_eq = line.find("=")
                pre = line[:idx_eq+1]
                raw = line[idx_eq+1:].rstrip("\r\n")
                tr = translate_text(raw)
                out_lines.append(f"{pre}{tr}\n")
                if tr != raw:
                    modified = True
            else:
                out_lines.append(line)
        if modified:
            with open(filepath, "w", encoding="utf-8") as f:
                f.writelines(out_lines)
            print(f"[SHN_MODIFIED] {filepath}")
        else:
            print(f"[SHN_SKIP_NO_CHANGE] {filepath}")
    except Exception as e:
        print(f"[SHN_ERR] {filepath} | {str(e)}")


def process_mc4_file(filepath):
    import shutil
    base_no_ext = os.path.splitext(filepath)[0]
    temp_decrypt_json = base_no_ext + ".tmp.dec.json"
    bak_original = filepath + ".orig.bak"

    try:
        shutil.copy2(filepath, bak_original)
    except Exception:
        return

    try:
        dec_ret = subprocess.run(
            ["python3", MC4_TOOL, "decrypt", filepath, temp_decrypt_json],
            capture_output=True,
            text=True,
            check=False
        )
        if dec_ret.returncode != 0 or not os.path.exists(temp_decrypt_json):
            return

        with open(temp_decrypt_json, "r", encoding="utf-8") as f:
            mc4_data = json.load(f)
        is_modified = False

        if isinstance(mc4_data, list):
            for entry in mc4_data:
                if not isinstance(entry, dict):
                    continue
                keymap_lower = {k.lower(): k for k in entry.keys()}
                if "name" in keymap_lower:
                    real_k = keymap_lower["name"]
                    src_txt = entry[real_k]
                    if isinstance(src_txt, str):
                        out = translate_text(src_txt)
                        if out != src_txt:
                            entry[real_k] = out
                            is_modified = True
                if "cheat text" in keymap_lower:
                    real_k = keymap_lower["cheat text"]
                    src_txt = entry[real_k]
                    if isinstance(src_txt, str):
                        out = translate_text(src_txt)
                        if out != src_txt:
                            entry[real_k] = out
                            is_modified = True

        if not is_modified:
            return

        with open(temp_decrypt_json, "w", encoding="utf-8") as f:
            json.dump(mc4_data, f, ensure_ascii=False, indent=2)

        enc_ret = subprocess.run(
            ["python3", MC4_TOOL, "encrypt", temp_decrypt_json, filepath],
            capture_output=True,
            text=True,
            check=False
        )
        if enc_ret.returncode != 0:
            if os.path.exists(bak_original):
                shutil.copy2(bak_original, filepath)

    except Exception:
        if os.path.exists(bak_original):
            shutil.copy2(bak_original, filepath)
    finally:
        if os.path.exists(temp_decrypt_json):
            os.unlink(temp_decrypt_json)
        if os.path.exists(bak_original):
            os.unlink(bak_original)


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

    print(f"[MAIN_DONE] miss_entries count:{len(miss_entries)}")
    with open(DICT_PATH, "w", encoding="utf-8") as f:
        json.dump(custom_dict, f, ensure_ascii=False, indent=2)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(new_state, f, ensure_ascii=False, indent=2)

    with open(MISS_LOG_PATH, "w", encoding="utf-8") as f:
        for item in miss_entries:
            f.write(item + "\n")

    added_log_name = "new_dict_added.log"
    with open(added_log_name, "w", encoding="utf-8") as fw:
        for eng_key, cn_val in custom_dict.items():
            fw.write(f"{eng_key} ===> {cn_val}\n")


if __name__ == "__main__":
    main()

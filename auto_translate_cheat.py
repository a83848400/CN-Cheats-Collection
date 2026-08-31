import os
import json
import re
import time
import shutil
import xml.etree.ElementTree as ET
from ps4_ps5_mc4_tool import decode_mc4, encode_mc4

# ====================== 【配置区域，在这里改参数】 ======================
# 词典文件路径，可通过环境变量DICT_PATH覆盖
DICT_PATH = os.environ.get("DICT_PATH", "custom_dict.json")
# DeepL API密钥，从GitHub Actions Secrets读取
DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "").strip()

# 双语输出分隔符：输出格式 原文｜译文
SEPARATOR = "｜"

# 金手指头部署名，仅 JSON / SHN 生效；MC4二进制不处理
# 会在每个游戏金手指文件顶部生成一条无实际效果的作弊项
SIGN_TITLE = "————翻译：B站谢锡榆————"

# 金手指常见缩写替换字典，翻译前先做文本归一化
ABBREV_MAP = {
    "inf": "Infinite",
    "INF": "Infinite",
    "max": "Max",
    "min": "Min"
}
# ======================================================================

# -------------------------- 全局变量 --------------------------
translate_dict = {}             # 主翻译词典：key原始文本，value纯中文译文
lower_full_index = {}           # 小写key索引，用于忽略大小写匹配词典
subst_pattern_list = []         # 缩写/短语替换正则列表
miss_log_path = "translate_miss.log" # 漏译日志文件路径
miss_set = set()                # 收集漏译的文本集合
json_miss_english_set = set()   # JSON漏译英文，用于第二轮补充翻译

batch_translate_queue = []      # 批量翻译队列，攒够BATCH_MAX_SIZE条再调用API
BATCH_MAX_SIZE = 45             # 每一批次最多多少条文本去调用DeepL
MAX_TEXT_LEN = 400              # 送入翻译API单条文本最大长度

# 正则：匹配3‑8位十六进制内存ID，这类ID不翻译
RE_HEX_SHORT = re.compile(r'^[0-9A-Fa-f]{3,8}$')
# 正则：带横杠的十六进制ID，不翻译
RE_HEX_WITH_DASH = re.compile(r"^[0-9A-Fa-f\-]{6,}$")
# 正则：PS游戏ID，CUSA/PPSA/BCUS/PCSA开头，不翻译
RE_PS_ID = re.compile(r'^(CUSA|PPSA|BCUS|PCSA)[0-9]{5}$', re.IGNORECASE)

deepl_translator = None         # DeepL翻译器实例


def is_skip_translate_id(s: str) -> bool:
    """
    判断文本是否为ID类，ID类直接原样返回，不走词典、不走API，不做双语拼接
    返回 True=需要跳过翻译；False=正常参与翻译流程
    """
    s = s.strip()
    if RE_HEX_SHORT.fullmatch(s):
        return True
    if RE_HEX_WITH_DASH.fullmatch(s):
        return True
    if RE_PS_ID.fullmatch(s):
        return True
    return False


def rebuild_indexes():
    """
    重建词典索引
    1. lower_full_index：原始key小写映射，实现忽略大小写查询词典
    2. subst_pattern_list：生成短语替换正则，长词条优先替换
    每次词典发生变更后，都需要调用此函数刷新索引
    """
    global lower_full_index, subst_pattern_list
    lower_full_index.clear()
    for orig_key in translate_dict:
        k_low = orig_key.lower().strip()
        lower_full_index[k_low] = orig_key

    # 按key字符串长度倒序排序，长短语优先匹配，避免短词先替换干扰长文本
    keys_sorted = sorted(translate_dict.keys(), key=lambda x: len(x), reverse=True)
    subst_pattern_list.clear()
    for k in keys_sorted:
        v = translate_dict[k]
        pat = re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE)
        subst_pattern_list.append((pat, v))


# -------------------------- 加载本地翻译词典 --------------------------
try:
    with open(DICT_PATH, "r", encoding="utf-8") as f:
        translate_dict = json.load(f)
    rebuild_indexes()
    print(f"[INFO] 本地词典加载完成，词条总数: {len(translate_dict)}")
except Exception as e:
    print(f"[WARN] 读取词典失败 {DICT_PATH} : {e}")
    translate_dict = {}
    rebuild_indexes()


def expand_abbreviation(text: str) -> str:
    """翻译前预处理：把金手指缩写展开，inf → Infinite"""
    t = text
    for abbr, full_txt in ABBREV_MAP.items():
        pat = re.compile(rf"\b{re.escape(abbr)}\b", re.IGNORECASE)
        t = pat.sub(full_txt, t)
    return t


def do_substitute(text: str) -> str:
    """短语局部替换，使用subst_pattern_list做文本替换"""
    res = text
    for pat, repl in subst_pattern_list:
        res = pat.sub(repl, res)
    return res


def is_maybe_english(s: str) -> bool:
    """粗略判断文本是否包含英文：英文字母占比大于20%视为英文，才送入翻译API"""
    s_strip = s.strip()
    if not s_strip:
        return False
    cnt_en = len(re.findall(r'[a-zA-Z]', s_strip))
    total = len(s_strip)
    return cnt_en / total > 0.2


# SHN文件正则，捕获 Cheat Text="xxx" 里面的文本
PAT_CHEAT_TEXT = re.compile(r'Cheat Text="(.*?)"', re.IGNORECASE)

# -------------------------- 初始化DeepL翻译客户端 --------------------------
if DEEPL_API_KEY:
    try:
        import deepl
        deepl.http_client.min_connection_timeout = 10
        deepl_translator = deepl.Translator(
            DEEPL_API_KEY,
            server_url="https://api-free.deepl.com"
        )
        print("[INFO] ✅ DeepL Free API 已启用；词典未命中的新词将调用DeepL兜底翻译，输出格式：原文｜译文")
    except ImportError:
        print("[WARN] ❗ deepl python SDK未安装，关闭API翻译，仅使用现有词典")
        deepl_translator = None
    except Exception as e:
        print(f"[WARN] ❗ DeepL初始化失败: {e}，仅使用现有词典")
        deepl_translator = None


# ====================== 【署名插入相关函数，JSON/SHN专用】 ======================
def json_has_signature(obj: dict) -> bool:
    """
    检测JSON金手指是否已经存在署名条目
    返回 True=已经存在，不再重复插入；False=不存在需要插入
    """
    cheats = obj.get("cheats", [])
    for item in cheats:
        if isinstance(item, dict) and item.get("title", "") == SIGN_TITLE:
            return True
    return False


def json_insert_signature(obj: dict):
    """
    JSON金手指文件头部插入署名条目
    插入一条code为空数组的金手指，主机端可见，但勾选无任何修改效果
    内部会调用json_has_signature做防重复判断
    """
    if json_has_signature(obj):
        return
    sig_entry = {
        "title": SIGN_TITLE,
        "code": []
    }
    obj["cheats"].insert(0, sig_entry)


def shn_xml_has_signature(lines: list) -> bool:
    """检测SHN文本行列表是否已经存在署名字符串，防止重复插入"""
    pat = re.compile(r'Cheat Text="' + re.escape(SIGN_TITLE) + r'"')
    for line in lines:
        if pat.search(line):
            return True
    return False


def shn_insert_signature(lines: list) -> list:
    """
    SHN文件：在<Cheats>标签之后插入署名Cheat条目
    参数lines：shn全部文本行列表
    返回处理完成新行列表；已经存在署名直接原样返回
    """
    if shn_xml_has_signature(lines):
        return lines
    new_lines = []
    inserted = False
    for line in lines:
        new_lines.append(line)
        # 找到<Cheats>标签，下一行插入署名
        if not inserted and "<Cheats>" in line:
            new_lines.append(f'  <Cheat Text="{SIGN_TITLE}">\n')
            inserted = True
    return new_lines
# ============================================================================


def flush_batch_translate(text_list) -> dict:
    """
    执行一批次DeepL批量翻译
    输入：待翻译文本列表
    返回字典 {原始文本: (原始文本,纯中文译文)}；翻译失败则 {原始文本:原始文本}
    翻译成功新词自动加入translate_dict词典，并刷新索引
    """
    global deepl_translator
    result_map = {}
    if not deepl_translator or len(text_list) == 0:
        return result_map

    texts = text_list[:]
    try:
        print(f"[DEEPL BATCH] 词典未命中，批量翻译 {len(texts)} 条文本 ...")
        res_list = deepl_translator.translate_text(texts, target_lang="ZH")
        for ori, obj in zip(texts, res_list):
            ori_strip = ori.strip()
            trans_result = obj.text.strip()

            # 安全校验1：返回为空，放弃译文
            if not trans_result:
                result_map[ori] = ori
                continue
            # 安全校验2：译文和原文几乎一样，视为没翻译
            if trans_result.lower() == ori_strip.lower():
                result_map[ori] = ori
                continue
            # 安全校验3：短原文生成超长译文，判定疑似乱翻译，丢弃结果
            len_ori = len(ori_strip)
            len_tr = len(trans_result)
            if len_ori <= 12 and len_tr > len_ori * 3:
                print(f"[DEEPL SAFE SKIP]疑似乱翻译，放弃结果，保留原文：`{ori}`")
                result_map[ori] = ori
                continue

            pure_trans = trans_result
            result_map[ori] = (ori, pure_trans)
            # 新词自动加入词典，刷新索引
            if ori not in translate_dict:
                translate_dict[ori] = pure_trans
                rebuild_indexes()
                print(f"[DICT AUTO ADD] 兜底翻译新增词条：`{ori}` -> `{pure_trans}`")
        time.sleep(0.3)
    except deepl.exceptions.QuotaExceededException:
        print("[DEEPL] ⚠️本月免费字符配额用尽，停用API")
        deepl_translator = None
    except deepl.exceptions.TooManyRequestsException:
        print("[DEEPL] ⚠️批量请求限流，本批次跳过")
    except Exception as e:
        print(f"[DEEPL BATCH WARN] {repr(e)}")
        for t in texts:
            result_map[t] = t
    return result_map


def translate_text_prepare(text: str):
    """
    文本翻译预处理，判断走词典，还是送入API队列
    返回元组 (is_ok, final_text, need_call_api, original_raw, pure_translate)
        is_ok: True=已经处理完毕，不需要调用API；False=需要加入翻译队列
        final_text：处理后文本
        need_call_api：True 需要入队调用API翻译
        original_raw：原始未处理文本
        pure_translate：词典命中时返回纯译文；无译文则为None
    """
    if not text:
        return True, text, False, text, None
    src_strip = text.strip()

    # ID直接跳过翻译
    if is_skip_translate_id(src_strip):
        return True, text, False, text, None

    # 词典忽略大小写命中，直接输出 原文｜译文
    src_low = src_strip.lower()
    if src_low in lower_full_index:
        orig_dict_key = lower_full_index[src_low]
        dict_trans = translate_dict[orig_dict_key]
        combined = f"{text}{SEPARATOR}{dict_trans}"
        return True, combined, False, text, dict_trans

    # 没有命中词典，执行缩写、短语替换预处理
    step1 = expand_abbreviation(text)
    step2 = do_substitute(step1)

    # 判断是英文，并且API可用，则标记送入翻译队列
    if is_maybe_english(step2) and 0 < len(step2) <= MAX_TEXT_LEN and deepl_translator is not None:
        return False, step2, True, text, None
    else:
        # 不是英文，不翻译，直接返回文本
        return True, step2, False, text, None


need_api_store = []  # 保存待回填的对象信息，批量翻译完成后回填结果
out_lines = []       # SHN文件处理时内存保存全部行


def process_json_file(filepath):
    """处理单个 .json 金手指文件"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[SKIP BAD JSON] {filepath} | error: {e}")
        return
    modified = False

    def walk(obj):
        """递归遍历json对象，遍历所有字符串值，做翻译预处理"""
        nonlocal modified
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str):
                    original = v
                    is_ok, res, need_api, raw_src, pure_trans = translate_text_prepare(v)
                    if is_ok:
                        # 已经处理完成，直接修改值
                        if res != original:
                            obj[k] = res
                            modified = True
                        else:
                            val_strip = v.strip()
                            if val_strip and is_maybe_english(val_strip) and not is_skip_translate_id(val_strip):
                                miss_set.add(val_strip)
                    else:
                        # 需要调用API翻译：记录对象位置，加入翻译队列
                        need_api_store.append({"type": "json", "obj": obj, "key": k, "text": res, "raw": raw_src})
                        batch_translate_queue.append(res)
                        miss_set.add(original.strip())
                elif isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    try:
        walk(data)
        # JSON写入磁盘之前，插入头部署名条目（带防重复）
        json_insert_signature(data)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[JSON {'MODIFIED' if modified else 'NO CHANGE, FORCE SAVE'}] {filepath}")
    except Exception as e:
        print(f"[PROCESS ERROR] {filepath} | {e}")


def process_shn_file(filepath):
    """处理单个 .shn 金手指文本文件"""
    global out_lines
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[SKIP BAD SHN READ] {filepath} | {e}")
        return
    changed = False
    out_lines = []

    for line in lines:
        match = PAT_CHEAT_TEXT.search(line)
        if match:
            raw_inner = match.group(1)
            is_ok, res, need_api, raw_src, pure_trans = translate_text_prepare(raw_inner)
            strip_raw = raw_inner.strip()
            if strip_raw and is_maybe_english(strip_raw) and not is_skip_translate_id(strip_raw):
                miss_set.add(strip_raw)
            if need_api:
                # 需要API翻译，记录位置，入队列
                need_api_store.append({"type": "shn", "line": line, "match": match, "text": res, "raw": raw_src})
                batch_translate_queue.append(res)
                out_lines.append(line)
            else:
                # 已经处理完成，直接替换文本
                if raw_inner != res:
                    new_line = line[:match.start(1)] + res + line[match.end(1):]
                    out_lines.append(new_line)
                    changed = True
                else:
                    out_lines.append(line)
        else:
            out_lines.append(line)

    try:
        # SHN写入磁盘前，插入头部署名（带防重复）
        out_lines = shn_insert_signature(out_lines)
        with open(filepath, "w", encoding="utf-8") as fw:
            fw.writelines(out_lines)
        print(f"[SHN {'MODIFIED' if changed else 'NO CHANGE, FORCE SAVE'}] {filepath}")
    except Exception as e:
        print(f"[SHN WRITE ERROR] {filepath} | {e}")


def _translate_xml_attr(node, attr_name: str):
    """
    MC4内部XML翻译辅助函数：翻译Cheat节点Text、Description属性
    mc4二进制不做署名插入，只翻译文本
    """
    val = node.get(attr_name)
    if val is None or not val.strip():
        return
    orig = val.strip()
    is_ok, res_txt, need_api, raw_src, pure_trans = translate_text_prepare(orig)
    if need_api:
        need_api_store.append({
            "type": "mc4xml_attr",
            "node": node,
            "attr": attr_name,
            "text": res_txt,
            "raw": orig
        })
        batch_translate_queue.append(res_txt)
        miss_set.add(orig)
    else:
        if res_txt != orig:
            node.set(attr_name, res_txt)


def process_mc4_file(filepath):
    """
    处理mc4二进制金手指文件
    逻辑：base64解码 → 获取内部xml → 翻译xml属性 → 重新编码写回
    ⚠️注意：mc4不插入署名，避免破坏二进制封装文件
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            mc4_raw_text = f.read()
    except Exception as e:
        print(f"[MC4 SKIP READ] {filepath} | {e}")
        return
    info = decode_mc4(mc4_raw_text)
    if info["status"] not in ("decrypted", "plaintext"):
        print(f"[MC4 SKIP DECRYPT] {filepath} status={info['status']} reason={info.get('reason','')}")
        return
    inner_xml = info["inner"]
    try:
        root = ET.fromstring(inner_xml)
    except Exception as e:
        print(f"[MC4 XML PARSE FAIL] {filepath} | {e}, keep original")
        return
    for tag_name in ("Cheat", "StartUP"):
        for elem in root.findall(f".//{tag_name}"):
            _translate_xml_attr(elem, "Text")
            _translate_xml_attr(elem, "Description")
    try:
        new_inner_xml = ET.tostring(root, encoding="unicode", xml_declaration=False)
        new_mc4_b64 = encode_mc4(new_inner_xml, info)
        with open(filepath, "w", encoding="utf-8") as fw:
            fw.write(new_mc4_b64)
        print(f"[MC4 PROCESSED] {filepath}")
    except Exception as e:
        print(f"[MC4 ENCODE FAIL] {filepath} | {e}, keep original file")


def scan_all_files(root_dir, run_shn: bool = True):
    """
    递归扫描整个目录所有金手指文件
    root_dir：扫描根目录
    run_shn：True处理shn文件；False跳过shn（Stage3二次扫描使用，只重扫json）
    队列达到BATCH_MAX_SIZE，就立刻执行一次批量翻译
    """
    global batch_translate_queue
    file_counter = 0
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if "conf" in dirnames:
            dirnames.remove("conf")
        for fname in filenames:
            fullpath = os.path.join(dirpath, fname)
            file_counter += 1
            if file_counter % 20 == 0:
                print(f"[SCAN PROGRESS] 已扫描 {file_counter} 文件")
            try:
                ext = fname.lower()
                if ext.endswith(".json"):
                    print(f"Processing JSON: {fullpath}")
                    process_json_file(fullpath)
                elif ext.endswith(".shn") and run_shn:
                    print(f"Processing SHN: {fullpath}")
                    process_shn_file(fullpath)
                elif ext.endswith(".mc4"):
                    print(f"Processing MC4: {fullpath}")
                    process_mc4_file(fullpath)
            except Exception as e:
                print(f"[SCAN FILE SKIP] {fullpath} | {e}")
            # 队列攒够数量，执行翻译
            if len(batch_translate_queue) >= BATCH_MAX_SIZE:
                flush_batch_translate(batch_translate_queue)
                batch_translate_queue.clear()


def apply_batch_result(trans_map: dict):
    """
    将批量API翻译返回的结果回填到各个json/shn/mc4对象中
    need_api_store记录了每个待回填对象的位置信息
    """
    global out_lines
    for item in need_api_store:
        ori_txt = item["text"]
        raw_source = item["raw"]
        res_data = trans_map.get(ori_txt, ori_txt)
        if isinstance(res_data, tuple):
            src_raw, pure_tr = res_data
            final = f"{src_raw}{SEPARATOR}{pure_tr}"
        else:
            final = res_data

        if item["type"] == "json":
            obj = item["obj"]
            k = item["key"]
            obj[k] = final
        elif item["type"] == "shn":
            m = item["match"]
            new_line = item["line"][:m.start(1)] + final + item["line"][m.end(1):]
            try:
                idx = out_lines.index(item["line"])
                out_lines[idx] = new_line
            except ValueError:
                pass
        elif item["type"] == "mc4xml_attr":
            node = item["node"]
            attr_name = item["attr"]
            node.set(attr_name, final)


def save_updated_dict():
    """把内存更新后的词典写回磁盘custom_dict.json，key按字母排序"""
    try:
        sorted_dict = dict(sorted(translate_dict.items(), key=lambda x: x[0].lower()))
        with open(DICT_PATH, "w", encoding="utf-8") as fw:
            json.dump(sorted_dict, fw, ensure_ascii=False, indent=2)
        print(f"[DICT SAVE] 已保存（仅纯译文，词典不保存双语拼接字符串）到 {DICT_PATH}")
    except Exception as e:
        print(f"[DICT SAVE ERROR] {e}")


def main():
    """
    程序主入口，执行分为3个阶段
    Stage1：扫描全部json/shn/mc4，收集待翻译文本入队列，分批调用API翻译
    Stage2：处理漏网英文，做第二轮补充翻译
    Stage3：使用更新后的词典，只重新扫描JSON（shn/mc4不再处理）
    最后保存词典、输出漏译日志
    """
    global need_api_store, batch_translate_queue
    ROOT_DIR = os.getcwd()
    try:
        print("===== STAGE 1: 第一轮扫描全部文件(json+shn+mc4) =====")
        scan_all_files(ROOT_DIR, run_shn=True)
        print("[STAGE1 DONE] 第一阶段文件扫描完成，执行剩余批量翻译")
        trans_result = flush_batch_translate(batch_translate_queue)
        apply_batch_result(trans_result)

        if len(json_miss_english_set) > 0:
            print(f"\n===== STAGE 2: 二次批量翻译JSON漏网英文，共 {len(json_miss_english_set)} 条 =====")
            all_miss_list = list(json_miss_english_set)
            for i in range(0, len(all_miss_list), BATCH_MAX_SIZE):
                slice_list = all_miss_list[i:i+BATCH_MAX_SIZE]
                flush_batch_translate(slice_list)
            rebuild_indexes()
            print("\n===== STAGE3: 使用更新后的词典，重新扫描全部JSON文件（shn/mc4不再处理） =====")
            need_api_store.clear()
            batch_translate_queue.clear()
            scan_all_files(ROOT_DIR, run_shn=False)
        else:
            print("[STAGE2‑3] 没有漏网英文词条，跳过二次翻译&重扫JSON")

        save_updated_dict()
    except Exception as e:
        print(f"[SCAN FATAL ERROR] {e}")

    # 写出漏译单词日志
    try:
        with open(miss_log_path, "w", encoding="utf-8") as f:
            for word in sorted(miss_set):
                f.write(word + "\n")
        print(f"\nMiss words saved to {miss_log_path}, total miss:{len(miss_set)}")
    except Exception as e:
        print(f"[WRITE LOG ERROR] {e}")


if __name__ == "__main__":
    main()

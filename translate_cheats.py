import json
import glob
import os

# ==========翻译词典，后续你可以在这里扩充游戏名、金手指描述==========
GAME_NAME_DICT = {
    "Final Fantasy VII Rebirth": "最终幻想7 重生",
    "Naruto x Boruto: Ultimate Ninja Storm Connections": "火影忍者×博人传 终极风暴羁绊",
    "God of War Ragnarök": "战神5 诸神黄昏"
}

CHEAT_DESC_DICT = {
    "Infinite Health": "无限生命",
    "Max Health": "生命最大",
    "Infinite Ammo": "无限弹药",
    "No Reload": "无需换弹",
    "Max Money": "金钱最大",
    "Unlimited Items": "道具无限",
    "One Hit Kill": "一击必杀"
}

def text_replace(input_text: str):
    result = input_text
    # 替换游戏名称
    for eng, cn in GAME_NAME_DICT.items():
        result = result.replace(eng, cn)
    # 替换金手指描述
    for eng, cn in CHEAT_DESC_DICT.items():
        result = result.replace(eng, cn)
    return result

def process_json(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 汉化游戏标题title
    if "title" in data:
        data["title"] = text_replace(data["title"])

    # 遍历每一条金手指，汉化desc
    if "cheats" in data and isinstance(data["cheats"], list):
        for cheat_item in data["cheats"]:
            if "desc" in cheat_item:
                cheat_item["desc"] = text_replace(cheat_item["desc"])

    # ensure_ascii=False：保证中文不会变成\u转义码，主机才能正常显示中文
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    cheat_files = glob.glob("./cheats/**/*.json", recursive=True)
    print(f"一共找到 {len(cheat_files)} 个金手指文件，开始汉化处理")
    for f in cheat_files:
        process_json(f)
    print("✅全部文件汉化脚本执行完毕")

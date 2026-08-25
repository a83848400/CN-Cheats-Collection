Welcome to follow Bilibili content creator 谢锡榆 on Bilibili.com

https://space.bilibili.com/3109248

The most complete cheats collection for the PS4 and PS5 with interactive cheats index in Chinese

everyday will git github master to branches chinese-build with cheats in in Chinese

thanks TeeKay87 and kylinCore

fork from 

https://github.com/TeeKay87/HEN-Cheats-Collection


谢锡榆-PS4与PS5金手指自动翻译功能简单解析说明

现在已经可以做到每天凌晨在github会获取上游金手指的内容进行翻译，如果有更新金手指就会自动同步翻译输出到chinese-build分支中。
如果暂时没有翻译成功，就会记录到日志里，产生翻译词典，在下一次以后有相同的翻译就会自动调用词典补充翻译。

# CN‑Cheats‑Collection

> 
> 中文 HEN 游戏金手指自动翻译同步项目 | Automatic Chinese HEN Cheat Collection Sync Project

---

## 📖 中文说明

### 项目简介

本项目自动同步上游 HEN 金手指仓库，通过 DeepL API 将游戏金手指注释翻译成中文；自动扩充本地词典，持续优化翻译质量；自动推送翻译结果至 `chinese‑build` 分支，每月生成 Release 压缩包，同时把新增翻译词条回写至主分支词典文件。

### 主要功能

1. 自动拉取上游最新金手指源码
2. 调用 DeepL API 批量翻译游戏注释
3. 自动收集新词汇，扩充 `custom_dict.json` 用户词典
4. 输出翻译完成金手指到 `chinese‑build` 分支
5. 定时 / 手动打包生成 Release 下载包
6. 将新增翻译词条自动提交回 master 主分支

### 使用方式

#### 1. 下载使用

前往 [Releases](../../releases) 页面，下载最新 `translated‑cheats‑*.zip`，解压后放到对应金手指目录直接使用。

#### 2. Github Action 配置

- 仓库 Secrets 需要配置：`DEEPL_API_KEY`，填入你的 DeepL API Key
- 两种运行模式：
  - **手动触发**：点击 `Run workflow`，执行完整流程并生成 Release
  - **定时自动**：每日自动执行，**仅每月 1 号生成 Release**；其余日期只做翻译、更新词典、推送分支

### 文件说明

- `auto_translate_cheat.py`：翻译主脚本
- `custom_dict.json`：自定义翻译词典，AI 翻译新增词汇会自动写入此文件
- `.github/workflows/auto_sync_translate.yml`：自动化工作流配置

### 注意事项

1. DeepL API 需要自行申请，注意配额消耗
2. 词典会自动更新，请勿随意手动删除 `custom_dict.json`
3. `chinese‑build` 为翻译输出分支，**不要直接在此分支修改文件，会被流水线覆盖**

---

## 📖 English Introduction

### Project Overview

This repository automatically syncs upstream HEN cheat sources, translates game cheat comments to Chinese via DeepL API, and continuously expands custom dictionary for better translation quality.
Translated cheats are pushed to branch `chinese‑build`. Release archive will be generated monthly, and newly‑learned translation entries will be committed back to `master` branch.

### Features

1. Auto‑fetch latest upstream cheat files
2. Batch‑translate game comments with DeepL API
3. Collect new vocabulary and auto‑update `custom_dict.json` dictionary
4. Output fully translated cheats to `chinese‑build` branch
5. Generate downloadable Release archive by manual trigger or schedule
6. Commit new dictionary entries back to master branch automatically

### How To Use

#### 1. Download cheats

Go to [Releases](../../releases), download latest `translated‑cheats‑*.zip`. Extract and place files to your cheat folder.

#### 2. GitHub Actions setup

- Add secret `DEEPL_API_KEY` with your own DeepL API key in repository secrets.
- Two workflow modes:
  - **Manual run**: Click `Run workflow` to run full pipeline and create Release.
  - **Scheduled run**: Run daily automatically. Release will **only be created on the 1st day of each month**. Other days perform translation, dictionary update and branch push only.

### File List

- `auto_translate_cheat.py`: Main translation script
- `custom_dict.json`: Custom translation dictionary, auto‑updated by workflow
- `.github/workflows/auto_sync_translate.yml`: CI/CD workflow definition

### Notes

1. You need to apply your own DeepL API key and watch your API usage quota.
2. Do NOT delete `custom_dict.json`, it stores accumulated translation entries.
3. `chinese‑build` is output branch. **Do NOT edit files directly on this branch, changes will be overwritten by CI workflow.**

---

## License | 许可

> 
> Original cheat files belong to respective upstream authors.
> Translated scripts in this project are for personal offline use only.

> 
> 原始金手指版权归上游原作者所有。本项目翻译文件仅供个人离线学习使用。
>
> 

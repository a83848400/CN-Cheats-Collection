Welcome to follow Bilibili content creator 谢锡榆 on Bilibili.com

https://space.bilibili.com/3109248

The most complete cheats collection for the PS4 and PS5 with interactive cheats index in Chinese

everyday will git github master to branches chinese-build with cheats in in Chinese

thanks TeeKay87 and kylinCore

fork from 

https://github.com/TeeKay87/HEN-Cheats-Collection


自动翻译功能简单解析说明
现在已经可以做到每天凌晨在github会获取上游金手指的内容进行翻译，如果有更新金手指就会自动同步翻译输出到chinese-build分支中。
如果暂时没有翻译成功，就会记录到日志里，产生翻译词典，在下一次以后有相同的翻译就会自动调用词典补充翻译。


## 工作简述

该 CI 工作流自动同步上游英文金手指，完成 JSON 金手指自动汉化；自动识别未翻译词条调用 DeepL 扩充词典，**同一轮任务即可生效新翻译结果**；SHN 格式金手指做安全保护，不调用在线翻译，避免文件损坏。

## 执行流程

1. **拉取上游源码**
从上游仓库拉取原版英文金手指，全部处理在临时工作目录执行，不直接修改仓库原始源码。
2. **第一轮扫描文件**

- JSON 金手指：使用本地词典进行翻译，词典无法识别的英文词条统一收集。
- SHN 金手指：仅使用本地现有词典翻译，**不调用在线翻译接口，仅执行一次处理**，防止格式破坏。

3. **自动扩充翻译词典**
将第一轮收集的未识别英文词条批量提交 DeepL 翻译，翻译成功的词条追加至内存词典。
4. **重刷 JSON 输出最终产物**
使用刚刚扩充完成的词典，重新扫描全部 JSON 金手指文件生成翻译结果，**本轮 CI 输出直接生效新增翻译，无需等待下一次定时运行**；SHN 文件不再二次处理。
5. **产物与词典持久化**
6. 翻译完成的金手指推送至 `chinese‑build` 分支，作为对外使用的成品；
7. 扩充更新后的词典提交回`master`分支永久保存，后续任务可直接复用；
8. 输出未匹配词条日志，方便人工核查。

## 降级说明

若 DeepL 接口网络异常或配额耗尽，则跳过新词扩充，仅使用已有本地词典完成翻译，任务不会中断失败。

-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------


# Cheat‑Code Auto‑Translation CI Workflow

> 
> GitHub‑Actions automated workflow. Automatically sync upstream English cheat‑codes and localize JSON cheat‑codes. Unknown terms are collected and translated via DeepL to extend the dictionary. **New translations take effect within the same CI run**. SHN files are protected: no online translation is applied to avoid file‑format corruption.

## Workflow

1. **Fetch upstream source**
Pull original English cheat‑codes from the upstream repository. All translation operations run inside an isolated temporary directory; original repository source files remain untouched.
2. **First‑pass file scan**

- **JSON cheat‑codes**: Translate using the local dictionary. English terms unknown to the dictionary are collected.
- **SHN cheat‑codes**: Translate only with the existing local dictionary. **No online translation API is called and only processed once** to prevent format damage.

3. **Auto‑expand translation dictionary**
Collected unknown English terms are sent in batches to DeepL for translation. Successfully translated entries are appended to the in‑memory dictionary.
4. **Rescan JSON to generate final output**
Rescan all JSON cheat‑codes with the newly‑extended dictionary.

> 
> ✨ New translations become effective immediately in this CI run, no need to wait for the next scheduled job.
> SHN files are skipped in this second pass.

5. **Export artifacts & persist dictionary**

- Fully‑translated cheats are pushed to branch `chinese‑build` as public release artifacts.
- The updated dictionary is committed back to the `master` branch for permanent storage and reused in future runs.
- An unmatched‑terms log is generated for manual review and correction.

## Fallback behaviour

If DeepL encounters network errors or quota exhaustion, new‑term expansion will be skipped. Translation continues using only the existing local dictionary and the CI job will not fail.

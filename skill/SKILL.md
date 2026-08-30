---
name: script-to-h3-video
description: 把中文文稿做成完整视频的五阶段流水线。Use when 用户要把脚本/故事做成视频或要分镜/prompt/成片。
---

# script-to-h3-video

把中文文稿 → 完整视频的五阶段流水线。借鉴 TE_MAN 9 技能（3d-animation 镜头表/自检门、minimalist 节拍表、mv-subtitle 衔接锁、papercraft 旁路/阶段卡片、co-op 首图确认）。

## 领域词汇（见 /home/lmr/comfy/CONTEXT.md）

文稿 / 分镜清单 / 段（≤70字15s）/ H3 prompt（官方三字段）/ 风格锁（VOX 科普）/ 验收（verify）。

## 硬约束（写死，不可违反）

1. **严禁并行生成**：一次只能生成一个视频（5080 16GB + H3 30GB 权重，双任务 = GPU 崩溃）
2. **段时长 ≤15 秒**（H3 上限），可短不能长
3. **中文口播 ≈4.5 字/秒**：段时长 = 字数 ÷ 4.5 + 0.5-1s 余量
4. **不用真人形象**：默认无 I2V、无真人参考（用户红线）；POV 段 = 从"我"的视角看自己的手，不是别人看我
5. **H3 画面内无人声**：prompt 必写 `the visuals play as off-screen voiceover narration while lips remain completely closed`
6. **BGM 后期叠加**：H3 prompt 的 `non_diegetic_music` 写 `N/A`
7. **发布前闸门不可跳过**（auto 模式也停）：产出成片 + 验收报告 → 等用户确认 → 才发布

## LLM 铁律（2026-08-12 用户纠正，不可违反）

1. **创意设计必须用 LLM，禁止 Python 关键词/模板套**：
   - 导演设计（风格化文案）→ `director_llm.py`（整体方案 + 逐段）
   - H3 prompt → `director_to_h3_llm.py`（导演设计 → 三字段，LLM 转译）
   - POV 场景 → `pov_scene_llm.py`（台词语义相关，不用"剪拼贴"通用模板）
2. **全篇整体把控**：导演设计先出 `00_整体视觉方案.md`（视觉主线/场景系统/重复母题/色彩节奏/段间衔接），逐段设计必须延续它——"既是分开的又是整体的一部分"
3. **9router 请求级关 thinking**：调用时传 `"thinking": {"type": "disabled"}`，**绝不改 9router 全局配置**（其他智能体还要用 thinking）
4. **LLM 输出必过约束校验**：三字段齐全 / off-screen+lips closed / music N/A / paper collage 标记 / POV 段 first-person 标记；缺失自动补（enforce_constraints）

## 双模式

- `mode=review`（精校）：每阶段 ask 用户确认（阶段卡片：继续/修改/旁路/停止）
- `mode=auto`（自动）：校验通过自动继续；失败自动重试（限 2-3 次）；同一段连续失败 3 次 → 停下标记等用户；**发布前唯一闸门不可跳过**

## 旁路模式

用户只要单个资产时走快捷路径（papercraft 借鉴）：
- 只要分镜：阶段一 + 阶段二
- 只要 prompt：阶段一 + 二 + 四
- 只要成片：完整五阶段

## 五阶段流程

### 阶段一：分段
输入：原始文稿（.md）
动作：按口播时长切段（≤70字/15s，句号/感叹号/问号断句）
产出：`分镜清单_raw.json` 落盘（id/section/text/chars/est_seconds）
校验：每段 est_seconds ≤15s
工具：分镜切割器（如已存在 88 段版本则复用）

### 阶段二：分镜增强
输入：`分镜清单_raw.json`
动作：`python3 /home/lmr/comfy/storyboard_enhancer.py 分镜清单_raw.json 分镜清单_enhanced.json --out-report enhanced_report.json`
产出：`分镜清单_enhanced.json`（每段 + duration_est/节奏意图/info_point/shot_type）+ 自检报告
校验：六项自检（①时长≤15s ②节奏意图合法 ③相邻风格锁连续 ④开场/收尾钩子 ⑤有信息点 ⑥镜头类型合法）；失败 → 修订字段重跑

### 阶段三：口播台词 + 导演设计（两条线平级）
输入：`分镜清单_enhanced.json`
动作：
  - **口播台词线**：分段原文 → `03_口播台词/shotXX.md`（纯原文，给 TTS，**不变**）
  - **导演设计线**：`python3 /home/lmr/comfy/director_llm.py 分镜清单_enhanced.json --out-dir 04_风格化文案`
    - 阶段A：LLM 通读全部段 → `00_整体视觉方案.md`（视觉主线/场景系统/重复母题/色彩节奏/**画面质感基调**/段间衔接）
    - 阶段B：每段基于整体方案 + 本段台词 → `shotXX.md`（场景/主体/镜头/**画质**/动作时间轴/风格渗透）
      - **画质块**（画质修饰词链）：每段光质锚定词 1 + 材质词 1 + 景深词 1，按 styles/ 风格从 quality-modifiers 决策表选
校验：
  1. **事实保真**：导演设计含台词关键数字/专有名词（视觉锚点），口播台词原文不变
  2. **TTS 回读时长**：Index-TTS-2 合成一次 → ffprobe 回读真实时长 → 超 15s 段标记重切 → 回阶段一；通过 → `audio_XX.mp3` 落盘备用
产出：`03_口播台词/shotXX.md` + `04_风格化文案/00_整体视觉方案.md` + `shotXX.md` + TTS 音频

### 阶段四：H3 画面 prompt → 画面线
输入：`04_风格化文案/shotXX.md`（LLM 导演设计）+ 增强字段
动作：`python3 /home/lmr/comfy/director_to_h3_llm.py 04_风格化文案 06_H3prompt --durations 02_分镜增强/分镜清单_enhanced.json`
  - LLM 把中文导演设计转成 H3 三字段（integrated_multimodal_description / overall_soundscape / non_diegetic_music）
  - POV 段（idx%5==0）自动标第一人称；其余第三人称
  - 写回前 enforce_constraints 强制校验（见 LLM 铁律 4）
要点：
  - off-screen voiceover + lips closed（画面内无人声）
  - non_diegetic_music: N/A（BGM 后期叠加）
  - 事实锚点保留（数字/名词在画面描述核对处）
  - **画质锚定词**：imd 必须含导演设计【画质】块的光/材质/景深词；不足自动末尾补默认三件套（绝不插开头——保护风格锁前缀检查）
校验：三字段齐全 + off-screen 约束 + POV/非 POV 标记正确 + 画质锚定词

### 阶段五：生成 + 合成
输入：`prompt_XX.json` + `audio_XX.mp3`
动作：
  1. H3 生成 480P ≤15s（串行，严禁并行；分辨率按平台：短视频=9:16 竖版默认，勿改横版——见踩坑 4）
     **命令**：`python3 submit_accel.py 1 <N> <项目>/06_H3prompt --script <稿子.md>`（自动输出到稿子同级 480P/）
  2. LTX 放大 720P（**花屏/error 时弃用，直接用 480P 合成**——见踩坑 3）
  3. 合成：`python3 compose_final.py <480P目录> <05_TTS语音> <07_成片> --bgm <BGM.mp3> --bgm-volume 0.25`
  4. 字幕烧录（可选）：ASS 底部白字黑描边 → `ffmpeg -vf "ass=subtitles.ass"`（见踩坑 10）
产出：最终成片 + `verify_output.py` 验收报告
校验（verify_output.py，十项）：文件/时长/分辨率/三字段/**画质链 quality_chain（仅提示不 FAIL，保护旧产物）**/风格锁一致/切点不在句中/连贯/信息点/音频对齐；失败段自动重跑（限 2-3 次）

### 发布闸门（不可跳过）
- 产出：成片 + 验收报告 → 展示给用户（MEDIA: 路径）
- 等用户确认 → 才发布
- auto 模式同样必须停

### 产物同步（稿子同级，2026-08-13 用户确认）
- 项目中间产物在 `<稿子目录>/流水线/<项目>/`（01-07 + 480P/720P）
- **最终成片 + 封面必须同步回稿子同级目录**（如 `<稿子目录>/每日新中国b站_<日期>_<slug>_成片.mp4`），与其他单件视频平级
- 同步三件：成片 mp4 + B站封面 + 竖版封面（发布包），命名带日期+slug

## BGM 与局部节奏增强（用户已确认）

- 原则：口播 BGM 是铺底不是卡点；mixkit 322/580 或 pixabay Documentary，音量 0.2-0.33x，fade in/out
- 三层：
  1. 段落节奏对齐（P0）：段边界落 BGM 小节边界 ±0.2s
  2. BGM 时长裁剪（P0）：ffmpeg 裁到成片时长 + fade in 0.5s / out 2s；人声 1.0x + BGM 0.2-0.33x + 音效 1.0x
  3. 局部节奏增强（P1）：高潮段（节奏意图=冲击）比周围更快/更紧/更响——切点更密（2-3镜/5s）、BGM 短暂抬升（0.33x→0.45x）再回落、局部踩拍（±0.05s）
- 严格全程卡点 = 排除
- **⚠️ 分段音量**：amix 默认 normalize 会拉平分段差异；高潮段降 BGM 用 `normalize=true` + 分段 `volume='if(between(t,起,止),0.4,1.0)'`（0.25→0.10），验证用低频段 volumedetect（见踩坑 9）

## 关键路径

- 分镜清单：`/home/lmr/comfy/分镜清单_raw.json` / `分镜清单_enhanced.json`
- 风格化文案：`/home/lmr/comfy/风格化文案/`
- H3 prompt：`/home/lmr/comfy/h3_prompts/`
- 验收报告：`/home/lmr/comfy/verify_report.json`
- ComfyUI 工作流：`E:\AI\Comfyui-WF-2026.8.8\ComfyUI\user\default\workflows\`
- ComfyUI 输出：`E:\...\ComfyUI\output\`（WSL 侧走 powershell.exe 桥接）

## 踩坑记录 → references/2026-08-12-icehouse-pipeline-lessons.md

**上下文指针**：遇到以下任一情况，先读 `references/2026-08-12-icehouse-pipeline-lessons.md`（13 条编号踩坑，2026-08-12 冰室极热项目实战固化）：

| 遇到 | 读编号 |
|------|--------|
| 项目文件放哪 / 产物目录错 | 1 |
| 480P/720P 输出文件名混乱 | 2、3 |
| H3 生成分辨率不对（竖/横） | 4 |
| LTX 放大 400/TypeError | 5 |
| 找不到 H3 输出文件 | 6 |
| 分段切进发布信息 / 改段数后旧文件残留 | 7 |
| 生成 TIMEOUT 卡死 / 队列释放 | 8 |
| BGM 分段音量不生效（amix） | 9 |
| 字幕烧录 / 封面文字 | 10、11 |
| 平台发布（B站/抖音/视频号） | 12、13 |
| 字幕含 % 静默丢失 / ass 滤镜不渲染 | 15 |

（历史踩坑——ui2api 转换/模型名/GPU 节奏/LLM 化/480P 污染/断点续跑——见下方旧段落，仍有效）

### UI→API 转换（ui2api.py）
- 节点端口号必须**整数**（`["120", 0]`，写 `"0"` 字符串 → validate 失败）
- rgthree Label/Bypasser 节点**跳过**（纯 UI 标记，未装 rgthree 时 400）
- rgthree Seed 节点**保留**（提供种子，widgets[0] → seed input）
- **widget/link 优先级**：有 link 的 input 用 link；widget 索引无论有无 link 都消耗一位（防错位）
- 多分支工作流：**只保留目标分支主链路**（SaveVideo 反向 BFS），其余节点全删（防 LoadImage 残留/GGUF 类型错）

### 模型名
- 工作流引用模型名常与实际不符 → 按实际模型列表修正（本机：fl2va_int8_convrot / qwen3vl_nvfp4_awq）
- LoRA 路径**反斜杠子目录**（`minimax_h3\xxx`）不能改正斜杠

### 执行节奏
- TTS 和 H3 生成**共用 GPU 互拖** → 先跑完视频生成，再集中 TTS
- 首个任务偶发 execution_interrupted（模型热加载 + /free 时序）→ 补跑即可
- TTS 批量偶发 CUDA NaN → 分段续跑（跳过已存在文件，从失败段继续）
- 长任务每段 3-4 分钟，107 段约 6 小时，必须后台 + 心跳监控

### LLM 化（2026-08-12 用户纠正后新增）
- **禁止 Python 关键词/模板做创意设计**：导演设计（director_llm）、H3 prompt 转译（director_to_h3_llm）、POV 场景（pov_scene_llm）全部走 LLM
- 9router 返回可能带 `data: [DONE]` SSE 尾缀 → 先截断再 json.loads；deepseek 系 content 可能是 reasoning_content → 取 `content or reasoning_content`
- **请求级关 thinking**：`"thinking": {"type": "disabled"}`（只影响本次调用，不动 9router 全局）
- LLM 输出约束校验不能只靠 prompt：`enforce_constraints` 写回前强制补齐（off-screen/music N/A/paper collage 标记）
- 大小写坑：LLM 可能输出小写 "handmade paper collage" → submit_accel 的 marker 校验用 `"paper collage"` + `.lower()`

### 480P 跨项目污染（2026-08-12 实战踩坑）
- **症状**：480P 里混入旧项目文件（同 pid 名的 shot01-107），拼成片时串内容
- **根因**：submit_accel 拷贝用 `glob(pid*)` 匹配，Windows 输出目录残留旧项目同名文件
- **修复**：只拷本次 prompt_id 的 history 输出（/history/{id} 的 gifs/videos 字段）；兜底按 pid + 最近 10 分钟
- 旧残留隔离到 `480P_旧项目残留/`（不删，红线）
- LOG（generated_480P_test.jsonl）是全局的：重跑某段前先删该段 LOG 记录（否则 SKIP）

### 导演设计 LLM 断点续跑
- `director_llm.py` 的 done 检测看 shotXX.md 是否已存在：**旧模板文件会误判为已完成** → 换 LLM 前先删旧 shotXX.md（保留 00_整体视觉方案.md）
- **deepseek 系模型空 content / 截断（2026-08-18 实测）**：`model=low` 路由到 deepseek-v4-flash 时，长 prompt（SYSTEM_SHOT+台词）的正文常落在响应的 `reasoning` 字段而非 `content`（`content` 为空或仅几十字符，`finish_reason=length`）。director_llm 已加提取：content <60 字符时从 `reasoning` 取最后一个 `【场景】` 起的完整设计块。**但逐段脚本的 done 检测会把 11 字节空壳 shotXX.md 误判为已完成**——重跑前必须删除 ≤60B 的空壳文件，否则永远跳过。整体方案同样可能写出仅含标题的空文件，重跑前删掉 00_整体视觉方案.md

## 项目文件夹规范（用户确认，必须保留）

**铁律：项目根 = 稿子所在目录**（用户 2026-08-12/13 纠正）。480P 输出到**稿子所在目录的 `480P/` 文件夹**（稿子同级），不是任何子目录。每个项目在稿子同目录建独立文件夹（`流水线/<slug>/`）放中间产物，但 **480P 输出始终在稿子同级**：

```
<稿子目录>/（如 .../每日新中国b站/）
├── <稿子>.md                    ← 稿子（唯一锚点）
├── 480P/                        ← H3 生成的分段视频（<slug>_shotXX_....mp4）——稿子同级！
├── 流水线/<slug>/               ← 中间产物（01-07 阶段）
│   ├── 01_分镜/ 02_分镜增强/ 03_口播台词/ 04_风格化文案/
│   ├── 05_TTS语音/ 06_H3prompt/ 07_成片/
│   └── 720P/                    ← LTX 放大（花屏弃用时为空）
```

**输出文件名铁律（用户 2026-08-12/13 纠正）**：所有输出文件必须带项目前缀（如 `icehouse-hyperthermal-event_shot01_00006_.mp4`），防跨项目同名混淆。**根源解决**：改工作流 SaveVideo 的 filename_prefix 注入前缀（`480P/<slug>_<pid>` 相对路径），不是拷贝后改名。

**提交命令（自适应稿子位置，2026-08-13 用户要求）**：
```bash
python3 submit_accel.py <start> <end> <项目>/06_H3prompt --script <稿子.md>
```
- 自动识别稿子路径 → 480P 输出到 `dirname(稿子)/480P/`（稿子同级）
- slug 从稿子文件名提取（去日期前缀和 `-稿.md` 后缀），注入 filename_prefix
- 兼容旧用法：无 `--script` 时回退到 prompt_dir 上一级/480P

规则：
- 阶段号前缀（01_ 02_ ...）保证文件夹按流程排序
- 480P 分段**永不删除**（用户红线），位置 = 稿子同级 480P/
- 每个阶段产物落盘对应文件夹，验收报告同放
- 拼接临时文件（_merged/ _concat.txt）放 05_成片/ 内，不污染其他文件夹

## 工具与脚本（/home/lmr/comfy/）

- `segment_script.py` — 阶段一：文稿分段器（≤70字/15s，句号断句）
- `storyboard_enhancer.py` — 阶段二：分镜增强（4 字段 + 六项自检）
- `director_llm.py` — 阶段三：**LLM 导演设计**（阶段A整体方案 + 阶段B逐段；`--only-scenes` 续跑）
- `pov_scene_llm.py` — 阶段四辅助：LLM 生成 POV 段语义相关场景（替代关键词模板）
- `director_to_h3_llm.py` — 阶段四：**LLM 导演设计 → H3 三字段**（含 enforce_constraints 强制校验）
- `merge_pov_scenes.py` — 阶段四辅助：LLM POV 场景写回 prompt JSON
- `ui2api.py` — UI 工作流 → API prompt 转换器（跳 Label/Bypasser、保留 Seed、widget/link 正确映射）
- `submit_accel.py` — 阶段五：串行生成（powershell 桥接 + 主链路裁剪 + 模型名修正 + **只拷本次 prompt_id 输出** + **`--script <稿子.md>` 自适应 480P 输出位置与文件名前缀**）
- `cleanup_480p.py` — 阶段五辅助：隔离 480P 中旧项目残留（按时间戳，移入 480P_旧项目残留/）
- `verify_output.py` — 阶段五：验收脚本（十项检查 + 报告，含画质链 quality_chain）
- `pipeline_contract.py` — 流水线契约：环节间只传文件（强制）+ 产出落盘标记
- `tts_batch.py` — 阶段三：Index-TTS-2 批量配音（manifest + 声线）
- `compose_final.py` — 阶段五：拼接成片（逐段合并视频+音频 → concat → BGM 叠加）

## 参考

- 能力矩阵：`/home/lmr/comfy/TE_MAN_9技能能力矩阵.md`
- 流程图 V2：`/home/lmr/comfy/script-to-h3-video-流程图-V2.md`
- spec V2：`/home/lmr/comfy/.scratch/script-to-h3-video-skill/spec.md`
- 官方 prompt 结构：h3-prompt-writing skill

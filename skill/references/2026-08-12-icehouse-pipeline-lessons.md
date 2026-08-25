# 2026-08-12 冰室极热事件全流程踩坑（script-to-h3-video 实战）

> 本次 icehouse-20260812 项目（B站+抖音+视频号三平台发布）完整跑通，以下为踩坑与最终方案。
> 引用时按编号定位；每条都已固化到主脚本或本文件，不再重复排查。

## 1. 项目根 = 稿子所在目录（用户纠正，最高优先级）

- **症状**：首次把项目建到 `/home/lmr/comfy/icehouse-20260812/`（comfy 项目根），被用户纠正"你的文稿在哪儿，这一系列的文件就应该在哪个文件夹里边"
- **规则（2026-08-13 最终版）**：
  - 480P 输出 = **稿子所在目录的 `480P/` 文件夹**（稿子同级）
  - 中间产物 = `<稿子目录>/流水线/<slug>/`（01-07 阶段）
  - 最终成片+封面 = 同步回稿子同级
- **落实（submit_accel.py）**：`submit_accel.py <start> <end> <prompt_dir> --script <稿子路径>`
  - 从稿子路径推导：`480P = dirname(稿子)/480P`，`slug` 从稿子文件名提取（去日期前缀和 `-稿.md` 后缀）
  - 工作流 `filename_prefix = 480P/<slug>_<pid>`（相对路径，ComfyUI 输出到 output/480P/）
  - 拷贝到 `<稿子目录>/480P/`（filename 相对 output 根拼 WIN_OUT_ROOT）

## 2. 输出文件名带项目前缀（根源解决，不是拷贝后改名）

- **症状**：不同项目 480P 输出都叫 `shot01_...`，混在一起无法区分
- **规则**：所有输出文件带项目前缀（`icehouse-20260812_shot01_00006_.mp4`）
- **根源解决**：改工作流 SaveVideo 节点的 `filename_prefix` = `video/MiniMax_H3/<SLUG>_<pid>`
  - submit_accel.py `convert_workflow()`：`SLUG` 从项目目录名推断，注入 filename_prefix
  - Windows 输出从源头带前缀，拷贝/下游天然区分
- **双前缀防护**：拷贝时检测 `src_name.startswith(SLUG + "_")` 则不重复加
- **下游兼容**：compose_final.py glob 改为 `*_shot*.mp4` + `shot*.mp4`，用正则 `shot(\d+)` 解析 id

## 3. 720P 花屏弃用，用 480P 合成

- **症状**：LTX 放大 720P 后花屏（shot03 也 error）
- **决定**：用户明确"不到720花屏，先不进行放大了，用480p合成成片加配音和bgm"
- **规则**：720P 放大不可靠时直接用 480P 合成（H3 原生 480×864 竖版）
- **目录**：720P 文件夹仍保留（如 `720P/`），但可空置

## 4. ResolutionSelector 9:16 竖版默认（平台适配关键）

- **症状**：H3 生成 480×864 竖版，以为 bug 去改横版，被用户纠正"不要生成横版"
- **事实**：工作流 `ResolutionSelector` 默认 `9:16 (Portrait Widescreen)`，ImageResizeKJv2 480×832
- **决定**：**短视频平台（B站/抖音/视频号）用竖版 9:16 是正确的**，不要改横版
- **教训**：先确认目标平台格式再判断"bug"；B站专版 README 说横版是旧规范，实际发布竖版 480×864 也通过

## 5. LTX 放大工作流字段名（API 签名必须匹配）

- **症状**：submit 400 `prompt_outputs_failed_validation` 或执行 TypeError
- **根因**：api 图字段名与节点实际签名不一致
- **正确字段**（2026-08-12 实测）：
  - `LTXVChunkFeedForward`：`model` + `chunks` + `dim_threshold`（不是 chunk_size/ffn_chunk_size）
  - `LTXVLoopingSampler`：model/vae/noise/sampler/sigmas/guider/latents + temporal_tile_size/temporal_overlap/guiding_strength/temporal_overlap_cond_strength/cond_image_strength/horizontal_tiles/vertical_tiles/spatial_overlap + **adain_factor**（object_info 不列但必填）+ guiding_start_step/guiding_end_step/last_step
- **排查法**：`/object_info/<NodeType>` 查 required；执行错误看 history 的 `execution_error.exception_message`

## 6. H3 输出路径是 output/Video/MiniMax_H3/（带下划线）

- **事实**：H3 输出在 `ComfyUI/output/Video/MiniMax_H3/`（不是 `output/MiniMaxH3/`——那是旧格式）
- **影响**：upscale_ltx.py 输入路径、LoadVideo annotated 都要用 `Video/MiniMax_H3/... [output]`
- **选文件**：`*{shot_id}*.mp4` 匹配多个时按 mtime 降序选最新（防选到旧项目残留）

## 7. 分段器会切进"发布信息"（需要截断标记）

- **症状**：稿子尾部 `## 发布信息`（标题/分区/标签/封面文字）被当正文切成 shot16/17，TTS 会念"分区：tid=232"
- **修复**：分段前 `md.split('## 发布信息')[0]`；改段数后**清理旧 shotXX.md**（03_口播台词/04_风格化文案/06_H3prompt 都要清，防止旧文件误判为已完成）

## 8. H3 生成 TIMEOUT 卡死 + interrupt 释放队列

- **症状**：某段提交后 status=TIMEOUT（wait_done 900s 超时），但任务实际还在 ComfyUI 队列里跑；脚本误以为失败去等队列，死等
- **处理**：
  1. 查队列 `queue_running` 的 prompt_id —— 若还在跑就是真卡住
  2. `POST /interrupt` 释放队列
  3. 脚本自动恢复继续下一段；被 interrupt 的段**不会自动重跑**，完成后单独补跑（`submit_accel.py N N <prompt_dir>`）
- **LOG 记录**：补跑前确认该段不在 LOG（TIMEOUT 段没写 LOG，可直接补跑）

## 9. amix normalize 之谜（BGM 分段音量被拉平）

- **症状**：高潮段 BGM 想降音量，但 `amix` 默认 `normalize=true` 把输入归一化，分段 volume 差异被拉平（0.25 和 0.08 几乎无差别）
- **关键**：`amix normalize=0` 关闭归一化才保留真实音量差
- **但 normalize=0 后 BGM 相对人声过低**（人声 -20dB，BGM 0.16 只有 -45dB 低频，淹没）——volumedetect 看不出差异
- **最终方案（v4）**：`normalize=true`（默认）+ 高潮段 BGM volume 降 `if(between(t,91,114),0.4,1.0)`（0.25→0.10）→ 听感"介于盖人声和不闻之间"
- **验证**：低频段 `highpass=100,lowpass=300` 测 mean_volume 才是 BGM 特征（v1 -27.1 / v4 -29.5 / v2 -48）
- **用户标准**（2026-08-13）：高潮段 BGM 音量要介于"第一版（盖人声）"和"第二版（几乎无）"之间

## 10. 字幕烧录（ASS 竖版）

- **规格**：底部居中、白字+黑描边、字大、内容完整简练
- **实现**：ASS `PlayResX=480 PlayResY=864`，`Microsoft YaHei` 或 `Noto Sans CJK`，Fontsize 34（480 宽约 14-16 字/行），`BorderStyle=1 Outline=3 Shadow=2`，`Alignment=2`（底部居中），每行 `\N` 断行
- **烧录**：`ffmpeg -i 成片.mp4 -vf "ass=subtitles.ass" -c:v libx264 -preset medium -crf 20 -c:a copy`
- **验证**：抽帧 vision 检查文字完整可读；横版 19 字一行会溢出，需自动缩小字号（fit 到画面 92% 宽）

## 11. 封面文字（PIL 明黄+黑描边）

- **规格**：明黄色 `(255,215,0)` + 黑描边，居中大字，内容简练直击要害
- **实现**：`draw.text(..., fill=YELLOW, stroke_width=size//10, stroke_fill=BLACK)`
- **竖版 736×1312**：两行 96px（"3亿年前大冰期/地球曾突然升温"）
- **横版 1312×736**：单行，自动缩字号 fit 到 92% 宽（19 字 → 68px）
- **验证**：vision 抽帧确认无裁剪/无遮挡

## 12. 平台发布（B站/抖音/视频号）

- **B站**：`sau bilibili upload-video --account diyi --tid 232 --tags "..." --thumbnail <横版封面>`；核验用创作中心 `arc_audits[0].Archive.bvid/title/cover`，封面 SHA-256 与本地一致
- **抖音**：`env -u DISPLAY sau douyin upload-video --headless --thumbnail <竖版封面>`；日志"视频发布成功"+"封面设置完成"
- **视频号**：必须 `xvfb-run -a`（禁 env -u DISPLAY）；`--headed`；cookie 失效先 login（后台+扫码）；核验后台 post/list 截屏确认缩略图
- **搜索索引延迟**：刚发布 10-30 分钟内 B站搜索找不到，用创作中心 API 核验不是搜索

## 13. 同研究重复发布

- 8-11 已发"冰室气候极热事件"（BV1GTui62E6F），8-12 又发"大冰期突然升温"——同一 PNAS 研究两个报道
- **注意**：同一研究不同日期报道可能重复，发布前检查近 7 天已发内容

## 14. 三平台发布实测补充（2026-08-13 显卡猝死事件）

- **B站封面**：用户给的封面可能是任意尺寸（如 1672×941），必须先转标准 1920×1080（PIL 居中裁剪 + LANCZOS）再传 `--thumbnail`；核验用 biliup `list --pubed` / `show <BV>` 的 `archive.cover` SHA-256 与本地比对
- **抖音 AI 声明**：`--declaration "内容由AI生成"`。铁律：选项原文必须先探针（上传视频到发布页 → 点"请选择自主声明" → 抓 `.semi-radio` 文本，不点发布），不能凭记忆编造。当前实测选项：内容由AI生成 / 内容为个人观点或见解 / 内容为转载信息 / 内容含营销推广信息 / 虚构演绎，仅供娱乐 / 无需添加自主声明。探针脚本 `/home/lmr/comfy/probe_douyin_declaration.py`
- **视频号登录**：cookie 失效时走 `xvfb-run -a sau tencent login`；若遇二维码截图失败/ProcessSingleton/扫码超时，读 douyin-upload skill 的 `references/tencent-login-qrcode-troubleshooting.md`（单一事实源，不在此复制）
- **视频号发布**：`xvfb-run -a sau tencent upload-video ... --headed`（禁 env -u DISPLAY）；发布后进后台 post/list 核验，页面有两个 body 用 `.first`
- **发布核验**：CLI exit 0 + "发布成功"日志 ≠ 已公开；B站看 `had_passed=true` + 封面 SHA，抖音看作品管理列表，视频号看后台状态（原创审核中=已提交）

## 16. 字幕时间轴偏移（ass= 滤镜 bug）与行宽溢出（2026-08-25 AI半年报实测）

- **症状**：`ass=` 滤镜烧录后字幕整体晚约 1 段（8s），画面已切到下一段但字幕还显示上一段内容；且整段台词单行渲染（25-58 字/650-1500px）大幅超出 480px 画面被裁切。
- **根因**：
  1. **行宽**：ASS 单行不自动换行，长句整行溢出画面 → 字幕"出画面"
  2. **ass= 滤镜时间偏移**：ffmpeg 的 `ass=` 滤镜有字幕时间基准 bug，字幕整体滞后约 1 段
- **修复**：
  1. 语义断行：按标点切短语再合并到 ≤14 字/行，最大行宽 ≤308px（画面 480 宽 - 边距）
  2. **禁用 `ass=` 滤镜，改用 `subtitles=xxx.srt`**（SRT + force_style），时间轴精确对齐
  3. 裁剪 TTS 尾部静音（silencedetect 定位说话终点），视频段裁剪到说话长度，字幕只在说话区间显示
- **验证铁律（每条字幕版都必须做，不能只看 rc=0）**：
  1. **行宽检查**：每行字数×字号 ≤ 画面宽度-边距（脚本算）
  2. **时间轴抽帧**：从字幕文件取 3+ 采样点（段首/段中/段尾），`ffmpeg -i video -ss T -frames:v 1` 精确 seek（-ss 在 -i 后），OCR/视觉比对"该时间点应显示哪段字幕"——必须匹配
  3. **音频-字幕对齐**：字幕显示区间 = 实际说话区间
- **字幕区域约束（用户 2026-08-25 定稿标准）**：字幕只能在屏幕下三分之一内（竖版 864px → y∈[576,864]）。**定稿参数：字号 9px、描边 1.5、阴影 0.3、白字黑边、底部居中 MarginV=40、每行 ≤20 字语义断行、最多 5 行、块高 ≤140px（限 288）、行宽 ≤180px（限 450）**。烧录：`subtitles=xxx.srt:force_style='FontName=Noto Sans CJK SC,FontSize=9,...,MarginV=40'`。用户要求以此状态为基准自检。

## 15. 字幕/文字烧录 % 陷阱（2026-08-16 digital-rmb 实测）

- **症状**：drawtext 字幕含 ASCII `%`（如 "176%"、"100亿"）时，该条 drawtext 整条静默不渲染，仅报 `Stray % near ...` 警告且 rc=0。`ass=` 滤镜对中文路径/超长文本同样可能静默失败（整片无字幕但无报错）。
- **根因**：drawtext 的 `text` / `textfile` 内容会做 expand（`%` 是格式化符），`%` 后跟字母/数字时解析出错丢弃该滤镜。
- **修复**：文本内 ASCII `%` → 全角 `％`（U+FF05），警告消失、字幕正常。`%%` 转义无效（仍报警告）。
- **规避**：`ass=` 滤镜（libass）对复杂场景不稳，优先用 drawtext + `textfile` 逐条 enable；命令行转义地狱（`\n` 换行会失效）→ 用 textfile 多行，绕开 `text='...'` 转义。
- **验证铁律**：烧录后必须抽帧 + vision 确认字幕真的出现（不能只看 rc=0），尤其在文本含数字/百分号/叹号的段落。
- **排版**：480×864 竖版，字号 24，每行≤15字语义断行（按句读切、不留单字行），多行块底部锚定 y=h-55-block_h，line_spacing=8。

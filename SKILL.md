---
name: workbuddy-watermark-remover
description: 去除 WorkBuddy/ImageGen 生成图右下角固定的「AI生成 WORKBUDDY」角标。当用户说「去水印」「去掉右下角那个角标」「把 AI生成 的标去掉」「图片上有 WORKBUDDY 水印帮我弄掉」「批量清理生成图的角标」「watermark removal」时使用。只针对位置尺寸固定的平台角标，采用已知 alpha 反混合擦除，画布尺寸不变、原图不动。
version: 1.0.1
display_name: WorkBuddy 去水印
display_name_en: WorkBuddy Watermark Remover
description_zh: 去除 WorkBuddy/ImageGen 生成图右下角固定的「AI生成 WORKBUDDY」角标。当用户说「去水印」「去掉右下角那个角标」「把 AI生成 的标去掉」「图片上有 WORKBUDDY 水印帮我弄掉」「批量清理生成图的角标」时使用。只针对位置尺寸固定的平台角标，采用已知 alpha 反混合擦除，画布尺寸不变、原图不动。
description_en: Remove the fixed "AI-generated / WORKBUDDY" badge stamped in the bottom-right corner of WorkBuddy / ImageGen outputs. Use when the user asks to remove watermarks, erase the corner badge, clean the WORKBUDDY mark, or batch-clean generated images. Uses known-alpha unmixing, so the canvas size never changes and the original file is never modified. Only applies to fixed-position platform badges.
author: Git小子
agent_created: true
---

# WorkBuddy 去水印

## 用途

擦除 WorkBuddy / ImageGen 出图时自动叠加在**右下角**的「AI生成 WORKBUDDY」角标。

做法不是"涂抹"或"模糊"，而是**已知 alpha 反混合**：预先从纯色底图上反解出水印每个像素的透明度（存为 `assets/wm_alpha_ref.png`），再对目标图逐像素反算，把水印"揭掉"，底下的真实画面自然回来。

效果：画布尺寸不变、无补丁痕迹、暗底亮底均适用、单张约 2.4 秒、零第三方依赖（纯 Python 标准库）。

## 何时使用

用户要求处理**平台固定角标**时使用：

- "去水印""去掉右下角那个标""AI生成 那行字去掉"
- "这张图右下角有个 WORKBUDDY 的标志"
- "批量把生成图的角标都清掉"

**不适用**（必须先看再决定）：

- 公众号/第三方账号自己叠的白色文字水印 → 蒙版对不上，改走"裁切"或补背景
- 水印在画面中间、或位置不固定 → 同上
- 非 PNG 格式（JPG/WebP）→ 先转成 PNG 再处理

## 快速开始

脚本目录：本 skill 下的 `scripts/`。

```bash
# 单张（推荐，默认 auto：优先擦除，不成就改裁切）
python scripts/clean_image.py 图片.png

# 强制擦除（画布不变）
python scripts/clean_image.py 图片.png --mode erase

# 强制裁掉底部水印条
python scripts/clean_image.py 图片.png --mode crop

# 整个目录批量
python scripts/clean_image.py 某目录/

# 低置信度也强制处理
python scripts/clean_image.py 图片.png --force
```

输出命名：擦除为 `原名_clean.png`，裁切为 `原名_cropped.png`。**原图一律不动**。

## 参数

| 参数 | 说明 |
|------|------|
| `--mode auto` | 默认。置信度足够就擦除，否则降级裁切 |
| `--mode erase` | 反混合擦除，画布尺寸不变 |
| `--mode crop` | 切掉底部含水印的横条（默认再额外多切 8px） |
| `--safety N` | crop 模式的额外余量，默认 8 |
| `--force` | 置信度低于阈值也照样处理 |

## 操作流程

1. **确认水印类型**：看图右下角。若是「AI生成 / WORKBUDDY」或同类平台角标，继续；若是他人账号的公众号水印，跳到"不适用时的替代路线"。
2. **执行**：`python scripts/clean_image.py <图片>`。
3. **读日志里的置信度**：
   - `> 6` 正常，擦除完成
   - `3 ~ 6` 痕迹偏弱，auto 会降级裁切
   - `< 3` 视为未检出，自动跳过（`--force` 可强制）
   - 实测真水印通常 36~120，无水印图约 −0.1~0.5，区分度很高
4. **验收**：放大右下角核对，别只信日志。

```python
import sys; sys.path.insert(0, 'scripts')
from clean_image import zoom
zoom('结果_clean.png', 宽-240, 高-160, 240, 160, 4, '核对图.png')
```

5. **交付**：给出输出路径，并说明原图未改动。

## 技术前提

蒙版锚定在**右下角**，取图右下 144×84 像素窗口。已实测三种尺寸（1024×1024、1536×1024、1024×1536），水印均为**固定 111×51 像素、距右/底各 10px**——即水印尺寸不随图片缩放，同一份蒙版通用。

因此：

- 任何尺寸 ≥ 148px 的图都能处理
- 不需要按图片大小换算比例
- 不需要事先知道水印文字内容

## 蒙版失效时如何重建

平台若改水印样式（字号、位置、新增图案），旧蒙版立即失效，表现为置信度骤降到 0 附近。此时：

1. 用同一提示词生成**两张纯色/极简背景图**，例如：
   `Flat neutral gray studio gradient background only, completely empty, minimal, no subject, no text.`
2. 重建蒙版：

```bash
python scripts/rebuild_mask.py 灰底图1.png 灰底图2.png
```

脚本覆盖 `assets/wm_alpha_ref.png`，并打印 alpha 峰值（正常约 0.55）与非零占比（正常约 24%）。

3. 拿一张旧图复测，确认置信度回到 30 以上。

## 不适用时的替代路线

| 情况 | 做法 |
|------|------|
| 水印靠近底边、且底部本就有留白 | `--mode crop` 直接切，零瑕疵 |
| 构图不能裁 | 只能补背景，效果必有代价，需向用户说明 |
| 需要任意位置的 AI 修复 | 本 skill 不覆盖 |

判断口诀：**水印位置固定 → 反混合（完美）；位置不固定 → 只能裁或补。**

## 已知限制

- 仅支持 PNG（8bit、非隔行）。JPG/WebP 需先转 PNG。
- 假设水印为纯白叠加；若实际为浅灰，擦除会略偏暗。
- `locate_wm.py` 可自动找水印包围盒，但**只在纯色底图上可靠**，复杂画面会被高光干扰；生产流程不要依赖它，用固定锚点 + 相关度打分。
- 重建蒙版后务必复测，别直接批量跑。
- 合规：仅用于本地整理与私用文件。对外发布 AI 生成内容须遵守《人工智能生成合成内容标识办法》，不得以去标识方式冒充人工创作。

## 文件说明

```
workbuddy-watermark-remover/
├── SKILL.md
├── assets/
│   └── wm_alpha_ref.png      # 144×84 水印透明度蒙版（锚定右下角）
└── scripts/
    ├── clean_image.py        # 主入口：擦除 / 裁切 / 批量 / 放大核对
    ├── crop_png.py           # 纯标准库 PNG 读写（五种行过滤器）
    ├── analyze_wm.py         # 从纯底图反解 alpha（平面拟合 + 最小二乘）
    ├── rebuild_mask.py       # 用两张纯底图重建蒙版
    └── locate_wm.py          # 自动定位水印框（诊断用，勿用于生产）
```

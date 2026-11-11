"""Render the verified M19 architecture as two editable SVGs and one vector PDF.

Documentation-only dependency: reportlab. No application services or private
project data are read. Run with --output-dir output/pdf/gamecrafter-architecture.
Chinese font paths can be overridden for another workstation.
"""

from __future__ import annotations

import argparse
import html
import math
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

W, H = 1840, 1280
INK, MUTED, LINE = "#173244", "#516878", "#728b9b"
PALETTES = {
    "tool": ("#edf4fb", "#afc6d9", "#205a85"),
    "model": ("#e9f6f2", "#91cbbf", "#116c60"),
    "human": ("#fff5de", "#e0bd70", "#886018"),
    "data": ("#f4f6f8", "#c7d3dc", "#405e74"),
    "external": ("#fcf0ed", "#e0b8ae", "#935b4d"),
}


def width(text: str, size: float, bold: bool = False) -> float:
    return pdfmetrics.stringWidth(text, "YHB" if bold else "YH", size)


class Diagram:
    def __init__(self, pdf: canvas.Canvas, title: str, page: int):
        self.pdf = pdf
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{html.escape(title)}</title>',
            '<desc id="desc">GameCrafter M19 current implementation, verified against '
            "the source code on 2026-11-11. Planned v3 features are explicitly separated.</desc>",
        ]
        self.pdf.saveState()
        self.pdf.scale(0.65, 0.65)
        self.rect(0, 0, W, H, "#ffffff", "#ffffff", radius=0)
        self.text(72, 63, "GAMECRAFTER / PRODUCT & AGENT ENGINEERING", 17, "#116c60", True)
        self.text(72, 119, title, 43, INK, True)
        self.text(
            72, 159, "现有 M19 实现 · 已包含 creative-evidence-v11 边界修复 · 非公开上线认证", 20
        )
        self.path([(72, 193), (1768, 193)], "#cdd9e2", 1)
        self.text(
            72,
            1240,
            "依据：docs/architecture/system-architecture.md 与实际 Python / React 代码",
            16,
        )
        self.text(1768, 1240, f"2026-11-11  |  {page} / 2", 16, anchor="end")

    def rect(self, x, y, w, h, fill, stroke, radius=12, dash=False):
        assert x >= 0 and y >= 0 and x + w <= W and y + h <= H
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"'
            + (' stroke-dasharray="7 5"' if dash else "")
            + "/>"
        )
        self.pdf.setFillColor(HexColor(fill))
        self.pdf.setStrokeColor(HexColor(stroke))
        self.pdf.setLineWidth(1.5)
        self.pdf.setDash([7, 5] if dash else [])
        self.pdf.roundRect(x, H - y - h, w, h, radius, fill=1, stroke=1)
        self.pdf.setDash([])

    def text(self, x, y, text, size=20, color=MUTED, bold=False, anchor="start"):
        measured = width(text, size, bold)
        left = x if anchor == "start" else x - measured / 2 if anchor == "middle" else x - measured
        assert left >= 0 and left + measured <= W, (text, left, measured)
        self.parts.append(
            f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
            f'font-family="Microsoft YaHei,Noto Sans CJK SC,Arial,sans-serif" '
            f'font-weight="{700 if bold else 400}" text-anchor="{anchor}">'
            f"{html.escape(text)}</text>"
        )
        self.pdf.setFillColor(HexColor(color))
        self.pdf.setFont("YHB" if bold else "YH", size)
        self.pdf.drawString(left, H - y, text)

    def path(self, points, color=LINE, thickness=2.2, dash=False):
        values = " ".join(f"{x},{y}" for x, y in points)
        self.parts.append(
            f'<polyline points="{values}" fill="none" stroke="{color}" stroke-width="{thickness}"'
            + (' stroke-dasharray="7 5"' if dash else "")
            + "/>"
        )
        path = self.pdf.beginPath()
        path.moveTo(points[0][0], H - points[0][1])
        for x, y in points[1:]:
            path.lineTo(x, H - y)
        self.pdf.setStrokeColor(HexColor(color))
        self.pdf.setLineWidth(thickness)
        self.pdf.setDash([7, 5] if dash else [])
        self.pdf.drawPath(path, stroke=1, fill=0)
        self.pdf.setDash([])

    def arrow(self, points, color=LINE, both=False, dash=False):
        self.path(points, color, dash=dash)
        ends = [(points[-2], points[-1])]
        if both:
            ends.append((points[1], points[0]))
        for (x0, y0), (x, y) in ends:
            theta = math.atan2(y - y0, x - x0)
            vertices = [(x, y)] + [
                (
                    x - 10 * math.cos(theta) + sign * 4.5 * math.sin(theta),
                    y - 10 * math.sin(theta) - sign * 4.5 * math.cos(theta),
                )
                for sign in (-1, 1)
            ]
            self.parts.append(
                '<polygon points="'
                + " ".join(f"{a:.2f},{b:.2f}" for a, b in vertices)
                + f'" fill="{color}"/>'
            )
            p = self.pdf.beginPath()
            p.moveTo(vertices[0][0], H - vertices[0][1])
            for a, b in vertices[1:]:
                p.lineTo(a, H - b)
            p.close()
            self.pdf.setFillColor(HexColor(color))
            self.pdf.drawPath(p, fill=1, stroke=0)

    def label(self, x, y, text, size=17, color=MUTED):
        length = width(text, size)
        self.rect(x - length / 2 - 9, y - size - 3, length + 18, size + 9, "#ffffff", "#ffffff", 3)
        self.text(x, y, text, size, color, anchor="middle")

    def box(self, x, y, w, h, title, lines, kind="tool", size=25, body=20):
        fill, stroke, color = PALETTES[kind]
        self.rect(x, y, w, h, fill, stroke)
        while width(title, size, True) > w - 36 and size > 18:
            size -= 1
        assert width(title, size, True) <= w - 36, title
        self.text(x + 18, y + 35, title, size, color, True)
        for i, line in enumerate(lines):
            assert width(line, body) <= w - 36, (title, line)
            baseline = y + 66 + i * (body + 9)
            assert baseline <= y + h - 12, (title, baseline)
            self.text(x + 18, baseline, line, body)

    def section(self, y, label):
        self.text(72, y, label, 23, INK, True)

    def finish(self, path: Path):
        self.parts.append("</svg>")
        path.write_text("\n".join(self.parts) + "\n", encoding="utf-8")
        self.pdf.restoreState()
        self.pdf.showPage()


def runtime(pdf, destination):
    d = Diagram(pdf, "系统运行架构：界面、执行与数据边界", 1)
    d.section(230, "01 交互层  /  Interface and API")
    d.box(
        72, 255, 250, 125, "用户与负责人", ["确认事实与选题", "核对当前稿并终审"], "human", 25, 20
    )
    d.box(
        392,
        255,
        575,
        125,
        "React / TypeScript / Vite",
        ["中文默认、英文切换、五步制作路线", "提交状态、问题定位、逐镜编辑、版本回看"],
        size=27,
    )
    d.box(
        1040,
        255,
        728,
        125,
        "FastAPI / Pydantic",
        [
            "输入与项目边界校验、幂等提交、只读状态接口",
            "认证与 RBAC 能力可用；录制使用本地单用户模式",
        ],
        size=27,
    )
    d.arrow([(322, 318), (392, 318)], both=True)
    d.arrow([(967, 318), (1040, 318)], both=True)
    d.arrow([(1404, 380), (1404, 424), (52, 424), (52, 582), (72, 582)], both=True)
    d.label(1000, 429, "命令入队 / 读取进度；前端轮询与部分 SSE")
    d.section(476, "02 执行与持久化  /  Modular Python backend")
    d.box(
        72,
        500,
        480,
        165,
        "PostgreSQL 17",
        [
            "业务实体、证据引用、知识快照",
            "持久任务队列、创作阶段与脚本版本",
            "审核决定、调用用量与审计记录",
        ],
        "data",
        27,
    )
    d.box(
        680,
        500,
        480,
        165,
        "共享 Python Worker",
        [
            "领取带尝试编号的任务租约",
            "心跳续期、分阶段处理与结果验证",
            "阶段缓存与原子保存；拒绝迟到写入",
        ],
        size=27,
    )
    d.box(
        1288,
        500,
        480,
        165,
        "Ollama 本地推理",
        [
            "提取 / 预审 / 策划 / 写作 / 质检",
            "Schema 约束、独立上下文、有界调用",
            "同一模型可承担多个角色，无云端回退",
        ],
        "model",
        27,
    )
    d.arrow([(552, 565), (680, 565)], both=True)
    d.label(616, 549, "租约 / 状态", 16)
    d.arrow([(1160, 565), (1288, 565)], both=True)
    d.label(1224, 549, "结构化调用", 16)
    d.box(
        72,
        733,
        480,
        125,
        "内容寻址对象存储",
        ["原始页面、规范化文本与导入文件", "数据库保存对象键及哈希，不混作事实"],
        "data",
        25,
    )
    d.box(
        680,
        733,
        480,
        150,
        "确定性业务工具",
        [
            "来源采集 / 趋势清洗匹配 / GDD 整理",
            "来源异步；趋势与 GDD 由 API 调用",
            "HTTP 优先；必要时受限浏览器回退",
        ],
        size=25,
    )
    d.box(
        1288,
        733,
        480,
        125,
        "外部资料：不可信输入",
        ["明确的官方页 / 可选本地文件 / 趋势", "来源地址、时间、地区与版本必须保留"],
        "external",
        25,
    )
    d.path([(312, 665), (312, 733)])
    d.arrow([(920, 665), (920, 733)], both=True)
    d.arrow([(1768, 318), (1806, 318), (1806, 697), (1090, 697), (1090, 733)])
    d.label(1490, 702, "趋势 / GDD：API 同步调用", 17)
    d.arrow([(680, 795), (552, 795)])
    d.label(616, 780, "保全来源", 16)
    d.arrow([(1160, 795), (1288, 795)], both=True)
    d.label(1224, 780, "受控访问", 16)
    d.rect(72, 899, 1696, 131, "#f4f7fa", "#c7d3dc")
    d.text(92, 933, "Harness = 模型之外的工作流控制层", 23, INK, True)
    for x, title, detail in [
        (92, "提交安全", "输入校验 · 项目边界 · 幂等"),
        (650, "执行安全", "租约心跳 · 取消 · 限次重试 · 过期拒写"),
        (1230, "交付安全", "快照与版本绑定 · 终审守卫 · 审计"),
    ]:
        d.text(x, 969, title, 20, INK, True)
        d.text(x, 1001, detail, 19)
    d.text(
        72,
        1073,
        "技术定位：Python 模块化单体 + 数据库持久队列；5 个模型职责，不是 5 个独立部署服务。",
        22,
        INK,
    )
    d.rect(72, 1110, 1696, 88, "#fffaed", "#d9ba78", dash=True)
    d.text(92, 1143, "规划，不计为当前能力", 22, "#886018", True)
    d.text(
        92,
        1177,
        "任意游戏名 → 自动发现官方来源 → 先比较 1-3 个营销方向。当前 M19 仍含旧案例入口。",
        21,
    )
    d.finish(destination / "gamecrafter-runtime.svg")


def workflow(pdf, destination):
    d = Diagram(pdf, "业务逻辑与 Agent 协作：从证据到交付", 2)
    legend_x = 72
    for label, kind in [
        ("确定性工具", "tool"),
        ("模型职责", "model"),
        ("人工关口", "human"),
        ("版本化数据", "data"),
    ]:
        d.rect(legend_x, 213, 16, 16, PALETTES[kind][0], PALETTES[kind][1], 3)
        d.text(legend_x + 26, 228, label, 18)
        legend_x += 205
    d.text(1768, 228, "箭头表示数据与控制依赖，不是自由聊天", 18, anchor="end")
    d.section(281, "01 资料变成可用事实")
    positions = [72, 356, 640, 924, 1208, 1492]
    first = [
        ("明确输入", ["官方页面 / 本地资料", "不等于内部 GDD"], "external"),
        ("来源与溯源工具", ["受控采集、保全证据", "URL / 时间 / 内容哈希"], "tool"),
        ("Knowledge Curator", ["模型提取候选事实", "精确引文另做校验"], "model"),
        ("Knowledge Reviewer", ["独立模型预审建议", "无权代替人工批准"], "model"),
        ("H1 人工知识审核", ["确认 / 修改 / 拒绝", "处理重复与冲突"], "human"),
        ("冻结知识快照", ["已审核值与证据绑定", "实体 / 地区 / 版本"], "data"),
    ]
    for x, (title, lines, kind) in zip(positions, first, strict=True):
        d.box(x, 305, 254, 125, title, lines, kind, 22, 17)
    for a, b in zip(positions[:-1], positions[1:], strict=True):
        d.arrow([(a + 254, 368), (b, 368)])
    d.arrow([(1619, 430), (1619, 465), (740, 465), (740, 535), (565, 535), (565, 550)])
    d.label(1110, 470, "绑定不可变知识版本与营销任务规格", 18)
    d.section(521, "02 形成营销建议与选题  /  平台、市场、时长固定")
    second_x = [72, 425, 778, 1131, 1484]
    second = [
        ("趋势工具", ["RSS / GDELT / 可选 YouTube", "手动 TikTok 观察；不伪造热度"], "tool"),
        ("可解释话题匹配", ["清洗、去重、时间与关键词", "匹配分不是效果预测"], "tool"),
        (
            "Campaign Strategist",
            ["中文方向 / 理由 / 英语开场", "拍摄步骤 / 风险 / 验证计划"],
            "model",
        ),
        ("Quality Critic", ["独立策划检查", "阻断稿保留，但不供写作"], "model"),
        ("H2 人工选题", ["可在策划前后确认", "保存选择与理由"], "human"),
    ]
    for x, (title, lines, kind) in zip(second_x, second, strict=True):
        d.box(x, 550, 280, 125, title, lines, kind, 22, 17)
    for a, b in zip(second_x[:-1], second_x[1:], strict=True):
        d.arrow([(a + 280, 613), (b, 613)])
    d.arrow([(565, 675), (565, 713), (1624, 713), (1624, 675)])
    d.label(1050, 718, "也可直接确认匹配话题；不强制采纳模型策划", 18)
    d.arrow([(1764, 640), (1794, 640), (1794, 778), (52, 778), (52, 917), (72, 917)])
    d.label(1100, 783, "必需：已批准选题 + 事实；可选：同一选题下通过检查的策划", 18)
    d.section(827, "03 创作、复核与交付")
    third = [
        ("Script Writer", ["五镜英语稿 / 按问题修订", "口播 / 字幕 / 画面 / 引用"], "model"),
        ("Quality Critic", ["逐段支持性判断与理由", "模型仍可能误报或漏报"], "model"),
        ("确定性质量检查", ["覆盖与引文 / Schema / 引用", "语速与时长 / 当前版本"], "tool"),
        ("H3 人工终审", ["事实、表达与素材权利", "批准只对当前检查版本有效"], "human"),
        ("准确版本导出", ["Markdown / JSON", "脚本与事实引用可回查"], "data"),
    ]
    for x, (title, lines, kind) in zip(second_x, third, strict=True):
        d.box(x, 854, 280, 125, title, lines, kind, 22, 17)
    for a, b in zip(second_x[:-1], second_x[1:], strict=True):
        d.arrow([(a + 280, 917), (b, 917)])
    d.arrow([(918, 979), (918, 1034), (212, 1034), (212, 979)], "#a67626")
    d.path([(1271, 979), (1271, 1034), (918, 1034)], "#a67626")
    d.label(700, 1039, "有阻断或被拒：限次修订 / 人工编辑 → 新版本 → 重评", 18, "#886018")
    d.rect(72, 1087, 1696, 66, "#edf7f4", "#acd0c6")
    d.text(92, 1114, "v11 输入边界", 21, "#116c60", True)
    d.text(
        272,
        1114,
        "策划、写作与创作评审只使用已批准事实值；完整原文留在追溯层，不扩大批准范围。",
        20,
    )
    d.text(92, 1140, "这不是事实正确率保证。覆盖检查、模型判断和负责人终审是不同关口。", 18)
    d.text(
        72,
        1194,
        "Quality Critic 虽出现两次，仍是同一职责的独立调用。"
        "5 个模型角色可共用本机模型；无自主发布或在线自学习。",
        19,
        INK,
    )
    d.finish(destination / "gamecrafter-workflow.svg")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("output/pdf/gamecrafter-architecture")
    )
    parser.add_argument("--font", default="C:/Windows/Fonts/msyh.ttc")
    parser.add_argument("--bold-font", default="C:/Windows/Fonts/msyhbd.ttc")
    args = parser.parse_args()
    pdfmetrics.registerFont(TTFont("YH", args.font))
    pdfmetrics.registerFont(TTFont("YHB", args.bold_font))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = args.output_dir / "GameCrafter_技术逻辑架构.pdf"
    pdf = canvas.Canvas(str(pdf_path), pagesize=(W * 0.65, H * 0.65))
    pdf.setTitle("GameCrafter 技术逻辑架构 - 现有 M19 实现")
    pdf.setAuthor("GameCrafter / Wenqi77Zhang")
    pdf.setSubject(
        "Runtime architecture and evidence-constrained agent workflow; v3 plans separated"
    )
    runtime(pdf, args.output_dir)
    workflow(pdf, args.output_dir)
    pdf.save()
    print(pdf_path.resolve())


if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# 分享前自检：扫出包里的个人信息
#
# 用法:
#   bash scripts/pii_scan.sh                 # 扫本 skill 根目录
#   bash scripts/pii_scan.sh <目录>          # 扫指定目录（例如解压后的分享包）
#
# 个人关键词从 assets/pii_patterns.txt 读（每行一个正则，忽略空行与 # 开头的注释）。
# 那个文件放自己的姓名/手机/城市/公司名，**不要随包发出去**。
#
# 退出码: 0=干净  1=有命中
set -uo pipefail

TARGET="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
HERE="$(cd "$(dirname "$0")" && pwd)"
PATFILE="$HERE/../assets/pii_patterns.txt"

echo "扫描目录: $TARGET"
echo ""

# ---- 通用格式规则（跟具体人无关，任何人分享前都该过一遍）----
COMMON='1[3-9][0-9]{9}|[0-9]{3}-[0-9]{4}-[0-9]{4}|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(com|cn|net|org)|/Users/[a-zA-Z0-9._-]+|/home/[a-zA-Z0-9._-]+|C:\\\\Users\\\\[a-zA-Z0-9._-]+|wxid_|\bwx[0-9a-f]{10,}\b'

# ---- 个人关键词（可选）----
if [ -f "$PATFILE" ]; then
  # 去掉注释行与空行，用 | 连接
  CUSTOM="$(grep -vE '^\s*(#|$)' "$PATFILE" | paste -sd '|' -)"
  PAT="$COMMON${CUSTOM:+|$CUSTOM}"
  echo "个人关键词: 已从 assets/pii_patterns.txt 载入"
else
  PAT="$COMMON"
  echo "个人关键词: 未找到 assets/pii_patterns.txt —— 只跑通用格式规则"
  echo "            （建议先 cp assets/pii_patterns.example.txt assets/pii_patterns.txt 并填上自己的信息）"
fi
echo ""

HITS="$(grep -rInE "$PAT" "$TARGET" 2>/dev/null \
  | grep -v '/\.git/' \
  | grep -v 'pii_patterns.txt' \
  | grep -v 'pii_patterns.example.txt' \
  | grep -v 'pii_scan.sh' \
  | grep -v '__pycache__' \
  || true)"

if [ -z "$HITS" ]; then
  echo "✅ 未发现个人信息"
  exit 0
fi

echo "⚠️  命中以下内容，逐条确认是不是个人信息："
echo ""
echo "$HITS"
echo ""
echo "提示：命中不一定是泄漏 ——"
echo "  · 规则文档里讲「不要包含绝对路径」属于**规则本身**，可以留"
echo "  · 出现真实姓名 / 手机 / 邮箱 / 本人城市 / 本人简历数字 → **必须改**"
exit 1

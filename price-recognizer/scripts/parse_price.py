#!/usr/bin/env python3
"""价格字符串解析与算术校验工具。

用法:
    python parse_price.py "¥1,299.00"          # 归一化价格文本 -> 1299.00
    python parse_price.py "1万2" "89块9"        # 支持中文混合写法
    python parse_price.py --check 95.00 0.00 6.00 89.00
        # 校验: 实付款 = 商品金额 + 运费 - 优惠, 与图中实付金额比对
    python parse_price.py --eval "95 + 0 - 6 == 89"
        # 直接求值自定义算式(仅允许数字和 + - * / ( ) . = 空格)
"""

import argparse
import re
import sys

DIGIT_MAP = {
    "零": 0, "〇": 0, "一": 1, "壹": 1, "二": 2, "贰": 2, "两": 2, "三": 3, "叁": 3,
    "四": 4, "肆": 4, "五": 5, "伍": 5, "六": 6, "陆": 6, "七": 7, "柒": 7,
    "八": 8, "捌": 8, "九": 9, "玖": 9,
}
UNIT_CHARS = "十拾百佰千仟"
CN_DIGIT_CHARS = "".join(DIGIT_MAP.keys())
CURRENCY_CHARS = r"¥￥$＄元圆RMB|rmb,，\s"


def cn_to_int(s: str) -> int:
    """中文/阿拉伯混合数字(含单位 十百千万)转整数。"""
    s = (s or "").strip()
    if not s:
        return 0
    if s.isdigit():
        return int(s)

    # 万 位拆分: "十二万五千" -> 120000 + 5000; "十二万五" -> 12.5万
    for wan in ("万", "萬"):
        if wan in s:
            head, _, tail = s.partition(wan)
            base = cn_to_int(head) if head else 0
            if not tail:
                return base * 10000
            if any(u in tail for u in UNIT_CHARS):
                return base * 10000 + cn_to_int(tail)
            # 纯数字尾巴: "万五" -> 5000, "万五八" -> 5800
            digits = [DIGIT_MAP[c] for c in tail if c in DIGIT_MAP]
            if not digits:
                return base * 10000
            val = 0
            for d in digits:
                val = val * 10 + d
            return base * 10000 + val * (10 ** max(0, 4 - len(digits)))

    total = section = num = 0
    for ch in s:
        if ch in DIGIT_MAP:
            num = DIGIT_MAP[ch]
        elif ch in UNIT_CHARS:
            unit = {"十": 10, "拾": 10, "百": 100, "佰": 100, "千": 1000, "仟": 1000}[ch]
            section += (num if num else 1) * unit
            num = 0
    return total + section + num


def parse_chinese_number(s: str) -> float:
    """中文数字金额(元为单位), 支持 角/分 与 '块X' 小数写法。"""
    s = re.sub(r"[元圆]", "", s)

    # "玖角" / "玖角五分" 结尾
    m = re.match(rf"^(.*?)([{CN_DIGIT_CHARS}])角(?:([{CN_DIGIT_CHARS}])分?)?$", s)
    if m:
        yuan = cn_to_int(m.group(1)) if m.group(1) else 0
        jiao = DIGIT_MAP[m.group(2)]
        fen = DIGIT_MAP[m.group(3)] if m.group(3) else 0
        return yuan + jiao * 0.1 + fen * 0.01

    # "一百二十九块九" / "十二点五"
    m = re.match(rf"^(.*?)[块点](\d+|[{CN_DIGIT_CHARS}]+)$", s)
    if m and m.group(2):
        yuan = cn_to_int(m.group(1)) if m.group(1) else 0
        tail = m.group(2)
        digits = [int(c) if c.isdigit() else DIGIT_MAP[c] for c in tail]
        frac = 0
        for d in digits:
            frac = frac * 10 + d
        return yuan + frac / (10 ** len(digits))

    return float(cn_to_int(s))


def parse_price(text: str) -> float:
    """把各种价格写法归一化为浮点数(元)。失败抛 ValueError。"""
    s = str(text).strip()
    if not s:
        raise ValueError("空字符串")

    s_clean = re.sub(rf"[{CURRENCY_CHARS}]", "", s)

    # 纯阿拉伯数字(含小数)
    if re.fullmatch(r"\d+(?:\.\d+)?", s_clean):
        return float(s_clean)

    # "89块9" / "12块05"
    m = re.fullmatch(r"(\d+)[块点](\d+)", s_clean)
    if m:
        whole, frac = m.group(1), m.group(2)
        return float(whole) + float(frac) / (10 ** len(frac))

    # "1万2" / "1.5万" / "2k5" (阿拉伯数字 + 万/k)
    m = re.fullmatch(r"(\d+(?:\.\d+)?)万(\d+)?", s_clean)
    if m:
        base = float(m.group(1)) * 10000
        if m.group(2):
            base += float(m.group(2)) * (10 ** max(0, 4 - len(m.group(2))))
        return base
    m = re.fullmatch(r"(\d+(?:\.\d+?)?)[kK](\d+)?", s_clean)
    if m:
        base = float(m.group(1)) * 1000
        if m.group(2):
            base += float(m.group(2)) * (10 ** max(0, 3 - len(m.group(2))))
        return base

    # 中文数字
    if re.search(rf"[{CN_DIGIT_CHARS}{UNIT_CHARS}万亿]", s_clean):
        return parse_chinese_number(s_clean)

    raise ValueError(f"无法解析价格文本: {text!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="价格解析与实付校验")
    parser.add_argument("prices", nargs="*", help="待归一化的价格文本")
    parser.add_argument("--check", nargs="+", metavar="N",
                        help="校验: 商品金额 运费 优惠... 实付款 (中间多项均计为优惠)")
    parser.add_argument("--eval", dest="expr", help="求值算式, 如 '95 + 0 - 6 == 89'")
    args = parser.parse_args()

    if args.expr:
        if not re.fullmatch(r"[\d+\-*/(). =]+", args.expr):
            print("ERROR: 算式包含不允许的字符", file=sys.stderr)
            return 1
        print(f"{args.expr} -> {eval(args.expr)}")  # noqa: S307 (输入已白名单校验)
        return 0

    if args.check:
        vals = [float(v) for v in args.check]
        if len(vals) < 4:
            print("ERROR: --check 需要至少 4 个数值: 商品金额 运费 优惠 实付款", file=sys.stderr)
            return 1
        goods, shipping, actual = vals[0], vals[1], vals[-1]
        discount = sum(vals[2:-1])
        expected = goods + shipping - discount
        diff = round(expected - actual, 2)
        status = "PASS ✅" if diff == 0 else f"FAIL ❌ 差额 {diff:+.2f} 元"
        print(f"商品金额 {goods:.2f} + 运费 {shipping:.2f} - 优惠 {discount:.2f} "
              f"= 期望实付 {expected:.2f} | 图中实付 {actual:.2f} | {status}")
        return 0 if diff == 0 else 2

    if not args.prices:
        parser.print_help()
        return 1

    rc = 0
    for p in args.prices:
        try:
            print(f"{p!r} -> {parse_price(p):.2f}")
        except ValueError as e:
            print(f"{p!r} -> ERROR: {e}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())

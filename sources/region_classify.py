"""地区分类器：把煤焦现货价格/指数名称归类为 (品种, 地区类型, 地区) 三元组，
供 web_cctd 等现货源将非结构化名称结构化后写入 spot_regional 表。"""
import config


def _match_variety(name):
    """返回名称命中的品种（焦煤/焦炭/动力煤等），无品种关键词命中时返回 None。"""
    for variety, kws in config.VARIETY_KEYWORDS.items():
        if any(kw in name for kw in kws):
            return variety
    return None


def _first_hit(name, names):
    """返回 names 中第一个作为子串出现在 name 内的元素，均未命中返回 None。"""
    for n in names:
        if n in name:
            return n
    return None


def classify(name):
    """把价格名称归类为 (品种, 地区类型, 地区)；无品种命中返回 None。

    判定顺序：进口 → 港口 → 产地 → 消费地 → 全国(兜底)。
    当名称包含"煤"但无特定品种关键词时，按动力煤兜底处理。
    """
    if not name:
        return None
    variety = _match_variety(name)
    if variety is None:
        if "煤" in name:
            variety = "动力煤"   # 无焦煤/焦炭关键词的煤价，按动力煤兜底
        else:
            return None

    if any(kw in name for kw in config.IMPORT_KEYWORDS):
        hit = _first_hit(name, config.IMPORT_KEYWORDS)
        # 进口来源若是具体口岸/国别用原文，否则用"进口"
        region = hit if hit and hit != "进口" else "进口"
        return (variety, "进口", region)

    port = _first_hit(name, config.PORT_NAMES)
    if port:
        return (variety, "港口", port)

    area = _first_hit(name, config.PRODUCTION_AREAS)
    if area:
        return (variety, "产地", area)

    cons = _first_hit(name, config.CONSUMPTION_AREAS)
    if cons:
        return (variety, "消费地", cons)

    return (variety, "全国", "全国")

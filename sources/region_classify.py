import config


def _match_variety(name):
    for variety, kws in config.VARIETY_KEYWORDS.items():
        if any(kw in name for kw in kws):
            return variety
    return None


def _first_hit(name, names):
    for n in names:
        if n in name:
            return n
    return None


def classify(name):
    """把价格名称归类为 (品种, 地区类型, 地区)；无品种命中返回 None。

    判定顺序：进口 → 港口 → 产地 → 消费地 → 全国(兜底)。
    """
    if not name:
        return None
    variety = _match_variety(name)
    if variety is None:
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

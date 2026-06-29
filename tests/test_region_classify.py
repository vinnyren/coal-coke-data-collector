from sources.region_classify import classify


def test_port_index():
    assert classify("CCTD秦皇岛动力煤(Q5500)") == ("动力煤", "港口", "秦皇岛")


def test_production_area():
    assert classify("新疆煤现货参考价") == ("动力煤", "产地", "新疆")


def test_import_keyword_takes_priority():
    # 含"进口"应判为进口，即使也含港口名
    assert classify("京唐港进口炼焦煤") == ("焦煤", "进口", "进口")


def test_lianjiao_maps_to_jiaomei():
    v, _, _ = classify("吕梁主焦煤车板价")
    assert v == "焦煤"


def test_consumption_area():
    assert classify("唐山二级冶金焦到厂价") == ("焦炭", "消费地", "唐山")


def test_national_fallback():
    assert classify("动力煤全国均价") == ("动力煤", "全国", "全国")


def test_no_variety_returns_none():
    assert classify("螺纹钢华东价格") is None

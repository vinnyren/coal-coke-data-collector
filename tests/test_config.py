import config

def test_varieties_cover_three_kinds():
    assert set(config.VARIETIES) == {"焦煤", "焦炭", "动力煤"}

def test_each_variety_has_required_fields():
    for name, v in config.VARIETIES.items():
        for field in ("code", "exchange", "main_symbol", "spot_var", "inventory_name"):
            assert field in v, f"{name} 缺少 {field}"

def test_db_path_points_to_sqlite_file():
    assert str(config.DB_PATH).endswith("coal_data.db")

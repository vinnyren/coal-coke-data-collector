CREATE TABLE IF NOT EXISTS futures_daily (
    variety TEXT NOT NULL,
    contract TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, settle REAL,
    volume REAL, open_interest REAL,
    UNIQUE(variety, contract, trade_date)
);

CREATE TABLE IF NOT EXISTS futures_realtime (
    variety TEXT NOT NULL,
    contract TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    last_price REAL, bid REAL, ask REAL,
    volume REAL, open_interest REAL,
    UNIQUE(variety, contract, captured_at)
);

CREATE TABLE IF NOT EXISTS spot_basis (
    variety TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    spot_price REAL, dominant_price REAL, near_price REAL,
    basis REAL, basis_rate REAL,
    UNIQUE(variety, trade_date)
);

CREATE TABLE IF NOT EXISTS position_rank (
    variety TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    side TEXT NOT NULL,          -- 'long' / 'short'
    rank_no INTEGER NOT NULL,
    member TEXT,
    volume REAL, change REAL,
    UNIQUE(variety, trade_date, side, rank_no)
);

CREATE TABLE IF NOT EXISTS inventory (
    variety TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    inventory REAL, change REAL,
    UNIQUE(variety, trade_date)
);

CREATE TABLE IF NOT EXISTS index_price (
    index_name TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    price REAL, source TEXT,
    UNIQUE(index_name, trade_date)
);

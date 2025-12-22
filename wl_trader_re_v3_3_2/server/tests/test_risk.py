from main import RISK, symbol_leverage
def test_leverage_buckets():
    assert symbol_leverage("EURUSD")==RISK["lev_fx"]
    assert symbol_leverage("XAUUSD")==RISK["lev_metals"]
    assert symbol_leverage("BTCUSD")==RISK["lev_crypto"]

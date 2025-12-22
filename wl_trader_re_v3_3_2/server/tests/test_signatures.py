import time
from utils_sign import sign_event, verify_event
def test_hmac_roundtrip():
    body={"user_id":1,"ts":int(time.time()*1000),"kind":"adjust","symbol":None,"qty":None,"price":None,"realized":0.0,"cash_delta":100.0,"note":"balance_adjust","source":"admin","reason":"manual"}
    sig = sign_event(body)
    assert isinstance(sig, str) and len(sig)==64
    assert verify_event(body, sig) is True
def test_verify_fails_on_tamper():
    body={"user_id":1,"ts":int(time.time()*1000),"kind":"adjust","symbol":None,"qty":None,"price":None,"realized":0.0,"cash_delta":100.0,"note":"balance_adjust","source":"admin","reason":"manual"}
    sig = sign_event(body); body["cash_delta"]=200.0
    assert verify_event(body, sig) is False

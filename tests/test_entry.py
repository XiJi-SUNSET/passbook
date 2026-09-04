"""Entry 模型：登录账号形态判定（邮箱/手机号/用户名）的纯逻辑测试。"""

from passbook.core.entry import login_account_kind


def test_email_detection():
    assert login_account_kind("xiji@qq.com") == "email"
    assert login_account_kind("  a@b.com  ") == "email"  # 容忍首尾空白
    assert login_account_kind("138@phone.example") == "email"  # 含 @ 优先于数字


def test_cn_mobile_detection():
    assert login_account_kind("13800138000") == "phone"
    assert login_account_kind("19912345678") == "phone"   # 新号段也支持
    assert login_account_kind("23800138000") == "username"  # 非 1[3-9] 开头不算
    assert login_account_kind("1380013800") == "username"   # 缺一位不是大陆手机号


def test_username_fallback():
    assert login_account_kind("xijisunset") == "username"
    assert login_account_kind("QQ10001") == "username"      # 纯数字名（含字母）
    assert login_account_kind("12345") == "username"        # 太短的数字不误判


def test_empty():
    assert login_account_kind("") == "empty"
    assert login_account_kind("   ") == "empty"

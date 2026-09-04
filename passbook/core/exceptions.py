"""异常体系。

三类异常对应三种完全不同的用户行动建议：
- CredentialsError    → 重输主密码（或确认文件没被篡改/替换）
- FormatError         → 这不是本程序生成的文件 / 格式版本过新，别硬解
- PayloadChecksumError→ 上次保存写坏了，赶紧从备份恢复
"""


class PassbookError(Exception):
    """密码本所有异常的基类。"""


class FormatError(PassbookError):
    """文件不是密码本、格式损坏或版本不支持。"""


class CredentialsError(PassbookError):
    """主密码错误或文件头被篡改。

    刻意不区分"密码错"与"头被篡改"，防止被当作解密预言机探测。
    """


class PayloadChecksumError(PassbookError):
    """数据区完整性校验失败——只能来自文件损坏，提示恢复备份。"""

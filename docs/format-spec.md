# .pbk 文件格式规范 (v1)

> 密码本单文件存储格式。全部整数为大端序（network order）。

## 总体布局

```
┌────────────────────────────────────────────────────────────┐
│ header_plain (61B)  ── magic + version + KDF/Cipher 参数     │
│ header_tag  (16B)   ── HMAC-SHA256(header_key, header_plain) │
│ wrapped_dek (48B)   ── AES-256-GCM(data_key, dek_iv, dek)    │
│ payload     (变长)   ── AES-256-GCM(dek, payload_iv,          │
│                         gzip(JSON), aad=header_plain+dek)    │
└────────────────────────────────────────────────────────────┘
```

AAD 串接形成认证链：header_tag 覆盖整个明文头；DEK 包装与 payload
加密均把前序字节作为 AAD，任何篡改都会在解密时失败。

## header_plain 字段

| 偏移 | 大小 | 字段 | 值 |
|---|---|---|---|
| 0 | 8 | magic | `"PASSBOOK"` |
| 8 | 2 | format_version | `1` |
| 10 | 1 | kdf_alg | `1` = Argon2id |
| 11 | 4 | memory_mib | Argon2id 内存 (MiB) |
| 15 | 4 | iterations | Argon2id 迭代次数 |
| 19 | 1 | parallelism | Argon2id 并行度 |
| 20 | 16 | salt | KDF 盐 |
| 36 | 1 | cipher_alg | `1` = AES-256-GCM |
| 37 | 12 | dek_iv | 包装 DEK 用的 IV |
| 49 | 12 | payload_iv | 加密 payload 用的 IV |

## 密钥链

```
主密码 ──Argon2id(salt, mem, iter, para)──▶ KEK (32B)
KEK ──HKDF(info="passbook:header")──▶ header_key (16B)
KEK ──HKDF(info="passbook:data")──▶ data_key (32B)
随机 ──CSPRNG──▶ DEK (32B)
data_key ──GCM(dek_iv)──▶ 包装 DEK
DEK ──GCM(payload_iv)──▶ 加密 gzip(条目 JSON)
```

## 设计要点

1. **KDF 参数明文入头**：不存参数则换机器/升级参数后旧库永远打不开；
   头被 HMAC 认证，防降级攻击（把参数改成弱值）。
2. **双层密钥**：改主密码只重包 DEK（毫秒级），无需重加密整个库。
3. **AEAD 自带认证**：不用 CBC+HMAC 手工组合，少一个出错点。
4. **版本号前置**：`format_version` 为将来格式升级留迁移路径。

## 读取失败映射

| 阶段 | 异常 | 用户提示 |
|---|---|---|
| magic/version/算法不支持 | `FormatError` | 不是本程序文件或版本过新 |
| header_tag 校验失败 | `CredentialsError` | 密码错或文件被篡改（不区分） |
| DEK 解包失败 | `CredentialsError` | 同上 |
| payload GCM 校验失败 | `PayloadChecksumError` | 数据损坏，恢复备份 |

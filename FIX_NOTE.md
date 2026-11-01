# db_manager.py 修复说明

当前 `vendor/xianyu-auto-reply-fix/db_manager.py` 在 main 上被意外覆盖为占位内容。

请按以下步骤恢复并应用修复：

```bash
# 从上一正常提交恢复原文件
git checkout cda4de0911f1a5f96d0aec9e71de01b92640f76b -- vendor/xianyu-auto-reply-fix/db_manager.py

# 应用补丁
git apply vendor/xianyu-auto-reply-fix/db_manager_password_fix.patch

# 提交
git add vendor/xianyu-auto-reply-fix/db_manager.py
git commit -m "fix(seller): restore db_manager.py and read admin password from SELLER_PASSWORD on first init"
git push
```

修复后，首次建库会优先读取环境变量 `SELLER_PASSWORD` 或 `ADMIN_PASSWORD`，未设置时回退 `admin123` 并打印警告。已有数据库不会被修改。

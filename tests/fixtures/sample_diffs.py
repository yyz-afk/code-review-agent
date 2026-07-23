"""DiffParser 测试 fixtures：真实风格的 diff 样本。"""

# 标准 unified diff（含新增、修改、删除、重命名）
SIMPLE_DIFF = """\
diff --git a/example.py b/example.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/example.py
@@ -0,0 +1,5 @@
+import os
+
+
+def hello():
+    print("hello")
"""

MULTI_HUNK_DIFF = """\
diff --git a/app.py b/app.py
index 1111111..2222222 100644
--- a/app.py
+++ b/app.py
@@ -5,4 +5,7 @@ def old_func():
     pass


+def new_func():
+    return 42
+
@@ -20,3 +23,5 @@ def another():
     x = 1
     y = 2
     return x + y
+    z = 3
+    return x + y + z
"""

MULTI_FILE_DIFF = """\
diff --git a/main.py b/main.py
index 1111111..2222222 100644
--- a/main.py
+++ b/main.py
@@ -1,3 +1,4 @@
 def run():
     start()
+    finish()
diff --git a/utils.py b/utils.py
index 3333333..4444444 100644
--- a/utils.py
+++ b/utils.py
@@ -10,3 +10,4 @@
 def helper():
     return None
+    raise RuntimeError()
"""

DELETE_FILE_DIFF = """\
diff --git a/old_module.py b/old_module.py
deleted file mode 100644
index 5555555..0000000
--- a/old_module.py
+++ /dev/null
@@ -1,5 +0,0 @@
-import os
-
-
-def deprecated():
-    pass
"""

# 含中文注释（验证 UTF-8 解析）
UTF8_DIFF = """\
diff --git a/server.py b/server.py
index 1111111..2222222 100644
--- a/server.py
+++ b/server.py
@@ -1,3 +1,5 @@
 def handler():
+    # 处理用户请求
+    user_id = request.args.get("id")
     return process(user_id)
"""

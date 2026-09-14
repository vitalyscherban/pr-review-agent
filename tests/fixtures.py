SAMPLE_DIFF = """diff --git a/src/app.py b/src/app.py
index e69de29..4b825dc 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,6 @@
 def add(a, b):
-    return a + b
+    return a + b  # fixed
+
+def divide(a, b):
+    return a / b
diff --git a/src/new_file.py b/src/new_file.py
new file mode 100644
index 0000000..1e5f9c1
--- /dev/null
+++ b/src/new_file.py
@@ -0,0 +1,2 @@
+password = "hardcoded-secret"
+print(password)
diff --git a/assets/logo.png b/assets/logo.png
new file mode 100644
index 0000000..abcdef1
Binary files /dev/null and b/assets/logo.png differ
"""

import subprocess

from ai_team.executor import AgentExecutor
from ai_team.skills import SkillLoader


class PatchModel:
    def generate(self, role, system_prompt, user_prompt):
        return """STATUS: COMPLETE
Created the requested file.
```diff
diff --git a/hello.txt b/hello.txt
new file mode 100644
index 0000000..ce01362
--- /dev/null
+++ b/hello.txt
@@ -0,0 +1 @@
+hello
```
"""


class EmptyPatchModel:
    def generate(self, role, system_prompt, user_prompt):
        return """STATUS: COMPLETE
No repository change is needed.
```diff
```
"""


class MalformedPatchModel:
    def generate(self, role, system_prompt, user_prompt):
        return """STATUS: COMPLETE
```diff
this is not a patch
```
"""


def test_permitted_role_applies_validated_diff(tmp_path, skills_root):
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    executor = AgentExecutor(tmp_path, SkillLoader(skills_root), PatchModel())
    executor.run_role("developer", "Create hello.txt")
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello\n"


def test_empty_diff_fence_is_treated_as_no_change(tmp_path, skills_root):
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    executor = AgentExecutor(tmp_path, SkillLoader(skills_root), EmptyPatchModel())
    result = executor.run_role("product", "Report current state")
    assert result.startswith("STATUS: COMPLETE")


def test_nonempty_malformed_diff_still_fails_validation(tmp_path, skills_root):
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    executor = AgentExecutor(tmp_path, SkillLoader(skills_root), MalformedPatchModel())
    try:
        executor.run_role("developer", "Make a change")
    except RuntimeError as error:
        assert "patch failed validation" in str(error)
    else:
        raise AssertionError("Malformed model patch should fail validation")

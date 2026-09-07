from types import SimpleNamespace

import pytest

from ai_team.config import Settings
from ai_team.executor import AgentExecutor, run_command
from ai_team.models import OmniRouteModelClient, ProviderFailure
from ai_team.skills import SkillLoader


class Completions:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


def response(model="qwen3-coder:30b", content="ok"):
    return SimpleNamespace(model=model, id="id", choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def client_with(values):
    completions = Completions(values)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def test_transport_rejects_wrong_route_without_retry():
    fake, calls = client_with([response("gpt-oss:20b")])
    client = OmniRouteModelClient(Settings(provider_attempts=2), client=fake)
    with pytest.raises(ProviderFailure, match="WRONG_ROUTE"):
        client.generate("developer", "system", "user")
    assert calls.calls == 1


def test_transport_rejects_empty_and_malformed_results():
    fake, _ = client_with([response(content="")])
    with pytest.raises(ProviderFailure, match="EMPTY"):
        OmniRouteModelClient(Settings(), client=fake).generate("developer", "s", "u")
    fake, _ = client_with([RuntimeError("raw sensitive upstream detail")])
    with pytest.raises(ProviderFailure, match="inspect safe audit metadata"):
        OmniRouteModelClient(Settings(), client=fake).generate("developer", "s", "u")


class SecretPatch:
    def generate(self, *args):
        return """STATUS: COMPLETE
```diff
diff --git a/.env b/.env
new file mode 100644
--- /dev/null
+++ b/.env
@@ -0,0 +1 @@
+TOKEN=x
```
"""


class MultiplePatches:
    def generate(self, *args):
        return "STATUS: COMPLETE\n```diff\na\n```\n```diff\nb\n```"


def test_secret_patch_and_multiple_patch_are_rejected_without_changes(tmp_path, skills_root):
    import subprocess
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    with pytest.raises(RuntimeError, match="excluded or out-of-scope"):
        AgentExecutor(tmp_path, SkillLoader(skills_root), SecretPatch()).run_role("developer", "x")
    assert not (tmp_path / ".env").exists()
    with pytest.raises(RuntimeError, match="multiple patches"):
        AgentExecutor(tmp_path, SkillLoader(skills_root), MultiplePatches()).run_role("developer", "x")


def test_review_only_executor_forbids_valid_mutation(tmp_path, skills_root):
    import subprocess
    from test_executor import PatchModel
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    executor = AgentExecutor(tmp_path, SkillLoader(skills_root), PatchModel(), allow_mutation=False)
    with pytest.raises(RuntimeError, match="not authorized"):
        executor.run_role("developer", "x")
    assert not (tmp_path / "hello.txt").exists()


def test_command_evidence_records_exit_and_timeout(tmp_path):
    import sys
    passed = run_command(tmp_path, [sys.executable, "-c", "print('ok')"], timeout=5)
    failed = run_command(tmp_path, [sys.executable, "-c", "raise SystemExit(3)"], timeout=5)
    timed = run_command(tmp_path, [sys.executable, "-c", "import time; time.sleep(1)"], timeout=0.01)
    assert "exit=0" in passed.result and "exit=3" in failed.result and "timeout" in timed.result

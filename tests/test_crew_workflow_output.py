import importlib
import os
import sys
import types
import unittest


class _Agent:
    verbose = False


class _CrewOutput:
    def __str__(self):
        return "agent reasoning text"


class _Crew:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def kickoff(self):
        return _CrewOutput()


class _Process:
    sequential = object()


def _install_stubs(span_recorder=None):
    sys.modules["crewai"] = types.SimpleNamespace(Crew=_Crew, Process=_Process)
    sys.modules["src.agents"] = types.SimpleNamespace(
        meeting_analyst=_Agent(),
        risk_scorer_agent=_Agent(),
        notion_orchestrator=_Agent(),
    )
    sys.modules["src.tasks"] = types.SimpleNamespace(build_tasks=lambda transcript: [transcript])
    sys.modules["src.tools"] = types.SimpleNamespace(
        create_sprint_summary=lambda: "summary text",
        reset_session=lambda: None,
    )

    if span_recorder is not None:
        def span(**kwargs):
            def decorator(func):
                def wrapper(*args, **inner_kwargs):
                    result = func(*args, **inner_kwargs)
                    span_recorder.append(result)
                    return result

                return wrapper

            return decorator

        sys.modules["neatlogs"] = types.SimpleNamespace(span=span)
    else:
        sys.modules.pop("neatlogs", None)

    sys.modules.pop("src.crew", None)
    return importlib.import_module("src.crew")


class CrewWorkflowOutputTest(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("NEATLOGS_API_KEY", None)
        os.environ.pop("NEATLOGS_ENDPOINT", None)
        for module in ("src.crew", "src.agents", "src.tasks", "src.tools", "crewai", "neatlogs"):
            sys.modules.pop(module, None)

    def test_run_returns_serialized_kickoff_output(self):
        crew = _install_stubs()

        result, summary = crew.run("transcript")

        self.assertEqual(result, "agent reasoning text")
        self.assertEqual(summary, "summary text")

    def test_traced_workflow_span_receives_serialized_output(self):
        recorded_outputs = []
        os.environ["NEATLOGS_API_KEY"] = "test-key"
        os.environ["NEATLOGS_ENDPOINT"] = "http://neatlogs.test"
        crew = _install_stubs(recorded_outputs)

        result, _ = crew.run("transcript")

        self.assertEqual(result, "agent reasoning text")
        self.assertEqual(recorded_outputs, ["agent reasoning text"])


if __name__ == "__main__":
    unittest.main()

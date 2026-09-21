"""작성 소스 보안 게이트의 차단과 맥락 검토 경계를 확인한다."""

import unittest
from unittest import mock

from scripts import security_source_gate as gate


class SecuritySourceGateTests(unittest.TestCase):
    def test_javascript_strings_and_comments_are_not_executable_findings(self) -> None:
        source = """
const oldCode = 'catch{} JSON.parse(data) dangerouslySetInnerHTML';
// catch{} document.write(value)
/* .catch(() => {}) */
const template = `catch{} ${ignored}`;
"""
        self.assertEqual(gate._findings_for_js("static/js/example.mjs", source, review=False), [])
        self.assertEqual(gate._findings_for_js("static/js/example.mjs", source, review=True), [])

    def test_empty_catches_and_unsafe_html_are_blocked(self) -> None:
        source = """
try { run(); } catch (error) {}
recorder.stop().catch(() => {}).finally(cleanup);
document.write(untrusted);
element.dangerouslySetInnerHTML = { __html: untrusted };
"""
        rules = [item[0] for item in gate._findings_for_js("static/js/example.js", source, review=False)]
        self.assertEqual(rules.count("JS-32"), 2)
        self.assertEqual(rules.count("JS-04"), 1)
        self.assertTrue(
            any(
                item[0] == "JS-04"
                for item in gate._findings_for_js("static/js/example.js", source, review=True)
            )
        )

    def test_only_new_context_dependent_apis_require_review(self) -> None:
        path = "static/js/example.js"
        older = "const value = JSON.parse(localCopy);\n"
        newer = older + "const body = JSON.parse(response.body);\n"
        with (
            mock.patch.object(gate, "_changed_paths", return_value=[path]),
            mock.patch.object(gate, "_source", side_effect=lambda ref, name: newer if ref == ":" else older),
            mock.patch.object(gate, "_reviewed", return_value=set()),
        ):
            findings = gate.check("staged", "HEAD", ":")
        self.assertEqual(
            [(rule, name, line) for rule, name, line, _ in findings],
            [("JS-36", path, 2)],
        )
        reviewed = {(findings[0][0], findings[0][1], findings[0][3])}
        with (
            mock.patch.object(gate, "_changed_paths", return_value=[path]),
            mock.patch.object(gate, "_source", side_effect=lambda ref, name: newer if ref == ":" else older),
            mock.patch.object(gate, "_reviewed", return_value=reviewed),
        ):
            self.assertEqual(gate.check("staged", "HEAD", ":"), [])

    def test_dynamic_sql_is_blocked_but_psycopg_identifiers_are_separate(self) -> None:
        unsafe = 'def load(cur, table):\n    cur.execute(f"SELECT * FROM {table}")\n'
        safe = (
            'def load(cur, table):\n'
            '    cur.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(table)))\n'
        )
        not_sql = 'def dispatch(executor, task):\n    executor.execute(f"task: {task}")\n'
        self.assertEqual(gate._findings_for_python("analysis/example.py", unsafe)[0][0], "PY-01")
        self.assertEqual(gate._findings_for_python("analysis/example.py", safe), [])
        self.assertEqual(gate._findings_for_python("analysis/example.py", not_sql), [])

    def test_python_empty_exception_handler_is_blocked(self) -> None:
        source = "try:\n    work()\nexcept Exception:\n    pass\n"
        self.assertEqual(gate._findings_for_python("analysis/example.py", source)[0][0], "PY-37")


if __name__ == "__main__":
    unittest.main()

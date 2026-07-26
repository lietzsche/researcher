import json
import shutil
import subprocess
from pathlib import Path

import pytest


APP_JS = Path(__file__).parents[1] / "app" / "static" / "app.js"


def test_section_neighbors_follow_toc_order_and_done_status() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js is required for the frontend behavior test")

    script = f"""
const fs = require("fs");
const vm = require("vm");
const element = {{ addEventListener() {{}}, className: "", textContent: "" }};
const context = {{
  document: {{ querySelector() {{ return element; }} }},
  window: {{ addEventListener() {{}}, setTimeout() {{}}, clearTimeout() {{}} }},
  console,
  AbortController,
  fetch: async () => {{}},
}};
vm.createContext(context);
vm.runInContext(fs.readFileSync({json.dumps(str(APP_JS))}, "utf8"), context);
const toc = [
  {{ id: "01", title: "One" }},
  {{ id: "02", title: "Two" }},
  {{ id: "03", title: "Three" }},
];
const states = [
  {{ id: "01", status: "done" }},
  {{ id: "02", status: "done" }},
  {{ id: "03", status: "pending" }},
];
process.stdout.write(JSON.stringify(context.sectionNeighbors(toc, states, "02")));
"""
    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    neighbors = json.loads(result.stdout)
    assert neighbors["previous"] == {
        "id": "01",
        "title": "One",
        "available": True,
    }
    assert neighbors["next"] == {
        "id": "03",
        "title": "Three",
        "available": False,
    }

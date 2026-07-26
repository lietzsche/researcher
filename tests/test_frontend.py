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
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
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


def test_topic_cards_route_pending_toc_states_to_status_screen() -> None:
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
const base = {{
  topic: "Topic", slug: "topic", depth: "standard",
  completed_sections: 0, total_sections: 0, has_study_document: false,
}};
process.stdout.write(JSON.stringify({{
  generating: context.topicCard({{ ...base, toc_status: "generating" }}),
  error: context.topicCard({{ ...base, toc_status: "error" }}),
  done: context.topicCard({{ ...base, toc_status: "done" }}),
}}));
"""
    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    cards = json.loads(result.stdout)
    assert "목차 생성 중" in cards["generating"]
    assert "#/topic/topic/toc" in cards["generating"]
    assert "목차 생성 실패" in cards["error"]
    assert "#/topic/topic/toc" in cards["error"]
    assert "#/topic/topic/progress" in cards["done"]


def test_build_navigation_is_immediate_and_section_nav_is_rendered_twice() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js is required for the frontend behavior test")

    script = f"""
const fs = require("fs");
const vm = require("vm");
let buildHandler;
const root = {{
  innerHTML: "",
  querySelectorAll() {{ return []; }},
  querySelector() {{
    return {{ querySelectorAll() {{ return []; }}, addEventListener() {{}} }};
  }},
}};
const buildButton = {{
  disabled: false,
  addEventListener(_name, handler) {{ buildHandler = handler; }},
}};
const context = {{
  document: {{
    querySelector(selector) {{
      if (selector === "#app") return root;
      if (selector === "#build-all") return buildButton;
      return {{ addEventListener() {{}} }};
    }},
  }},
  window: {{
    addEventListener() {{}},
    setTimeout() {{}},
    clearTimeout() {{}},
    location: {{ hash: "#/topic/topic/toc" }},
  }},
  console,
  AbortController,
  marked: {{ parse(text) {{ return text; }} }},
  fetch: async (url) => {{
    if (url.endsWith("/build")) return new Promise(() => {{}});
    if (url.includes("/sections/")) {{
      return {{ ok: true, text: async () => "# Body" }};
    }}
    return {{
      ok: true,
      status: 200,
      json: async () => ({{
        toc: [{{ id: "01", title: "One" }}, {{ id: "02", title: "Two" }}],
        manifest: {{
          topic: "Topic", depth: "standard", toc_status: "done",
          sections: [
            {{ id: "01", title: "One", status: "done" }},
            {{ id: "02", title: "Two", status: "done" }},
          ],
        }},
      }}),
    }};
  }},
}};
vm.createContext(context);
vm.runInContext(fs.readFileSync({json.dumps(str(APP_JS))}, "utf8"), context);
(async () => {{
  await context.renderToc("topic");
  buildHandler({{ currentTarget: buildButton }});
  const immediateHash = context.window.location.hash;
  await context.renderSectionDocument("topic", "01");
  const navCount = (root.innerHTML.match(/<nav class="section-nav"/g) || []).length;
  process.stdout.write(JSON.stringify({{ immediateHash, navCount }}));
}})();
"""
    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    behavior = json.loads(result.stdout)
    assert behavior["immediateHash"] == "#/topic/topic/progress"
    assert behavior["navCount"] == 2

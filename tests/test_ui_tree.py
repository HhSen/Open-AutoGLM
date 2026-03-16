import xml.etree.ElementTree as ET

import main
from phone_agent.actions.handler import parse_action, summarize_ui_tree_for_model
from phone_agent.adb.device import _extract_android_ui_nodes
from phone_agent.xctest.device import _extract_ios_ui_nodes


def test_parse_get_ui_tree_action():
    action = parse_action('do(action="Get_UI_Tree")')

    assert action == {"_metadata": "do", "action": "Get_UI_Tree"}


def test_extract_android_ui_nodes_includes_relative_coordinates():
    root = ET.fromstring(
        """
        <hierarchy>
          <node
            index="0"
            text="Search"
            resource-id="com.example:id/search"
            class="android.widget.EditText"
            package="com.example"
            content-desc=""
            clickable="true"
            enabled="true"
            focused="false"
            selected="false"
            bounds="[100,200][300,260]"
          />
        </hierarchy>
        """
    )

    nodes = _extract_android_ui_nodes(root, screen_width=400, screen_height=800)

    assert len(nodes) == 1
    assert nodes[0]["center_px"] == [200, 230]
    assert nodes[0]["center_rel"] == [500, 287]
    assert nodes[0]["resource_id"] == "com.example:id/search"


def test_extract_ios_ui_nodes_includes_relative_coordinates():
    root = {
        "type": "XCUIElementTypeButton",
        "label": "Continue",
        "name": "Continue",
        "value": None,
        "visible": True,
        "enabled": True,
        "accessible": True,
        "rect": {"x": 10, "y": 20, "width": 100, "height": 40},
        "children": [],
    }

    nodes = _extract_ios_ui_nodes(root, screen_width=390, screen_height=844)

    assert len(nodes) == 1
    assert nodes[0]["center_px"] == [180, 120]
    assert nodes[0]["center_rel"] == [461, 142]
    assert nodes[0]["label"] == "Continue"


def test_extract_ios_ui_nodes_without_screen_size_omits_relative_coordinates():
    root = {
        "type": "XCUIElementTypeButton",
        "label": "Continue",
        "name": "Continue",
        "value": None,
        "visible": True,
        "enabled": True,
        "accessible": True,
        "rect": {"x": 10, "y": 20, "width": 100, "height": 40},
        "children": [],
    }

    nodes = _extract_ios_ui_nodes(root)

    assert len(nodes) == 1
    assert "center_rel" not in nodes[0]
    assert nodes[0]["center_px"] == [180, 120]


def test_summarize_ui_tree_prioritizes_labeled_interactive_nodes():
    ui_tree = {
        "nodes": [
            {"type": "XCUIElementTypeOther", "label": "", "accessible": False},
            {"type": "XCUIElementTypeButton", "label": "Save", "accessible": True},
        ]
    }

    summarized = summarize_ui_tree_for_model(ui_tree, max_nodes=1)

    assert summarized["node_count"] == 2
    assert summarized["truncated"] is True
    assert summarized["nodes"] == [ui_tree["nodes"][1]]


def test_print_or_save_state_prints_summary_and_saves_full_tree(tmp_path, capsys):
    state = {
        "platform": "adb",
        "nodes": [
            {"type": "TextView", "text": f"Label {index}", "clickable": False}
            for index in range(130)
        ],
    }
    output_path = tmp_path / "tree.json"

    main._print_or_save_state(state, str(output_path))

    stdout = capsys.readouterr().out
    assert "Full state saved to:" in stdout
    assert '"node_count": 130' in stdout
    assert '"truncated": true' in stdout

    saved_payload = output_path.read_text(encoding="utf-8")
    assert '"platform": "adb"' in saved_payload
    assert saved_payload.count('"type": "TextView"') == 130

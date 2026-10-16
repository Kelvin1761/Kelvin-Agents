"""Export exact active formula sources and transitive engine helpers; no paraphrase."""
import ast
import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ENGINE = REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine"


def main():
    output = ["# HKJC 全公式原碼附錄", "", "由 formula_sources.py 抽取，數值直接來自當前 code；展示時移除行尾空白，SHA256對應原檔。",
              "包含九維、初出馬、顯示尺、SIP、限幅、資料解析及中性回退。診斷分會註明；shadow 候選不等於現役。", ""]
    sources = [ENGINE / name for name in ("dimensions.py", "scoring.py", "matrix_mapper.py",
               "features/form.py", "features/speed.py", "features/jockey.py", "features/trainer.py",
               "features/tier_loader.py", "features/draw.py", "rail_draw_context.py", "live_priors.py")]
    for path in sources:
        text = path.read_text()
        output.extend([f"## {path.relative_to(REPO)}", "", f"SHA256: `{hashlib.sha256(text.encode()).hexdigest()}`", "", "```python", text.rstrip(), "```", ""])
    path = ENGINE / "engine_core.py"
    text = path.read_text()
    tree = ast.parse(text)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RacingEngine")
    methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
    pending = {"_ability_score", "_class_score", "_consistency_score", "_consistency_shadow_detail",
               "_candidate_health_risk_score", "_formline_strength_score", "_trackwork_trend_score",
               "_race_shape_context_score", "_distance_suitability_adjustment", "_apply_mainline_context",
               "_apply_trainer_signal_context", "_apply_trainer_signal_v3", "_apply_health_only_v2",
               "_distance_score", "_track_going_score", "_weight_score", "_risk_score", "_confidence_score"}
    selected = set()
    while pending:
        name = pending.pop()
        if name in selected or name not in methods:
            continue
        selected.add(name)
        for node in ast.walk(methods[name]):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
                pending.add(node.func.attr)
    output.extend(["## engine_core.py：計分方法及傳遞依賴", "", f"抽取 {len(selected)} 個方法。", ""])
    for name in sorted(selected, key=lambda k: methods[k].lineno):
        node = methods[name]
        output.extend([f"### {name}（第 {node.lineno} 行）", "", "```python", ast.get_source_segment(text, node), "```", ""])
    path = ENGINE.parent / "hkjc_auto_orchestrator.py"
    text = path.read_text()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.FunctionDef) and node.name in {"_apply_sip_enhancements", "_apply_mainline_shape_robustness", "_apply_mainline_whole_field_ranking"}:
            output.extend([f"## orchestrator：{node.name}", "", "```python", ast.get_source_segment(text, node), "```", ""])
    dest = Path(__file__).with_name("ALL_FORMULAS.md")
    dest.write_text("\n".join(line.rstrip() for line in "\n".join(output).splitlines()) + "\n", encoding="utf-8")
    print(f"{dest}: {dest.stat().st_size} bytes")


if __name__ == "__main__":
    main()

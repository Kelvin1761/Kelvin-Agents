os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os
import ast
import argparse
from pathlib import Path

DEFAULT_IGNORES = {
    '__pycache__', '.git', '.venv', 'venv', 'node_modules', 
    '.agents', '.claude-plugin', '.claude', '.vscode', 'tmp', 'scratch'
}

def get_docstring(node):
    doc = ast.get_docstring(node)
    if doc:
        # Get first line of docstring
        return doc.strip().split('\n')[0]
    return ""

def format_args(args_node):
    args = []
    for arg in args_node.args:
        arg_str = arg.arg
        if arg.annotation:
            if isinstance(arg.annotation, ast.Name):
                arg_str += f": {arg.annotation.id}"
            # For simplicity, we only capture simple type hints like str, int, bool. 
            # Subscripts like List[str] are harder to parse safely without full AST unparsing,
            # so we just show the param name if it's complex.
        args.append(arg_str)
    
    # Handle *args, **kwargs
    if args_node.vararg:
        args.append(f"*{args_node.vararg.arg}")
    if args_node.kwarg:
        args.append(f"**{args_node.kwarg.arg}")
        
    return ", ".join(args)

def extract_ast_info(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            file_content = f.read()
            
        tree = ast.parse(file_content)
        
        md_lines = []
        md_lines.append(f"## `{filepath}`\n")
        
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
                base_str = f"({', '.join(bases)})" if bases else ""
                doc = get_docstring(node)
                doc_str = f" - {doc}" if doc else ""
                md_lines.append(f"* **Class `{node.name}{base_str}`**{doc_str}")
                
                # Extract methods
                for class_body_item in node.body:
                    if isinstance(class_body_item, ast.FunctionDef):
                        args_str = format_args(class_body_item.args)
                        method_doc = get_docstring(class_body_item)
                        method_doc_str = f" - {method_doc}" if method_doc else ""
                        md_lines.append(f"  * `def {class_body_item.name}({args_str})`{method_doc_str}")
                        
            elif isinstance(node, ast.FunctionDef):
                args_str = format_args(node.args)
                doc = get_docstring(node)
                doc_str = f" - {doc}" if doc else ""
                md_lines.append(f"* **Function `{node.name}({args_str})`**{doc_str}")
                
        if len(md_lines) == 1:
            # File had no classes or functions
            md_lines.append("* (No classes or functions found)")
            
        return "\n".join(md_lines) + "\n"
        
    except SyntaxError as e:
        return f"## `{filepath}`\n* [SyntaxError] Could not parse AST: {e}\n\n"
    except Exception as e:
        return f"## `{filepath}`\n* [Error] {e}\n\n"

def should_ignore(path_obj):
    # Check if any parent part of the path is in the ignore list
    return any(part in DEFAULT_IGNORES for part in path_obj.parts)

def build_repomap(target_dir, output_file=None):
    target_path = Path(target_dir)
    if not target_path.exists():
        print(f"Error: Directory {target_dir} does not exist.")
        return

    output = ["# Antigravity AST Codebase Map\n"]
    
    py_files = []
    for root, _, files in os.walk(target_dir):
        root_path = Path(root)
        if should_ignore(root_path):
            continue
            
        for file in files:
            if file.endswith('.py'):
                py_files.append(root_path / file)
                
    # Sort files for deterministic output
    py_files.sort()
    
    for file_path in py_files:
        # Convert path to string relative to target_dir if reasonable
        rel_path = file_path.relative_to(target_path) if target_path.is_absolute() else file_path
        output.append(extract_ast_info(str(rel_path)))
        
    final_markdown = "\n".join(output)
    
    if output_file:
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(final_markdown)
        print(f"Repomap successfully saved to {output_file}")
    else:
        print(final_markdown)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Antigravity Native AST Repository Mapper")
    parser.add_argument("target_dir", help="Directory to scan")
    parser.add_argument("--output", "-o", help="Output Markdown file path (optional)")
    
    args = parser.parse_args()
    
    build_repomap(args.target_dir, args.output)

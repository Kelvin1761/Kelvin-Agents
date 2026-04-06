import sys
import base64

def append_to_file(filepath, b64_content):
    content = base64.b64decode(b64_content).decode('utf-8')
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(content + '\n')
    print(f"Successfully appended {len(content)} characters to {filepath}")

if __name__ == "__main__":
    filepath = sys.argv[1]
    b64_content = sys.argv[2]
    append_to_file(filepath, b64_content)

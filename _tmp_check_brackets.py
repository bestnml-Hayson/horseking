import os, sys

def check_brackets(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    stack = []
    pairs = {')': '(', ']': '[', '}': '{'}
    lines = content.split('\n')
    in_string = None
    escape = False
    in_comment_line = False
    in_comment_block = False
    for line_no, line in enumerate(lines, 1):
        in_comment_line = False
        i = 0
        while i < len(line):
            ch = line[i]
            # Handle block comment
            if in_comment_block:
                if ch == '*' and i+1 < len(line) and line[i+1] == '/':
                    in_comment_block = False
                    i += 2
                    continue
                i += 1
                continue
            # Handle line comment
            if not in_string:
                if ch == '/' and i+1 < len(line) and line[i+1] == '/':
                    break
                if ch == '/' and i+1 < len(line) and line[i+1] == '*':
                    in_comment_block = True
                    i += 2
                    continue
            # Handle strings
            if escape:
                escape = False
                i += 1
                continue
            if ch == '\\':
                escape = True
                i += 1
                continue
            if in_string:
                if ch == in_string:
                    in_string = None
                i += 1
                continue
            else:
                if ch in ('"', "'", '`'):
                    in_string = ch
                    i += 1
                    continue
            # Brackets
            if ch in '([{':
                stack.append((ch, line_no, i))
            elif ch in ')]}':
                if not stack:
                    print(f"  [{filepath}:{line_no}:{i}] Extra closing '{ch}' - no matching open")
                    return False
                open_ch, open_line, open_i = stack.pop()
                expected_open = pairs[ch]
                if open_ch != expected_open:
                    print(f"  [{filepath}:{line_no}:{i}] Mismatch: closing '{ch}' matches '{open_ch}' at line {open_line}:{open_i} (expected '{expected_open}')")
                    return False
            i += 1
    if stack:
        print(f"  [{filepath}] Unclosed brackets:")
        for (ch, ln, col) in stack[-10:]:
            print(f"    - '{ch}' at line {ln}:{col}")
        return False
    print(f"  [{filepath}] OK - all brackets balanced")
    return True

root = r"D:\Trae\horse\public"
for f in sorted(os.listdir(root)):
    if f.endswith('.js'):
        fp = os.path.join(root, f)
        check_brackets(fp)

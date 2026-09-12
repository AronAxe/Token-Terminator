from pathlib import Path

path = Path("scripts/apply_v051_hardening.py")
text = path.read_text(encoding="utf-8")
old = '''replace_once(
    "src/rtk_hermes_plus/ledger.py",
    '    native_raw_chars INTEGER NOT NULL DEFAULT 0,\\n    native_output_chars INTEGER NOT NULL DEFAULT 0,\\n    native_compressions INTEGER NOT NULL DEFAULT 0,\\n',
    '    native_raw_chars INTEGER NOT NULL DEFAULT 0,\\n    native_output_chars INTEGER NOT NULL DEFAULT 0,\\n    native_raw_tokens INTEGER NOT NULL DEFAULT 0,\\n    native_output_tokens INTEGER NOT NULL DEFAULT 0,\\n    native_token_measurements INTEGER NOT NULL DEFAULT 0,\\n    native_compressions INTEGER NOT NULL DEFAULT 0,\\n',
)
'''
new = '''text = read("src/rtk_hermes_plus/ledger.py")
needle = '    native_raw_chars INTEGER NOT NULL DEFAULT 0,\\n    native_output_chars INTEGER NOT NULL DEFAULT 0,\\n    native_compressions INTEGER NOT NULL DEFAULT 0,\\n'
replacement = '    native_raw_chars INTEGER NOT NULL DEFAULT 0,\\n    native_output_chars INTEGER NOT NULL DEFAULT 0,\\n    native_raw_tokens INTEGER NOT NULL DEFAULT 0,\\n    native_output_tokens INTEGER NOT NULL DEFAULT 0,\\n    native_token_measurements INTEGER NOT NULL DEFAULT 0,\\n    native_compressions INTEGER NOT NULL DEFAULT 0,\\n'
if text.count(needle) != 2:
    raise RuntimeError(f"ledger schema: expected two native metric blocks, found {text.count(needle)}")
text = text.replace(needle, replacement)
write("src/rtk_hermes_plus/ledger.py", text)
'''
if old not in text:
    raise RuntimeError("target patcher block not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")

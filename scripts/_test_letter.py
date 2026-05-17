import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from backend.llm.providers.openai_provider import extract_letter

cases = [
    ("D. MAIS; MAIS; MAS.", "D"),
    ("B",                   "B"),
    ("c",                   "C"),
    ("A)",                  "A"),
    ("E. Nenhuma das anteriores", "E"),
    ("b) texto longo",      "B"),
    ("F: opcao F",          "F"),
    ("A",                   "A"),
]
all_ok = True
for raw, expected in cases:
    got = extract_letter(raw)
    ok = got == expected
    if not ok:
        all_ok = False
    status = "OK  " if ok else "FAIL"
    print(f"  {status}  {repr(raw):<40} -> {got}  (esperado {expected})")

print()
print("Todos OK" if all_ok else "FALHOU")

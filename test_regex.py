import re
text = """#### 💡 結論
> - **核心邏輯:** Lathlain 返回自己曾狂勝的 1400m 路程，兼逢對手水準不及剛戰 Flemington 賽事。更致命的是，今場預計步速偏慢，她可以舒舒服服守在包廂位置，直路發力極致發揮。
> - **最大競爭優勢:** 完美的步速形勢與 1400m 首本路程。
> - **最大失敗原因:** 情緒再次失控。"""

core_logic_match = re.search(r'核心邏輯[^\*]*\*\*\s*(.*?)(?=\n\s*>?\s*-\s*\*\*|$)', text, re.DOTALL)
if core_logic_match:
    print("Match found:", repr(core_logic_match.group(1)))
else:
    print("No match")

# Wong Choi 模型說明

呢個資料夾入面嘅文件，**全部係由 live code 自動生成嘅**。冇人手寫嘅版本。

## 想睇個模型而家係點

用瀏覽器打開（雙擊就得）：

- `AU Wong Choi 模型說明.html`
- `HKJC Wong Choi 模型說明.html`

`.md` 係同一份內容嘅純文字版，方便用手機／編輯器／Telegram 睇。

## 想更新

跑：

```bash
./更新模型說明.sh
```

或者逐個平台：

```bash
python3 .agents/skills/shared_racing/scripts/explain_model.py --platform au
python3 .agents/skills/shared_racing/scripts/explain_model.py --platform hkjc
```

## 唔好手改呢啲檔

改咗會被下次生成覆蓋，而且會令文件同真實模型再次講唔同嘅嘢 —— 呢個就係
之前 `AU Wong Choi 現行評分結構詳解（港式中文）.md` 出事嘅原因：佢寫住 7 維、
提到一個已經唔存在嘅 `rank_adjustments.py`，而真正 live 嘅係 6 維。

想改內容就改生成器：`.agents/skills/shared_racing/scripts/explain_model.py`。

## CI 會幫你睇實

每次 push，CI 會跑 `--check`。如果有人改咗權重但冇重新生成文件，CI 就會紅燈，
唔會出現「文件靜靜咁過期」呢種情況。

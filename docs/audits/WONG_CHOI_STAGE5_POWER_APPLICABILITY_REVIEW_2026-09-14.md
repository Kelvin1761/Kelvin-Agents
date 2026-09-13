# Wong Choi Stage 5 power applicability review — 2026-09-14

## Decision

**DEFER／fail closed。** 現役四份frozen ruler全部要求pre-registered power，但production
checkout目前有 **0/4** reviewed power profiles。呢個結果唔代表模型差，亦唔代表可以放寬
sample gate；只代表現有證據未足以凍結metric-specific minimum effect同variance floor。
任何AU、HKJC、Tennis或NBA candidate仍然不可因Stage 5自動產生promotion authority。

## Authoritative evidence inspected

- Production checkout：`2a7580633c45b3af50b190229ae783b7472ca231`。
- Frozen rulers：`au-v2`、`hkjc-v2`、`tennis-v1`、`nba-v1`。
- `inspect_power_applicability()`重算結果：四個domain均為
  `power_profile_missing`、`profiles_verified=0`、
  `power_applicability_verified=false`、`model_promotion_allowed=false`。
- `nba-v1`仍為`descriptive_only`且`promotion_allowed=false`；歷史或synthetic evidence
  不可代替2026–27 forward live gate。
- D-AU、D-HKJC、D-Tennis、D-NBA producer releases已建立，但本review時仍未merge／activate；
  四批都基於同一rollback target，必須順序refresh及activate。

## Independent contract finding

現有`wong-choi-power-profile/v1`雖然要求一個非空`authority`字串，但未核對：

1. review文件真係存在；
2. path係repo內`docs/audits/`而唔係absolute／traversal／symlink；
3. profile綁定review文件嘅exact bytes；
4. verifier重跑時review文件有冇被改寫。

因此，單靠寫一個虛構authority名稱，理論上可以令任意effect size／SD floor通過靜態
profile shape gate。呢個係Task 6 acceptance blocker，唔可以用release approval或一句
「已review」代替machine binding。

本scope已準備fail-closed `wong-choi-power-profile/v2`修正：profile新增
`authority_sha256`，只接受repo內
`docs/audits/`嘅regular、non-symlink、size-bounded文件，並喺每次verification重新hash。
假hash、path escape及review bytes變更全部被拒絕。修正只加強research safety contract；
冇建立power profile、冇改evaluation ruler、holdout、model、scoring或promotion state。

## Why no numeric profile was created

`minimum_effect`係產品／模型判決尺度，`sd_floor`要由outcome-independent development
evidence估計。兩者都唔可以由terminal結果反推，亦唔可以由測試fixture嘅`0.02／0.05`
複製到production。現況分domain如下：

| Domain | Current applicability | Required evidence before a frozen profile |
|---|---|---|
| AU | DEFER | D-AU activation；pre-registered neutral comparison；同一frozen engine／dataset嘅dev-only paired metric variance；獨立選定每個primary／ranking metric嘅minimum material effect |
| HKJC | DEFER | D-HKJC activation；HKJC自己嘅dev-only variance同cohort coverage；不可借AU數字 |
| Tennis | DEFER | D-Tennis activation；active family有verified earliest pre-match PIT outcomes；逐family development variance；terminal每family floor仍維持600＋power |
| NBA | DEFER | D-NBA activation；首30個forward settled recommendations完成live baseline gate；current ruler仍只可descriptive，profile不可解鎖promotion |

## Verification

- `test_research_power_applicability.py`：13 passed。
- 覆蓋：missing profiles、四domain valid-shape fixture、ruler／metric／family／assumption
  mismatch、authority hash mismatch、authority path escape、forged report、review文件改寫。
- 呢啲fixture只驗證contract行為；fixture數值**唔係**production power設定。

## Task 6 checkpoint

Task 6保持 **NOT READY**。完成條件係：

1. authority-binding修正經獨立scoped release批准及activate；
2. 四個D producer依固定順序activate並有real future evidence；
3. 每個domain嘅power profile由dev-only／forward evidence支持，獨立review後hash-pin；
4. applicability重算為4/4，但輸出仍保持`model_promotion_allowed=false`；
5. Task 10 platform safety matrix同全局health gate完成。

呢個review係「暫緩並列明缺口」嘅證據，**唔係**任何numeric profile嘅approval authority。
